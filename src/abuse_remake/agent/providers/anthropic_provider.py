"""Claude through the official ``anthropic`` SDK (Messages API).

Credentials are whatever the SDK resolves from the environment (``ANTHROPIC_API_KEY`` or an
``ant auth login`` profile). This module never reads or stores a key.

Structured output uses ``output_config.format`` (a JSON schema), so the first text block is the
JSON answer. ``max_tokens`` covers thinking too on models that always think, so keep
``--max-output-tokens`` generous and use ``--effort low`` to keep the answer fast.
"""

from __future__ import annotations

import anthropic

from . import FATAL_STATUS, ProviderError, ProviderReply, RequestLimits, short


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, limits: RequestLimits, client=None):
        self.model = model
        self.limits = limits
        self.client = client or anthropic.Anthropic(timeout=limits.timeout_s, max_retries=0)

    def request(self, system: str, prompt: str, schema: dict) -> dict:
        output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
        if self.limits.effort:
            output_config["effort"] = self.limits.effort
        return {"model": self.model, "max_tokens": self.limits.max_output_tokens, "system": system,
                "messages": [{"role": "user", "content": prompt}], "output_config": output_config}

    def complete(self, system: str, prompt: str, schema: dict) -> ProviderReply:
        try:
            resp = self.client.messages.create(**self.request(system, prompt, schema))
        except anthropic.APITimeoutError as exc:  # subclass of APIConnectionError: check first
            raise ProviderError("timeout", short(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate_limit", short(exc)) from exc
        except anthropic.APIStatusError as exc:
            category = "auth" if exc.status_code in FATAL_STATUS else "api_error"
            raise ProviderError(category, f"HTTP {exc.status_code}: {short(exc)}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection", short(exc)) from exc
        except anthropic.AnthropicError as exc:  # e.g. a 200 response that fails validation, identity errors
            raise ProviderError("api_error", short(exc)) from exc
        except TypeError as exc:  # the SDK raises this when it finds no credentials at all
            raise ProviderError("auth", short(exc)) from exc
        usage = resp.usage
        inp = int(usage.input_tokens or 0) + int(getattr(usage, "cache_read_input_tokens", 0) or 0) \
            + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        out = int(usage.output_tokens or 0)
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            category = getattr(details, "category", None) if details is not None else None
            raise ProviderError("refusal", f"stop_reason refusal ({category or 'no category'})", inp, out)
        if resp.stop_reason == "max_tokens":
            raise ProviderError("truncated", f"hit max_tokens={self.limits.max_output_tokens}", inp, out)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        if not text.strip():
            raise ProviderError("empty", f"no text block (stop_reason {resp.stop_reason})", inp, out)
        return ProviderReply(text=text, input_tokens=inp, output_tokens=out, model=getattr(resp, "model", self.model),
                             stop=resp.stop_reason)
