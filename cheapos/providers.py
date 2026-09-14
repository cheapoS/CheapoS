"""OpenAI-compatible chat completions, with explicit accounting before dispatch."""

import json
from .measurement import enabled as measuring
import math
import os
import re
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from .streaming import read_chat_stream
from .served_identity import metadata


REQUEST_TIMEOUT_SECONDS = 180


def is_local_ollama(config):
    endpoint = urlsplit(config.get("base_url", ""))
    return config.get("gateway") != "omniroute" and endpoint.hostname in {"127.0.0.1", "localhost", "::1"} and endpoint.port == 11434


class ProviderError(Exception):
    def __init__(self, message, code=None, retry_after=None, scope=None, usage=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.scope = scope
        self.usage = usage


def http_failure(error, config):
    """Read bounded machine metadata only; do not expose upstream bodies/secrets."""
    reason = {401: "API key was rejected", 402: "Provider credit limit reached", 403: "Provider denied access", 429: "Provider rate limit reached"}.get(error.code, f"Provider returned HTTP {error.code}")
    if config.get("gateway") == "omniroute" and error.code not in {401, 402, 403}:
        try:
            raw = error.read(16385)
            data = json.loads(raw) if len(raw) <= 16384 else {}
            metadata = data.get("error", {}) if isinstance(data, dict) else {}
            code = metadata.get('code') if isinstance(metadata, dict) else None
        except (ValueError, OSError):
            code = None
        delay = None
        try:
            value = error.headers.get("Retry-After", "")
            try:
                candidate = float(value)
            except ValueError:
                candidate = parsedate_to_datetime(value).timestamp() - time.time()
            if math.isfinite(candidate) and candidate > 0:
                delay = min(86400, max(1, math.ceil(candidate)))
        except (ValueError, TypeError, OverflowError, AttributeError):
            pass
        if delay is not None or code in {'model_cooldown', 'provider_cooldown'} or error.code == 429:
            # Only explicit shared-quota metadata can exclude sibling models.
            scope = 'provider' if code == 'provider_cooldown' else 'model'
            retry = f'Retry in about {delay} seconds.' if delay is not None else 'The reset time is unknown.'
            return ProviderError(f'OmniRoute reports a {scope} cooldown. {retry} No model compatibility conclusion was drawn.',
                                 code='gateway_cooldown', retry_after=delay, scope=scope)
    if error.code == 404:
        reason = "This model route is unavailable (HTTP 404)"
    return ProviderError(reason + ". This request did not complete.", code=f"http_{error.code}")


class BudgetError(Exception):
    def __init__(self, message, limit=None, used=None, allowed=None):
        super().__init__(message)
        self.limit_hit = {'key': limit, 'used': used, 'allowed': allowed, 'remaining': max(0, allowed-used)} if limit and used is not None and allowed is not None else None


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_provider(value, role):
    if not isinstance(value, dict):
        raise ValueError("Provider settings must be an object")
    endpoint = str(value.get("base_url", "")).rstrip("/")
    parsed = urlsplit(endpoint)
    try:
        parsed.port
    except ValueError:
        raise ValueError("Use a valid API endpoint port") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an API base URL without credentials, query parameters, or fragments")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote model endpoints must use HTTPS")
    model = str(value.get("model", "")).strip()
    if not model or len(model) > 200:
        raise ValueError(f"Choose a {role} model ID")
    access = value.get('access')
    if access not in (None, 'included'):
        raise ValueError('Invalid provider access classification')
    rates = []
    for key in ("input_rate", "output_rate"):
        try:
            rate = 0.0 if access == 'included' else float(value[key])
        except (ValueError, TypeError, KeyError):
            raise ValueError("Set input and output prices per million tokens (0 for a free/local model)")
        if not math.isfinite(rate) or rate < 0 or rate > 10000:
            raise ValueError("Invalid model price")
        rates.append(rate)
    env = value.get("key_env") or f"CHEAPOS_{role.upper()}_API_KEY"
    if not re.fullmatch(r"CHEAPOS_[A-Z0-9_]+", env):
        raise ValueError("API key environment variable names must start with CHEAPOS_")
    gateway = value.get("gateway", "openai")
    if gateway not in {"openai", "omniroute"}:
        raise ValueError("Choose OmniRoute or an OpenAI-compatible connection")
    result = {"base_url": endpoint, "model": model, "input_rate": rates[0], "output_rate": rates[1], "key_env": env, "gateway": gateway}
    if access:
        result['access'] = access
    return result


