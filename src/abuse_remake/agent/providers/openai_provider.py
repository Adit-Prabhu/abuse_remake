"""OpenAI models through the official ``openai`` SDK (Chat Completions).

Credentials are whatever the SDK resolves from the environment (``OPENAI_API_KEY``). This
module never reads or stores a key. Structured output uses a strict ``json_schema``
``response_format``.
"""

from __future__ import annotations

import openai

from . import FATAL_STATUS, ProviderConfigError, ProviderError, ProviderReply, RequestLimits, short


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, limits: RequestLimits, client=None):
        self.model = model
        self.limits = limits
        if client is None:
            try:
                client = openai.OpenAI(timeout=limits.timeout_s, max_retries=0)
            except openai.OpenAIError as exc:  # no OPENAI_API_KEY: report it before the episode starts
                raise ProviderConfigError(f"OpenAI client: {short(exc)}") from exc
        self.client = client

    def request(self, system: str, prompt: str, schema: dict) -> dict:
        req = {"model": self.model, "max_completion_tokens": self.limits.max_output_tokens,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
               "response_format": {"type": "json_schema",
                                   "json_schema": {"name": "decision", "schema": schema, "strict": True}}}
        if self.limits.effort:
            req["reasoning_effort"] = self.limits.effort
        return req

    def complete(self, system: str, prompt: str, schema: dict) -> ProviderReply:
        try:
            resp = self.client.chat.completions.create(**self.request(system, prompt, schema))
        except openai.APITimeoutError as exc:  # subclass of APIConnectionError: check first
            raise ProviderError("timeout", short(exc)) from exc
        except openai.RateLimitError as exc:
            raise ProviderError("rate_limit", short(exc)) from exc
        except openai.APIStatusError as exc:
            category = "auth" if exc.status_code in FATAL_STATUS else "api_error"
            raise ProviderError(category, f"HTTP {exc.status_code}: {short(exc)}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderError("connection", short(exc)) from exc
        except openai.OpenAIError as exc:  # e.g. a 200 response that fails validation
            raise ProviderError("api_error", short(exc)) from exc
        usage = resp.usage
        inp = int(getattr(usage, "prompt_tokens", 0) or 0)
        out = int(getattr(usage, "completion_tokens", 0) or 0)
        if not resp.choices:
            raise ProviderError("empty", "no choices", inp, out)
        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            raise ProviderError("refusal", short(choice.message.refusal), inp, out)
        if choice.finish_reason == "length":
            raise ProviderError("truncated", f"hit max_completion_tokens={self.limits.max_output_tokens}", inp, out)
        if choice.finish_reason == "content_filter":
            raise ProviderError("refusal", "finish_reason content_filter", inp, out)
        text = choice.message.content or ""
        if not text.strip():
            raise ProviderError("empty", f"no content (finish_reason {choice.finish_reason})", inp, out)
        return ProviderReply(text=text, input_tokens=inp, output_tokens=out, model=getattr(resp, "model", self.model),
                             stop=choice.finish_reason)
