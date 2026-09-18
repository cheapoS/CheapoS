"""OpenAI-compatible chat completions, with explicit accounting before dispatch."""

import json
from .measurement import enabled as measuring
import math
import re
import time
import socket
import threading
from contextlib import nullcontext
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from .streaming import read_chat_stream
from .served_identity import metadata
from .request_pacer import pacer, provider_identity, gateway_identity, pacing_interval


REQUEST_TIMEOUT_SECONDS = 180


def is_local_ollama(config):
    try:
        endpoint = urlsplit(config.get("base_url", ""))
        return (config.get("gateway") != "omniroute" and endpoint.scheme == "http"
                and endpoint.hostname in {"127.0.0.1", "localhost", "::1"} and endpoint.port == 11434
                and endpoint.path.rstrip("/") == "/v1" and not any((endpoint.username, endpoint.password, endpoint.query, endpoint.fragment)))
    except ValueError:
        return False


def guard_inference_route(config, gateway_url):
    """Development policy: remote inference uses the configured local OmniRoute.

    This also checks captured task settings; labels or an old provider API key
    cannot turn a direct remote endpoint into an authorized gateway.
    """
    if is_local_ollama(config):
        return
    def identity(url):
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
                or parsed.path.rstrip('/') != '/v1'
                or any((parsed.username, parsed.password, parsed.query, parsed.fragment))):
            return None
        port = parsed.port if parsed.port is not None else 80
        if not 1 <= port <= 65535:
            return None
        return ('127.0.0.1' if parsed.hostname == 'localhost' else parsed.hostname, port)
    try:
        target = identity(config.get('base_url', ''))
        if config.get('gateway') == 'omniroute' and target is not None and target == identity(gateway_url):
            return
    except (TypeError, ValueError):
        pass
    raise ValueError('Remote models must use the configured OmniRoute or compatible gateway connection. '
                     'Open Models and select the configured gateway; direct provider endpoints are disabled. '
                     'Saved tasks keep their original connection and edits; start a new chat with the gateway model choices.')


