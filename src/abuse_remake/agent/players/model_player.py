"""The model-driven player: one model request per decision, validated by the episode.

    COURSE_MODEL=<model id> uv run abuse-agent --player model -- --provider vertex --memory M1

Each decision renders the observation, the legal actions and the memory text for the chosen
condition (``agent/memory.py``) into one prompt, makes one request with structured JSON output
and returns the model's ``action`` unchanged. The episode, not this player, decides whether the
action is legal: an answer that is not JSON, not a string or not in ``legal_actions`` is
refused and counted there. A failed request (timeout, rate limit, refusal, truncation) is
returned as a decision with no action, so it is refused and counted too. Nothing is repaired,
retried or substituted.

Token budgets (``max_input_tokens`` and ``max_output_tokens`` from the runner's budgets, or the
command line) are checked before each request. Once one is used up the player stops calling
the model and the runner ends the episode as "token budget exhausted".
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from ..memory import CONDITIONS, Memory
from ..prompts import decision_schema, render_turn, system_prompt
from ..protocol import serve
from ..providers import PROVIDERS, ProviderError, RequestLimits, make_provider


class ModelPlayer:
    def __init__(self, provider, memory: str = "M1", max_input_tokens: int = 0, max_output_tokens: int = 0,
                 log=None):
        self.provider = provider
        self.condition = memory
        self.default_caps = (max_input_tokens, max_output_tokens)
        self.log = log
        self.memory = Memory(memory)
        self.system = system_prompt(self.memory.keeps_notes)
        self.schema = decision_schema(self.memory.keeps_notes)
        self.start({})

    @classmethod
    def from_args(cls, argv: list[str], client=None) -> ModelPlayer:
        a = parser().parse_args(argv)
        limits = RequestLimits(timeout_s=a.timeout, max_output_tokens=a.max_output_tokens, effort=a.effort,
                               thinking_budget=a.thinking_budget)
        provider = make_provider(a.provider, a.model, limits, client)
        return cls(provider, a.memory, a.max_input_tokens_episode, a.max_output_tokens_episode, log=sys.stderr)

    # --- protocol --------------------------------------------------------------------------
    def start(self, info: dict) -> None:
        self.memory = Memory(self.condition)
        budgets = info.get("budgets") or {}
        self.max_in = self.default_caps[0] or int(budgets.get("max_input_tokens") or 0)
        self.max_out = self.default_caps[1] or int(budgets.get("max_output_tokens") or 0)
        self.used_in = self.used_out = self.calls = self.errors = 0

    def end(self, outcome: dict) -> None:
        if self.log is not None:
            print(f"model player: {self.calls} calls, {self.errors} errors, {self.used_in} input and "
                  f"{self.used_out} output tokens; notes cut {self.memory.notes_truncated} times",
                  file=self.log, flush=True)

    def decide(self, observation: dict, legal_actions: list[str]) -> dict:
        try:
            return self._decide(observation, legal_actions)
        except Exception as exc:  # noqa: BLE001 - a bug here must refuse one decision, not end the episode
            if self.log is not None:
                traceback.print_exc(file=self.log)
            return {"action": None, "error": f"player error: {type(exc).__name__}: {exc}"[:300],
                    "meta": self._meta(calls=0, errors=1, category="player_error")}

    # --- internals ---------------------------------------------------------------------------
    def budget_left(self) -> bool:
        return not ((self.max_in and self.used_in >= self.max_in) or (self.max_out and self.used_out >= self.max_out))

    def _meta(self, calls: int, errors: int, inp: int = 0, out: int = 0, latency: float | None = None,
              category: str | None = None, model: str | None = None) -> dict:
        return {"provider": self.provider.name, "model": model or self.provider.model, "memory": self.condition,
                "calls": calls, "errors": errors, "input_tokens": inp, "output_tokens": out,
                "latency_s": None if latency is None else round(latency, 3), "error_category": category}

    def _decide(self, obs: dict, legal: list[str]) -> dict:
        self.memory.observe(obs)
        if not self.budget_left():
            self.memory.record(obs["tick"], None)
            return {"action": None, "error": "token budget exhausted",
                    "meta": self._meta(calls=0, errors=0, category="budget")}
        prompt = render_turn(obs, legal, self.memory.render())
        t0 = time.monotonic()
        try:
            reply = self.provider.complete(self.system, prompt, self.schema)
        except ProviderError as exc:
            latency = time.monotonic() - t0
            self.calls += 1
            self.errors += 1
            self.used_in += exc.input_tokens
            self.used_out += exc.output_tokens
            self.memory.record(obs["tick"], None)
            return {"action": None, "error": f"model request failed: {exc}",
                    "meta": self._meta(1, 1, exc.input_tokens, exc.output_tokens, latency, exc.category)}
        latency = time.monotonic() - t0
        self.calls += 1
        self.used_in += reply.input_tokens
        self.used_out += reply.output_tokens
        meta = self._meta(1, 0, reply.input_tokens, reply.output_tokens, latency, None, reply.model)
        try:
            data = json.loads(reply.text)
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError:
            self.memory.record(obs["tick"], None)
            meta["error_category"] = "bad_json"
            return {"action": None, "error": "model reply is not a JSON object", "raw": reply.text[:600],
                    "meta": meta}
        action = data.get("action")  # passed on unchanged: the episode validates it
        note = data.get("note")
        self.memory.record(obs["tick"], action, data.get("notes"))
        out = {"action": action, "note": note if isinstance(note, str) else "", "raw": reply.text[:600],
               "meta": meta}
        if self.memory.keeps_notes:
            out["notes"] = self.memory.notes
        return out


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="model_player", description="Model-driven Abuse player")
    ap.add_argument("--provider", choices=PROVIDERS, default="vertex")
    ap.add_argument("--model", default=None, help="model ID (default: the COURSE_MODEL environment variable)")
    ap.add_argument("--memory", choices=CONDITIONS, default="M1")
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds per request (one attempt)")
    ap.add_argument("--max-output-tokens", type=int, default=1024, help="output cap per request")
    ap.add_argument("--effort", default=None, help="Anthropic effort / OpenAI reasoning effort (optional)")
    ap.add_argument("--thinking-budget", type=int, default=None, help="Gemini thinking budget (optional)")
    ap.add_argument("--max-input-tokens-episode", type=int, default=0, help="0 = use the runner's budget")
    ap.add_argument("--max-output-tokens-episode", type=int, default=0, help="0 = use the runner's budget")
    return ap


SDK_MODULE = {"vertex": "google.genai", "anthropic": "anthropic", "openai": "openai"}


def check_config(argv: list[str]) -> str | None:
    """A problem that would make every request fail, found before the episode starts, or None.
    Checks settings only; it never reads or tests credentials."""
    import importlib.util
    import os

    try:
        a = parser().parse_args(argv)
    except SystemExit:
        return "bad model player arguments"
    if not (a.model or os.environ.get("COURSE_MODEL", "").strip()):
        return "no model: pass --model or set COURSE_MODEL"
    try:
        found = importlib.util.find_spec(SDK_MODULE[a.provider]) is not None
    except ModuleNotFoundError:
        found = False
    if not found:
        return f"the {a.provider} SDK is not installed: run `uv sync --extra model`"
    if a.provider == "vertex" and not os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        return "set GOOGLE_CLOUD_PROJECT (and GOOGLE_CLOUD_LOCATION) for Vertex AI"
    return None


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return serve(ModelPlayer.from_args(argv))


if __name__ == "__main__":
    sys.exit(main())
