"""Gemini on Vertex AI through the ``google-genai`` SDK: the default live provider.

Credentials are Application Default Credentials (``gcloud auth application-default login``).
The project and region come from ``GOOGLE_CLOUD_PROJECT`` and ``GOOGLE_CLOUD_LOCATION``. This
module never reads or stores a key.
"""

from __future__ import annotations

import os

from . import FATAL_STATUS, ProviderConfigError, ProviderError, ProviderReply, RequestLimits, short

REFUSAL_FINISH = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}


class VertexProvider:
    name = "vertex"

    def __init__(self, model: str, limits: RequestLimits, client=None):
        self.model = model
        self.limits = limits
        if client is None:
            from google import genai
            from google.genai import types

            project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
            if not project:
                raise ProviderConfigError("set GOOGLE_CLOUD_PROJECT (and GOOGLE_CLOUD_LOCATION) for Vertex AI")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
            client = genai.Client(
                vertexai=True, project=project, location=location,
                http_options=types.HttpOptions(timeout=int(limits.timeout_s * 1000),  # milliseconds
                                               retry_options=types.HttpRetryOptions(attempts=1)))
        self.client = client

    def config(self, system: str, schema: dict) -> dict:
        cfg = {"system_instruction": system, "response_mime_type": "application/json",
               "response_json_schema": schema, "max_output_tokens": self.limits.max_output_tokens,
               # the SDK would otherwise send follow-up requests on finish_reason CONTINUATION,
               # each billed: one decision must be one request
               "automatic_continuation": False}
        if self.limits.thinking_budget is not None:
            cfg["thinking_config"] = {"thinking_budget": self.limits.thinking_budget}
        return cfg

    def complete(self, system: str, prompt: str, schema: dict) -> ProviderReply:
        try:
            resp = self.client.models.generate_content(model=self.model, contents=prompt,
                                                       config=self.config(system, schema))
        except Exception as exc:  # noqa: BLE001 - every failure of the one attempt is classified
            raise ProviderError(_classify(exc), short(exc)) from exc
        usage = getattr(resp, "usage_metadata", None)
        inp = int(getattr(usage, "prompt_token_count", 0) or 0)
        out = int(getattr(usage, "candidates_token_count", 0) or 0) \
            + int(getattr(usage, "thoughts_token_count", 0) or 0)  # thinking is billed as output
        feedback = getattr(resp, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise ProviderError("refusal", f"prompt blocked: {_name(feedback.block_reason)}", inp, out)
        cands = getattr(resp, "candidates", None) or []
        finish = _name(getattr(cands[0], "finish_reason", None)) if cands else ""
        if finish in ("MAX_TOKENS", "CONTINUATION"):
            raise ProviderError("truncated", f"hit max_output_tokens={self.limits.max_output_tokens}", inp, out)
        if finish in REFUSAL_FINISH:
            raise ProviderError("refusal", f"finish_reason {finish}", inp, out)
        text = getattr(resp, "text", None) or ""
        if not text.strip():
            raise ProviderError("empty", f"no text (finish_reason {finish or 'none'})", inp, out)
        model = getattr(resp, "model_version", None) or self.model  # the version that answered
        return ProviderReply(text=text, input_tokens=inp, output_tokens=out, model=model, stop=finish or None)


def _name(value) -> str:
    return str(getattr(value, "name", None) or value or "")


def _classify(exc: BaseException) -> str:
    try:
        from google.genai import errors
    except ImportError:  # only with an injected client and no SDK
        errors = None
    if errors is not None and isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        if code == 429:
            return "rate_limit"
        if code in (408, 504):
            return "timeout"
        if code in FATAL_STATUS:
            return "auth"
        return "api_error"
    if isinstance(exc, _types("TimeoutException", "Timeout")) or isinstance(exc, TimeoutError):
        return "timeout"  # checked first: requests.Timeout is also a ConnectionError
    if isinstance(exc, _types("TransportError", "ConnectionError")) or isinstance(exc, ConnectionError):
        return "connection"
    if _is_auth_error(exc):
        return "auth"
    return "api_error"


def _types(httpx_name: str, requests_name: str) -> tuple[type[BaseException], ...]:
    """Exception classes from the HTTP libraries google-genai may use (httpx, httpx2, requests)."""
    found: list[type[BaseException]] = []
    for mod, name in (("httpx", httpx_name), ("httpx2", httpx_name), ("requests.exceptions", requests_name)):
        try:
            found.append(getattr(__import__(mod, fromlist=[name]), name))
        except (ImportError, AttributeError):
            pass
    return tuple(found)


def _is_auth_error(exc: BaseException) -> bool:
    try:
        from google.auth import exceptions as gauth
    except ImportError:
        return False
    return isinstance(exc, gauth.GoogleAuthError)  # no or bad Application Default Credentials