class ChatProvider:
    def __init__(self, config, key=""):
        self.config = config
        self.key = key or os.environ.get(config["key_env"], "")

    def complete(self, messages, tools, max_tokens):
        return self._complete(messages, tools, max_tokens)

    @property
    def streams_output(self):
        return self.config.get("gateway") == "omniroute" or is_local_ollama(self.config)

    def complete_with_progress(self, messages, tools, max_tokens, emit, stopped):
        return self._complete(messages, tools, max_tokens, emit, stopped)

    def greet(self, messages, emit, stopped):
        return self._complete(messages, [], 512, emit, stopped, timeout_seconds=30, stream_seconds=60, brief=True)

    def complete_brief(self, messages, tools, max_tokens, emit, stopped):
        return self._complete(messages, tools, max_tokens, emit, stopped, timeout_seconds=30, stream_seconds=60, brief=True)

    def _complete(self, messages, tools, max_tokens, emit=None, stopped=lambda: False, timeout_seconds=REQUEST_TIMEOUT_SECONDS, stream_seconds=600, brief=False):
        body = {"model": self.config["model"], "messages": messages, "stream": emit is not None}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if self.config.get("_recovery_reasoning") is not None:
            body["reasoning"] = self.config["_recovery_reasoning"]
        if brief and is_local_ollama(self.config):
            body.update({"max_tokens": min(max_tokens, 512 if tools else 128), "reasoning_effort":"none"})
        if emit is not None:
            body["stream_options"] = {"include_usage": True}
        if tools:
            body.update({"tools": tools, "tool_choice": "auto", "parallel_tool_calls": False})
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream" if emit is not None else "application/json", "User-Agent": "CheapOS/0.2"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(self.config["base_url"] + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        try:
            with build_opener(NoRedirects()).open(request, timeout=timeout_seconds) as response:
                if emit is not None and response.headers.get_content_type() == "text/event-stream":
                    data = read_chat_stream(response, emit, stopped, ProviderError, max_seconds=stream_seconds)
                else:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise ProviderError("Provider response exceeded 4 MB")
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        detail = f'{error.msg}, line {error.lineno}, column {error.colno}' if isinstance(error, json.JSONDecodeError) else 'invalid text encoding'
                        raise ProviderError(f'Provider returned malformed response JSON ({detail}). No tool calls from this response were executed.', code='invalid_response_json') from None
        except InterruptedError:
            raise
        except HTTPError as error:
            raise http_failure(error, self.config) from None
        except (URLError, TimeoutError, OSError) as error:
            if isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError):
                duration = "3 minutes" if timeout_seconds == 180 else f"{timeout_seconds} seconds"
                reason = f"The model stopped sending output for {duration}" if emit is not None else f"The model did not finish within {duration}"
                raise ProviderError(reason + ". Uncertain usage remains counted.", code="model_timeout") from None
            raise ProviderError("The model connection failed before a complete response arrived. Uncertain usage remains counted.", code="model_connection") from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("Provider returned an invalid response structure. No tool calls from this response were executed.", code="invalid_response_shape") from None
        try:
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError()
            if choice.get("finish_reason") == "length":
                raise ProviderError("The model reached its output limit before finishing. Partial tool calls were not executed.",
                                    code="output_limit", usage=data.get("usage"))
            message = choice["message"]
            if not isinstance(message, dict) or not (message.get("content") or message.get("tool_calls")):
                raise ValueError()
            # Preserve tool IDs and reasoning_details required by some tool-capable providers.
            message = {key: value for key, value in message.items() if key in {"role", "content", "tool_calls", "reasoning_details", "reasoning"}}
            message["role"] = "assistant"
            usage=dict(data.get("usage") or {})
            usage["_served_identity"]=metadata(self.config["model"],data.get("model"))
            return message, usage
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("Provider returned no usable message or tool calls", code="empty_response") from None


def reserve(task, config, messages, tools, role):
    # A deliberately conservative preflight estimate; provider tokenizers/billing can differ.
    prompt_bound = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False).encode("utf-8")) + 1024
    output = int(task["limits"]["output_tokens"])
    if role == "reviewer" and not measuring(task):
        remaining = task["limits"]["reviewer_tokens"] - task["usage"]["reviewer"]["tokens"]
        output = min(output, remaining - prompt_bound)
    token_blocked = output < 128
    remaining_cost = task["limits"]["dollars"] - task["usage"]["cost"]
    input_cost = prompt_bound * config["input_rate"] / 1_000_000
    if config["output_rate"]:
        output = min(output, math.floor((remaining_cost - input_cost) * 1_000_000 / config["output_rate"]))
    projected = input_cost + max(0, output) * config["output_rate"] / 1_000_000
    if output < 128 or projected > remaining_cost + 1e-10:
        key = 'reviewer_tokens' if role == 'reviewer' and token_blocked else 'dollars'
        used = task['usage']['reviewer']['tokens'] if key == 'reviewer_tokens' else task['usage']['cost']
        raise BudgetError("The next model request does not fit the remaining budget. Increase the task limit or use a smaller checkpoint/model.", key, used, task['limits'][key])
    reservation = {"role": role, "prompt_tokens": prompt_bound, "completion_tokens": output, "tokens": prompt_bound + output, "cost": projected}
    bucket = task["usage"][role]
    bucket["tokens"] += reservation["tokens"]
    bucket["cost"] += projected
    task["usage"]["cost"] += projected
    task["usage"]["uncertain_requests"] += 1
    task["in_flight"] = reservation
    return reservation


def reconcile(task, config, reservation, usage):
    def count(key):
        value = usage.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    prompt, completion = count("prompt_tokens"), count("completion_tokens")
    if prompt is None or completion is None:
        task["in_flight"] = None
        return False
    cost = usage.get("cost")
    reported_cost = isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0
    if not reported_cost:
        cost = (prompt * config["input_rate"] + completion * config["output_rate"]) / 1_000_000
    bucket = task["usage"].setdefault(reservation["role"], {"tokens": 0, "cost": 0})
    bucket["tokens"] += prompt + completion - reservation["tokens"]
    bucket["cost"] += cost - reservation["cost"]
    task["usage"]["cost"] += cost - reservation["cost"]
    task["usage"]["uncertain_requests"] -= 1
    if not reported_cost:
        task["usage"]["estimated_requests"] += 1
    task["in_flight"] = None
    return True
