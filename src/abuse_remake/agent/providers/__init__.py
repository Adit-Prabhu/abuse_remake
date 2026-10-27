"""Provider adapters for the model-driven player.

Every adapter makes exactly one request per decision:

- no automatic retries (a course requirement: a failed request is a refused decision, never a
  silent paid retry), and SDK-level retries are switched off;
- a per-request timeout and a per-request output-token cap;
- structured JSON output against a fixed schema;
- the model ID comes from ``--model`` or ``COURSE_MODEL``, never from code, and the resolved
  ID is returned with every reply so the runner can record it.

A failed request raises ``ProviderError`` with a category (``timeout``, ``rate_limit``,
``api_error``, ``connection``, ``refusal``, ``truncated``, ``empty``, ``auth``). The player turns
it into a refused decision. Nothing is retried and no fixture is substituted. An ``auth`` error
(missing or rejected credentials, no permission, unknown model) is marked fatal: every later
request would fail the same way, so the runner ends the episode with its own reason rather than
spend the rest of the budget on refusals.

Each SDK is imported only by its own adapter module, and only when that provider is chosen,
so the game and the baselines never need the ``model`` extra.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

PROVIDERS = ("vertex", "anthropic", "openai")


@dataclass(frozen=True)
class RequestLimits:
    timeout_s: float = 20.0
    max_output_tokens: int = 1024
    effort: str | None = None  # Anthropic output_config.effort, OpenAI reasoning_effort
    thinking_budget: int | None = None  # Gemini thinking budget in tokens


@dataclass
class ProviderReply:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    stop: str | None = None


class ProviderError(Exception):
    """One failed request. Tokens the provider still billed (a truncated or refused answer)
    are carried so the budget counts them."""

    def __init__(self, category: str, message: str, input_tokens: int = 0, output_tokens: int = 0):
        super().__init__(f"{category}: {message}"[:300])
        self.category = category
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.fatal = category == "auth"


FATAL_STATUS = (401, 403, 404)  # bad or missing credentials, no permission, unknown model


class ProviderConfigError(RuntimeError):
    """Missing model or provider settings; raised before any request is made."""


def resolve_model(model: str | None) -> str:
    model = (model or os.environ.get("COURSE_MODEL", "")).strip()
    if not model:
        raise ProviderConfigError("no model: pass --model or set COURSE_MODEL")
    return model


def make_provider(name: str, model: str | None, limits: RequestLimits | None = None, client=None):
    limits = limits or RequestLimits()
    model = resolve_model(model)
    if name == "vertex":
        from .vertex import VertexProvider

        return VertexProvider(model, limits, client)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model, limits, client)
    if name == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(model, limits, client)
    raise ProviderConfigError(f"unknown provider {name!r}; choose from {', '.join(PROVIDERS)}")


def short(exc: BaseException) -> str:
    """A one-line error message for traces (SDK messages carry request IDs, never keys)."""
    return " ".join(str(exc).split())[:200] or type(exc).__name__