class ProviderError(Exception):
    def __init__(self, message, code=None, retry_after=None, scope=None, usage=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.scope = scope
        self.usage = usage


class ToolCallValidationError(ProviderError):
    """A gateway rejected generated tool arguments before returning the call."""
    def __init__(self):
        super().__init__('The provider rejected the generated tool call because its arguments did not match the tool schema. No tools were executed.', code='http_400')


def http_failure(error, config):
    """Read bounded machine metadata only; do not expose upstream bodies/secrets."""
    reason = {401: "API key was rejected", 402: "Provider credit limit reached", 403: "Provider denied access", 429: "Provider rate limit reached"}.get(error.code, f"Provider returned HTTP {error.code}")
    if config.get("gateway") == "omniroute":
        try:
            raw = error.read(16385)
            data = json.loads(raw) if len(raw) <= 16384 else {}
            metadata = data.get("error", {}) if isinstance(data, dict) else {}
            code = metadata.get('code') if isinstance(metadata, dict) else None
        except (ValueError, OSError):
            metadata = {}
            code = None
        if error.code in {400, 413, 422} and code in {'context_length_exceeded', 'context_window_exceeded'}:
            return ProviderError('The request exceeds this route context capacity.', code=code, scope='request')
        detail = metadata.get('message', '') if isinstance(metadata, dict) else ''
        if error.code in {401, 402, 403}:
            # OmniRoute can relay an upstream access refusal using the same
            # status as its own client-key rejection. Only recognize a known
            # upstream contract for the requested provider; ambiguous auth
            # errors still block this connection. Never retain the raw body.
            provider = provider_identity(config)
            missing_credentials = (isinstance(detail, str) and provider != 'unknown'
                                   and detail.startswith(f'No active credentials for provider: {provider}.'))
            restricted_opencode = (error.code == 403 and provider == 'opencode' and isinstance(detail, str)
                                   and detail.removeprefix('[403]: Error from provider (Console): ').rstrip('.')
                                   == "OpenCode's free tier can only be used from within OpenCode")
            if missing_credentials or restricted_opencode:
                return ProviderError('This upstream provider does not permit this connection.',
                                     code='upstream_access_denied', scope='provider')
            return ProviderError(reason + '. This request did not complete.', code=f'http_{error.code}')
        # Groq can reject a generated call at the gateway before CheapOS sees
        # its arguments. Keep this distinct from a bad HTTP request/connection,
        # without retaining failed_generation or arbitrary upstream error text.
        if error.code == 400 and (code in {'tool_use_failed', 'tool_call_validation_failed'}
                or (isinstance(detail, str) and detail.lower().startswith('tool call validation failed:'))):
            return ToolCallValidationError()
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
            detail = (metadata.get('message') or '') if isinstance(metadata, dict) else ''
            scope = 'provider' if code == 'provider_cooldown' or (isinstance(detail, str) and any(k in detail.lower() for k in ('quota', 'daily limit', 'rate limit', 'credit', 'exhausted'))) else 'model'
            retry = f'Retry in about {delay} seconds.' if delay is not None else 'The reset time is unknown.'
            return ProviderError(f'OmniRoute reports a {scope} cooldown. {retry} No model compatibility conclusion was drawn.',
                                 code='gateway_cooldown', retry_after=delay, scope=scope)
    if error.code == 404:
        reason = "This model route is unavailable (HTTP 404)"
    return ProviderError(reason + ". This request did not complete.", code=f"http_{error.code}")


class BudgetError(Exception):
    code = 'budget_exceeded'

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
    if "connection_id" in value:
        identity = value["connection_id"]
        if not isinstance(identity,str) or not re.fullmatch(r"default|[a-f0-9]{32}",identity):
            raise ValueError("Choose a saved gateway connection")
        result["connection_id"] = identity
    if "gateway_type" in value:
        from .omniroute import GATEWAY_TYPES
        if value["gateway_type"] not in GATEWAY_TYPES:
            raise ValueError("Unknown gateway adapter")
        result["gateway_type"] = value["gateway_type"]
    if "provider" in value and isinstance(value["provider"], str):
        result["provider"] = value["provider"]
    if "pacing" in value:
        result["pacing"] = bool(value["pacing"])
    if "pacing_interval" in value:
        try:
            result["pacing_interval"] = max(0.0, float(value["pacing_interval"]))
        except (ValueError, TypeError):
            pass
    if access:
        result['access'] = access
    return result


class BriefResponseGuard:
    """Cancel only an active brief transport, including a blocked response read.

    The watchdog never invokes a model or schedules another consultation. Socket
    shutdown precedes close so a buffered readline releases its internal lock.
    """
    def __init__(self, response, stopped, seconds, clock=None):
        self.response=response;self.stopped=stopped;self.clock=clock or time.monotonic
        self.deadline=self.clock()+seconds;self.done=threading.Event()
        self.thread=None;self.reason=None

    def poll(self):
        if self.reason or self.done.is_set():return
        reason='cancelled' if self.stopped() else 'deadline' if self.clock()>=self.deadline else None
        if not reason:return
        self.reason=reason
        for path in (('fp','raw','_sock'),('fp','_sock'),('_sock',)):
            obj=self.response
            for name in path:obj=getattr(obj,name,None)
            if obj is not None:
                try:obj.shutdown(socket.SHUT_RDWR)
                except (OSError,AttributeError):pass
        try:self.response.close()
        except (OSError,ValueError):pass

    def _watch(self):
        while not self.done.wait(.05):
            self.poll()
            if self.reason:return

    def __enter__(self):
        self.poll()
        if not self.reason:
            self.thread=threading.Thread(target=self._watch,daemon=True,name='cheapos-brief-response')
            self.thread.start()
        return self

    def __exit__(self, kind, value, traceback):
        self.poll()
        self.done.set()
        if self.thread:self.thread.join()
        if self.reason=='cancelled':raise InterruptedError('Brief model request cancelled')
        if self.reason=='deadline':raise ProviderError('The brief model request reached its response deadline. Uncertain usage remains counted.',code='model_timeout')
        return False


class ChatProvider:
    def __init__(self, config, key=""):
        self.config = config
        self.key = key
        self.request_timing = {}

    def complete(self, messages, tools, max_tokens, tool_choice=None):
        return self._complete(messages, tools, max_tokens, tool_choice=tool_choice)

    @property
    def streams_output(self):
        return self.config.get("gateway") == "omniroute" or is_local_ollama(self.config)

    def complete_with_progress(self, messages, tools, max_tokens, emit, stopped, tool_choice=None):
        return self._complete(messages, tools, max_tokens, emit, stopped, tool_choice=tool_choice)

    def greet(self, messages, emit, stopped):
        return self._complete(messages, [], 512, emit, stopped, timeout_seconds=30, stream_seconds=60, brief=True)

    def complete_brief(self, messages, tools, max_tokens, emit, stopped):
        return self._complete(messages, tools, max_tokens, emit, stopped, timeout_seconds=30, stream_seconds=60, brief=True)

    def _complete(self, messages, tools, max_tokens, emit=None, stopped=lambda: False, timeout_seconds=REQUEST_TIMEOUT_SECONDS, stream_seconds=600, brief=False, tool_choice=None):
        if not brief and self.config.get("_request_seconds"):
            timeout_seconds = stream_seconds = self.config["_request_seconds"]
        clean_messages = [{k: v for k, v in m.items() if k != 'reasoning_fallback'} for m in messages]
        body = {"model": self.config["model"], "messages": clean_messages, "stream": emit is not None}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if self.config.get("_recovery_reasoning") is not None:
            body["reasoning"] = self.config["_recovery_reasoning"]
        if brief and is_local_ollama(self.config):
            body.update({"max_tokens": min(max_tokens, 512 if tools or self.config.get("_coordinator_recovery") is True else 128), "reasoning_effort":"none"})
            if self.config.get('_coordinator_recovery') is True:
                body['response_format'] = {'type': 'json_object'}
        if emit is not None:
            body["stream_options"] = {"include_usage": True}
        if tools:
            body.update({"tools": tools, "tool_choice": tool_choice or "auto", "parallel_tool_calls": False})
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream" if emit is not None else "application/json", "User-Agent": "CheapOS/0.2"}
        if self.config.get("gateway_type") == "9router":
            headers["X-9Router-Token-Saver"] = "off"
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(self.config["base_url"] + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        from .structural_telemetry import add
        try:
            add(self.request_timing, 'request_wire', wire_bytes=len(request.data or b''))
        except Exception:
            pass
        provider_name = provider_identity(self.config)
        gateway_name = gateway_identity(self.config)
        payload_bytes = len(request.data) if request.data else 0
        interval = pacing_interval(self.config, provider_name, payload_bytes=payload_bytes)
        with pacer.throttle(provider_name, interval, gateway=gateway_name, stopped=stopped, timing=self.request_timing):
            network_started = time.monotonic()
            try:
                with build_opener(NoRedirects(), ProxyHandler({})).open(request, timeout=timeout_seconds) as response, (BriefResponseGuard(response, stopped, stream_seconds if emit is not None else timeout_seconds) if brief or self.config.get("_operator_interruptible") else nullcontext()):
                    if emit is not None and response.headers.get_content_type() == "text/event-stream":
                        data = read_chat_stream(response, emit, stopped, ProviderError, max_seconds=stream_seconds)
                        response_wire_bytes = data.get("_wire_bytes")
                    else:
                        raw = response.read(4_000_001)
                        response_wire_bytes = len(raw)
                        if len(raw) > 4_000_000:
                            raise ProviderError("Provider response exceeded 4 MB", code="response_too_large")
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
            finally:
                self.request_timing['gateway_request_seconds'] = time.monotonic() - network_started
        try:
            add(self.request_timing, 'response_extraction',
                wire_bytes=response_wire_bytes,
                extraction='native' if data['choices'][0]['message'].get('tool_calls') else 'none',
                tool_count=len(data['choices'][0]['message'].get('tool_calls') or []), transformed=True)
        except Exception:
            pass
        try:
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError()
            if choice.get("finish_reason") == "length":
                raise ProviderError("The model reached its output limit before finishing. Partial tool calls were not executed.",
                                    code="output_limit", usage=data.get("usage"))
            message = choice["message"]
            if not bool(message.get("tool_calls")) and not (isinstance(message.get("content"), str) and message["content"].strip()) and isinstance(message.get("reasoning"), str) and message["reasoning"].strip():
                message["content"] = message["reasoning"]
                message["reasoning_fallback"] = True
            has_content = isinstance(message.get("content"), str) and bool(message["content"].strip())
            has_tools = bool(message.get("tool_calls"))
            if not isinstance(message, dict) or not (has_content or has_tools):
                raise ValueError()
            # Preserve tool IDs and reasoning_details required by some tool-capable providers.
            message = {key: value for key, value in message.items() if key in {"role", "content", "tool_calls", "reasoning_details", "reasoning", "reasoning_fallback"}}
            message["role"] = "assistant"
            usage=dict(data.get("usage") or {})
            usage["_served_identity"]=metadata(self.config["model"],data.get("model"))
            return message, usage
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("Provider returned no usable message or tool calls", code="empty_response") from None


def reserve(task, config, messages, tools, role):
    # Add new role accounting only at dispatch; never rewrite historical totals.
    if role in {'planner','coordinator'} and role not in task['usage']:
        task['usage'][role] = {'tokens': 0, 'cost': 0}
    bucket = task['usage'].get(role)
    if not isinstance(bucket, dict) or any(isinstance(bucket.get(k), bool) or not isinstance(bucket.get(k), (int, float)) or not math.isfinite(bucket[k]) or bucket[k] < 0 for k in ('tokens', 'cost')):
        raise ValueError('Saved role accounting is invalid; inspect the saved task before resuming')
    # A deliberately conservative preflight estimate; provider tokenizers/billing can differ.
    prompt_bytes = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False).encode("utf-8"))
    prompt_bound = prompt_bytes + 1024
    from .request_budget import resolve
    output = int(config.get("_effective_output_tokens", resolve(task, config)["tokens"]))
    from .work_budgets import effective, active
    selected_review = effective(task).get("work_review_tokens") if active(task) else None
    if role == "reviewer" and selected_review is not None:
        output = min(output, selected_review - task["usage"]["reviewer"]["tokens"] - prompt_bound)
    if role == "reviewer" and not measuring(task):
        remaining = task["limits"]["reviewer_tokens"] - task["usage"]["reviewer"]["tokens"]
        output = min(output, remaining - prompt_bound)
    minimum_output = 1 if 'response_tokens' in task['limits'] else 128
    review_allowance = selected_review if selected_review is not None else task['limits'].get('reviewer_tokens') if not measuring(task) else None
    token_blocked = role == 'reviewer' and review_allowance is not None and review_allowance - task['usage']['reviewer']['tokens'] - prompt_bound < minimum_output
    remaining_cost = task["limits"]["dollars"] - task["usage"]["cost"]
    input_cost = prompt_bound * config["input_rate"] / 1_000_000
    if config["output_rate"]:
        output = min(output, math.floor((remaining_cost - input_cost) * 1_000_000 / config["output_rate"]))
    projected = input_cost + max(0, output) * config["output_rate"] / 1_000_000
    if output < minimum_output or projected > remaining_cost + 1e-10:
        key = 'reviewer_tokens' if role == 'reviewer' and token_blocked else 'dollars'
        if key == 'reviewer_tokens' and selected_review is not None: key = 'work_review_tokens'
        used = task['usage']['reviewer']['tokens'] if key in {'reviewer_tokens','work_review_tokens'} else task['usage']['cost']
        raise BudgetError("The next model request does not fit the remaining budget. Increase the task limit or use a smaller checkpoint/model.", key, used, selected_review if key == 'work_review_tokens' else task['limits'][key])
    reservation = {"role": role, "prompt_tokens": prompt_bound, "completion_tokens": output, "tokens": prompt_bound + output, "cost": projected}
    reservation.update(basis='serialized_utf8_bytes_plus_buffer_v1', prompt_bytes=prompt_bytes, buffer_tokens=1024)
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
