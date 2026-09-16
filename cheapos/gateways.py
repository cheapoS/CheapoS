"""Model discovery behind the same interface used for inference."""

import json
import math
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .providers import ChatProvider, NoRedirects, ProviderError


class ModelGateway(Protocol):
    def health(self): ...
    def list_models(self): ...
    def chat(self, messages, tools, max_tokens): ...


def normalize_models(data, openrouter=False, infer_access=True):
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ProviderError("The gateway did not return a model catalog")
    models, seen = [], set()
    for item in data["data"][:5000]:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 200 or model_id in seen:
            continue
        seen.add(model_id)
        pricing = item.get("pricing") or {}
        def rate(*keys):
            for k in keys:
                if k in pricing:
                    try:
                        value = float(pricing[k]) * 1_000_000
                        return value if math.isfinite(value) and 0 <= value <= 10000 else None
                    except (KeyError, TypeError, ValueError, OverflowError):
                        return None
            return None
        input_rate = rate("input", "prompt")
        output_rate = rate("output", "completion")
        provider_name = str(item.get("owned_by") or "")[:100]
        free_providers = {"antigravity", "kiro", "opencode", "oc", "nvidia", "groq"}
        provider_prefix = model_id.split("/")[0] if "/" in model_id else ""
        is_free_account = infer_access and (provider_name in free_providers or provider_prefix in free_providers)
        is_combo = item.get("owned_by") == "combo" or provider_name == "combo" or model_id.startswith("auto/")
        explicit_free = (
            ((model_id.endswith(":free") and (openrouter or model_id.startswith("openrouter/")))
             or model_id.endswith("-free")
             or is_free_account)
            and (not model_id.startswith("openrouter/") or model_id.endswith(":free"))
            and not is_combo
        )
        if is_free_account and not is_combo:
            input_rate = output_rate = 0.0
        elif infer_access and explicit_free and not pricing and input_rate is None and output_rate is None:
            input_rate = output_rate = 0.0
        capabilities = item.get("capabilities") or {}
        tools = capabilities.get("tool_calling") if isinstance(capabilities, dict) else None
        if not isinstance(tools, bool):
            supported = item.get("supported_parameters")
            tools = "tools" in supported if isinstance(supported, list) else None
        reasoning = capabilities.get("reasoning", capabilities.get("thinking")) if isinstance(capabilities, dict) else None
        if not isinstance(reasoning, bool):
            supported = item.get("supported_parameters")
            reasoning = any(p in supported for p in ("reasoning", "reasoning_effort")) if isinstance(supported, list) else None
        recovery_reasoning = None
        reasoning_meta = item.get("reasoning")
        supported = item.get("supported_parameters")
        if isinstance(reasoning_meta, dict) and isinstance(supported, list) and "reasoning" in supported:
            if reasoning_meta.get("mandatory") is False:
                recovery_reasoning = {"enabled": False}
            else:
                efforts = reasoning_meta.get("supported_efforts", [])
                if efforts is None:
                    recovery_reasoning = {"effort": "low"}
                elif isinstance(efforts, list):
                    effort = next((e for e in ("minimal", "low", "medium") if e in efforts), None)
                    if effort:
                        recovery_reasoning = {"effort": effort}
        context = item.get("context_length")
        output_limit = item.get("max_output_tokens")
        if output_limit is None and isinstance(item.get("top_provider"), dict):
            output_limit = item["top_provider"].get("max_completion_tokens")
        if not isinstance(output_limit, (int, float)) or isinstance(output_limit, bool) or (isinstance(output_limit,float) and not math.isfinite(output_limit)) or output_limit <= 0 or output_limit != int(output_limit):
            output_limit = None
        elif output_limit is not None:
            output_limit = int(output_limit)
        local = item.get("owned_by") == "ollama" and not model_id.startswith("auto/")
        if local and input_rate is None and output_rate is None:
            input_rate = output_rate = 0.0
        models.append({"id": model_id, "name": str(item.get("name") or model_id)[:240], "local":local,
                       "provider": provider_name, "combo": is_combo,
                       "context_length": context if isinstance(context, int) and not isinstance(context, bool) and context > 0 else None,
                       "max_output_tokens": output_limit, "tool_calling": tools, "reasoning": reasoning, "recovery_reasoning": recovery_reasoning,
                       "input_rate": input_rate, "output_rate": output_rate,
                       "free": input_rate == 0 and output_rate == 0 and not is_combo})
    return sorted(models, key=lambda m: m["id"])


