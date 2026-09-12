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


def normalize_models(data, openrouter=False):
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
        def rate(key):
            try:
                value = float(pricing[key]) * 1_000_000
                return value if math.isfinite(value) and 0 <= value <= 10000 else None
            except (KeyError, TypeError, ValueError, OverflowError):
                return None
        input_rate, output_rate = rate("prompt"), rate("completion")
        explicit_free = model_id.endswith(":free") and (openrouter or model_id.startswith("openrouter/"))
        if explicit_free and input_rate is None and output_rate is None:
            input_rate = output_rate = 0.0
        capabilities = item.get("capabilities") or {}
        tools = capabilities.get("tool_calling") if isinstance(capabilities, dict) else None
        if not isinstance(tools, bool):
            supported = item.get("supported_parameters")
            tools = "tools" in supported if isinstance(supported, list) else None
        context = item.get("context_length")
        local = item.get("owned_by") == "ollama" and not model_id.startswith("auto/")
        if local and input_rate is None and output_rate is None:
            input_rate = output_rate = 0.0
        models.append({"id": model_id, "name": str(item.get("name") or model_id)[:240], "local":local,
                       "provider": str(item.get("owned_by") or "")[:100],
                       "context_length": context if isinstance(context, int) and not isinstance(context, bool) and context > 0 else None,
                       "tool_calling": tools, "input_rate": input_rate, "output_rate": output_rate,
                       "free": input_rate == 0 and output_rate == 0 and not model_id.startswith("auto/") and item.get("owned_by") != "combo"})
    return sorted(models, key=lambda m: m["id"])


class OpenAICompatibleGateway(ChatProvider):
    def _catalog(self):
        headers = {"Accept": "application/json", "User-Agent": "CheapOS/0.2"}
        if self.key:
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
                raise ProviderError("The gateway requires a valid client API key. Its dashboard password is separate.") from None
            raise ProviderError(f"Model discovery returned HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("The model endpoint is not reachable") from None
        except (ValueError, TypeError):
            raise ProviderError("The gateway returned an invalid model catalog") from None

    def list_models(self):
        data, _ = self._catalog()
        return normalize_models(data, openrouter=self.config["base_url"].startswith("https://openrouter.ai/"))

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
            raise ProviderError("The endpoint is responding, but it was not identified as OmniRoute")
        return normalize_models(data)


def gateway_for(config, key=""):
    gateway = OmniRouteGateway if config.get("gateway") == "omniroute" else OpenAICompatibleGateway
    return gateway(config, key)
