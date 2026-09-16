"""Client-side request pacer for free and rate-limited LLM providers.

Enforces minimum quiet intervals between consecutive requests to the same
provider and serializes concurrent calls to single-concurrency free tiers
(e.g. OpenRouter :free, NVIDIA NIM, OpenCode/Ling, Groq, Antigravity) to
prevent HTTP 429 rate limit errors, HTTP 500/503 upstream crashes, and token
burst rejections.
"""

import os
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

# Minimum quiet intervals (seconds) required between completions for known free providers.
# These delays prevent triggering Tokens-Per-Minute (TPM) caps and strict 1-concurrency limits.
PROVIDER_PACING_SECONDS = {
    "openrouter": 5.0,     # OpenRouter :free tier: smooth 12 RPM, avoids burst rate/TPM limit
    "nvidia": 4.0,         # NVIDIA NIM: concurrency=1, token recovery, avoids 500 crashes
    "opencode": 4.0,       # OpenCode / Ling: endpoint recovery, avoids 503
    "oc": 4.0,
    "antigravity": 4.0,    # Google Gemini free tier: 15 RPM
    "google": 4.0,
    "groq": 2.0,           # Groq: high throughput
    "kiro": 3.0,           # Kiro endpoint pacing
    "openai": 4.0,         # OpenAI free/shared tier pacing
    "omniroute": 4.0,      # OmniRoute gateway shared pacing
}

DEFAULT_FREE_PACING_SECONDS = 3.0


def provider_identity(config):
    """Determine upstream provider key for pacing and concurrency grouping."""
    if not isinstance(config, dict):
        return "unknown"
    if config.get("local"):
        return "local"
    # Explicit provider tag from gateway discovery catalog
    provider = str(config.get("provider") or "").strip().lower()
    if provider:
        if provider.startswith("opencode") or provider == "oc":
            return "opencode"
        if provider == "google":
            return "antigravity"
        return provider

    # Check base_url: local ollama / localhost mock endpoints (not OmniRoute)
    endpoint = str(config.get("base_url") or "")
    try:
        parsed = urlsplit(endpoint)
        if config.get("gateway") != "omniroute" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            return "local"
    except ValueError:
        pass

    # Inspect model name
    model = str(config.get("model") or "").strip().lower()
    if model.startswith("fixture") or model == "fixture":
        return "fixture"

    clean_model = model.removeprefix("no-think/")
    prefix = clean_model.split("/", 1)[0] if "/" in clean_model else ""

    if prefix in {"nvidia", "groq", "antigravity", "opencode", "oc", "kiro", "openrouter", "ollama", "google"}:
        if prefix in {"opencode", "oc"}:
            return "opencode"
        if prefix == "google":
            return "antigravity"
        return prefix

    if ":free" in clean_model or clean_model.endswith("-free"):
        if clean_model.startswith("ling-") or clean_model.startswith("nemotron-3.5-lightning"):
            return "opencode"
        return "openrouter"

    return prefix or "remote"


def gateway_identity(config):
    """Determine gateway identifier (e.g. omniroute) for cross-model rate limiting."""
    if not isinstance(config, dict):
        return None
    gw = config.get("gateway")
    if gw and isinstance(gw, str) and gw.strip():
        return gw.strip().lower()
    base_url = str(config.get("base_url") or "")
    if "20128" in base_url or "omniroute" in base_url.lower():
        return "omniroute"
    return None


def pacing_interval(config, provider=None, payload_bytes=0):
    """Return required minimum interval (in seconds) between requests to this provider."""
    if not isinstance(config, dict):
        return 0.0
    if os.environ.get("CHEAPOS_DISABLE_PACING") == "1":
        return 0.0
    if config.get("pacing") is False:
        return 0.0
    if "pacing_interval" in config:
        try:
            val = float(config["pacing_interval"])
            return max(0.0, val)
        except (ValueError, TypeError):
            pass

    # Fixture models and local models never pace
    ident = (provider or provider_identity(config)).lower()
    if ident in {"local", "fixture", "ollama"}:
        return 0.0

    model = str(config.get("model") or "").lower()
    if model.startswith("fixture"):
        return 0.0

    # Paid models (non-zero rate and not included access) do not require free-tier throttling
    if config.get("access") != "included":
        input_rate = config.get("input_rate")
        output_rate = config.get("output_rate")
        try:
            if input_rate is not None and output_rate is not None:
                if float(input_rate) > 0 or float(output_rate) > 0:
                    return 0.0
        except (ValueError, TypeError):
            pass

    base = PROVIDER_PACING_SECONDS.get(ident, DEFAULT_FREE_PACING_SECONDS)
    # Payload-aware token scaling to prevent TPM exhaustion on large context turns
    extra = 0.0
    if ident != "groq" and payload_bytes:
        if payload_bytes > 160_000:       # ~40k+ prompt tokens
            extra = 4.0
        elif payload_bytes > 60_000:      # ~15k+ prompt tokens
            extra = 2.0
    return base + extra


class RequestPacer:
    """Thread-safe rate limiter and request serializer per provider."""

    def __init__(self):
        self._lock = threading.RLock()
        self._provider_locks = {}
        self._last_completed = {}
        self._stats = {"delays_count": {}, "total_delayed_seconds": {}}

    def _get_provider_lock(self, provider):
        with self._lock:
            if provider not in self._provider_locks:
                self._provider_locks[provider] = threading.RLock()
            return self._provider_locks[provider]

    @contextmanager
    def throttle(self, provider, min_interval, gateway=None, stopped=None):
        """Serialize calls to the provider and enforce quiet cooldown between calls."""
        if min_interval <= 0:
            yield
            return

        targets = [provider]
        if gateway:
            gw_target = f"gateway:{gateway}"
            if gw_target not in targets:
                targets.append(gw_target)

        acquired = []
        try:
            for target in sorted(targets):
                lock = self._get_provider_lock(target)
                if not lock.acquire(blocking=False):
                    while not lock.acquire(timeout=0.05):
                        if stopped and stopped():
                            raise InterruptedError(f"Task stopped while waiting for {target} provider slot")
                acquired.append(lock)

            delayed_duration = 0.0
            with self._lock:
                now = time.monotonic()
                remaining = 0.0
                for target in targets:
                    last_time = self._last_completed.get(target)
                    if last_time is not None:
                        elapsed = now - last_time
                        rem = min_interval - elapsed
                        if rem > remaining:
                            remaining = rem

            if remaining > 0:
                delayed_duration = remaining
                deadline = time.monotonic() + remaining
                while time.monotonic() < deadline:
                    if stopped and stopped():
                        raise InterruptedError(f"Task stopped during {provider} provider cooldown")
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

                with self._lock:
                    self._stats["delays_count"][provider] = self._stats["delays_count"].get(provider, 0) + 1
                    self._stats["total_delayed_seconds"][provider] = self._stats["total_delayed_seconds"].get(provider, 0.0) + delayed_duration

            yield
        finally:
            now = time.monotonic()
            with self._lock:
                for target in targets:
                    self._last_completed[target] = now
            for lock in reversed(acquired):
                lock.release()

    def reset(self):
        with self._lock:
            self._last_completed.clear()
            self._stats["delays_count"].clear()
            self._stats["total_delayed_seconds"].clear()

    def stats(self):
        with self._lock:
            return {
                "last_completed": dict(self._last_completed),
                "delays_count": dict(self._stats["delays_count"]),
                "total_delayed_seconds": dict(self._stats["total_delayed_seconds"]),
            }


# Singleton pacer instance
pacer = RequestPacer()