class OpenAICompatibleGateway(ChatProvider):
    def _catalog(self, *, public=False):
        headers = {"Accept": "application/json", "User-Agent": "CheapOS/0.2"}
        if self.key and not public:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(self.config["base_url"].rstrip("/") + "/models", headers=headers)
        try:
            with build_opener(NoRedirects(), ProxyHandler({})).open(request, timeout=4) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ProviderError("Model catalog is too large")
                return json.loads(raw), response.headers
        except HTTPError as error:
            if error.code in {401, 403}:
                raise ProviderError("The gateway requires a valid client API key. Its dashboard password is separate.", code="client_key_rejected") from None
            raise ProviderError(f"Model discovery returned HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("The model endpoint is not reachable", code="endpoint_unavailable") from None
        except (ValueError, TypeError):
            raise ProviderError("The gateway returned an invalid model catalog", code="invalid_catalog") from None

    def list_models(self):
        data, _ = self._catalog()
        return normalize_models(data, openrouter=self.config["base_url"].startswith("https://openrouter.ai/"),
                                infer_access=self.config.get("gateway_type", "omniroute") == "omniroute")

    def health(self):
        try:
            self.list_models()
            return True
        except ProviderError:
            return False

    def chat(self, messages, tools, max_tokens):
        return super().complete(messages, tools, max_tokens)

    # Preserve the engine's existing injectable provider contract.
    def complete(self, messages, tools, max_tokens):
        return self.chat(messages, tools, max_tokens)


class OmniRouteGateway(OpenAICompatibleGateway):
    def __init__(self, config, key=""):
        # A shared gateway must never inherit a direct provider's role-specific key.
        self.config = config
        self.key = key

    def list_models(self):
        data, headers = self._catalog()
        if not headers.get("x-omniroute-route-class"):
            raise ProviderError("The endpoint is responding, but it was not identified as OmniRoute", code="unidentified_service")
        models = normalize_models(data)
        if any(m["id"].startswith("openrouter/") for m in models):
            # OmniRoute can advertise a bundled, stale provider catalog. Only
            # refresh an already connected provider; never forward its client key.
            try:
                upstream, _ = OpenAICompatibleGateway(
                    {"base_url": "https://openrouter.ai/api/v1", "key_env": "CHEAPOS_CATALOG_UNUSED"}
                )._catalog(public=True)
            except ProviderError:
                raise ProviderError("OpenRouter's current catalog could not be checked. Refresh Models before using its free routes.") from None
            models = refresh_openrouter_free_models(models, upstream)
        return models


def refresh_openrouter_free_models(models, upstream):
    # Explicit current prices are required here, rather than :free name inference.
    fresh = normalize_models(upstream)
    eligible = {m.get("id") for m in upstream.get("data", []) if isinstance(m, dict) and isinstance(m.get("id"), str)
                and isinstance(m.get("pricing"), dict) and {"prompt", "completion"} <= m["pricing"].keys()}
    kept = {m["id"]: m for m in models
            if not (m["id"].startswith("openrouter/") and (m["id"].endswith(":free") or m.get("free")))}
    for m in fresh:
        # Named variants preserve independent worker/reviewer identity; exclude
        # the provider's opaque free router and non-chat zero-priced products.
        if m["id"] in eligible and m["id"].endswith(":free") and m["free"]:
            m = {**m, "id": "openrouter/" + m["id"], "provider": "openrouter", "local": False}
            kept[m["id"]] = m
    return sorted(kept.values(), key=lambda m: m["id"])


def gateway_for(config, key=""):
    gateway = OmniRouteGateway if config.get("gateway") == "omniroute" and config.get("gateway_type", "omniroute") == "omniroute" else OpenAICompatibleGateway
    return gateway(config, key)
