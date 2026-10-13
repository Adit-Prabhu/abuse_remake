"""The model-driven player and its provider adapters, with mocked clients (no network, no keys).

The adapters are tested against the real SDK exception and response types where the ``model``
extra is installed (CI installs it); fake clients stand in for the network.
"""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from abuse_remake.agent.interface import PLAYER_ID, AbuseEpisode, Budgets
from abuse_remake.agent.memory import NOTES_MAX, Memory
from abuse_remake.agent.players.model_player import ModelPlayer, check_config
from abuse_remake.agent.prompts import SYSTEM, decision_schema, render_turn, system_prompt
from abuse_remake.agent.protocol import InProcessPlayer
from abuse_remake.agent.providers import (
    ProviderConfigError,
    ProviderError,
    ProviderReply,
    RequestLimits,
    make_provider,
    resolve_model,
)
from abuse_remake.agent.runner import budget_stop, run_episode
from abuse_remake.agent.runner import main as runner_main


class FakeProvider:
    """Stands in for a provider: answers from a script and records every prompt."""

    name = "fake"
    model = "fake-model"

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def complete(self, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        a = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(a, Exception):
            raise a
        text = a if isinstance(a, str) else json.dumps(a)
        return ProviderReply(text=text, input_tokens=1000, output_tokens=30, model=self.model, stop="end")


def play(provider, memory="M1", decisions=6, **budget):
    player = ModelPlayer(provider, memory=memory)
    out = run_episode(InProcessPlayer(player), "level01", 0,
                      budgets=Budgets(max_ticks=9000, max_decisions=decisions, **budget))
    return out, player


# --- configuration: no hard-coded model ------------------------------------------------------
def test_model_comes_from_flag_or_course_model(monkeypatch):
    monkeypatch.delenv("COURSE_MODEL", raising=False)
    with pytest.raises(ProviderConfigError):
        resolve_model(None)
    monkeypatch.setenv("COURSE_MODEL", "  some-model  ")
    assert resolve_model(None) == "some-model"
    assert resolve_model("explicit") == "explicit"
    with pytest.raises(ProviderConfigError):
        make_provider("nope", "m")


def test_runner_refuses_to_start_a_model_player_without_a_model(monkeypatch, capsys):
    monkeypatch.delenv("COURSE_MODEL", raising=False)
    assert runner_main(["--player", "model", "--max-decisions", "2", "--", "--provider", "anthropic"]) == 2
    assert "COURSE_MODEL" in capsys.readouterr().err
    monkeypatch.setenv("COURSE_MODEL", "m")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    problem = check_config(["--provider", "vertex"])
    assert problem is not None and ("GOOGLE_CLOUD_PROJECT" in problem or "SDK" in problem)


def test_model_player_imports_no_engine_code():
    code = ("import sys, abuse_remake.agent.players.model_player; "
            "bad = [m for m in sys.modules if m.startswith('abuse_remake.engine') or m == 'pygame']; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# --- the player: one request per decision, answers passed on unchanged ------------------------
def test_one_request_per_decision_and_the_episode_validates():
    prov = FakeProvider([{"action": "explore right", "note": "go"}, {"action": "fly away", "note": "?"},
                         {"action": 7, "note": "bad type"}, {"action": "wait", "note": "rest"}])
    out, _ = play(prov, decisions=6)
    assert len(prov.calls) == 6 == out["model_calls"] == out["decisions"]
    assert out["invalid_actions"] == 2  # "fly away" and 7; the last answer ("wait") then repeats
    assert out["input_tokens"] == 6000 and out["output_tokens"] == 180
    assert out["provider"] == "fake" and out["model"] == "fake-model" and out["memory"] == "M1"


def test_refusals_reach_the_model_through_last_result():
    prov = FakeProvider([{"action": "fly away", "note": ""}, {"action": "wait", "note": ""}])
    play(prov, decisions=2)
    assert 'REFUSED: not in legal_actions' in prov.calls[1]["prompt"]


def test_failed_requests_are_refused_decisions_with_no_retry():
    prov = FakeProvider([ProviderError("timeout", "20 s"), {"action": "wait", "note": ""}])
    ep = AbuseEpisode("level01", seed=0)
    player = ModelPlayer(prov)
    reply = player.decide(ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID))
    assert reply["action"] is None and "timeout" in reply["error"]
    assert reply["meta"]["calls"] == 1 and reply["meta"]["errors"] == 1 and len(prov.calls) == 1
    assert reply["meta"]["error_category"] == "timeout"
    r = ep.step(PLAYER_ID, reply["action"])
    assert r["accepted"] is False and ep.invalid_actions == 1 and ep.ticks == 0


def test_non_json_answers_are_refused_with_the_raw_text_kept():
    prov = FakeProvider(["I think I will go right", ["wait"]])
    ep = AbuseEpisode("level01", seed=0)
    player = ModelPlayer(prov)
    for _ in range(2):
        reply = player.decide(ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID))
        assert reply["action"] is None and reply["meta"]["error_category"] == "bad_json"
        assert ep.step(PLAYER_ID, reply["action"])["accepted"] is False
    assert reply["raw"] == '["wait"]' and ep.invalid_actions == 2


def test_a_bug_in_the_player_refuses_one_decision_instead_of_crashing():
    class Broken(FakeProvider):
        def complete(self, system, prompt, schema):
            raise KeyError("boom")

    reply = ModelPlayer(Broken([])).decide(AbuseEpisode("level01", seed=0).observe(PLAYER_ID), ["wait"])
    assert reply["action"] is None and reply["meta"]["error_category"] == "player_error"


# --- budgets -----------------------------------------------------------------------------------
def test_token_budget_ends_the_episode_as_its_own_outcome():
    prov = FakeProvider([{"action": "wait", "note": ""}])
    out, _ = play(prov, decisions=50, max_input_tokens=3500)
    assert out["reason"] == "token budget exhausted" and out["status"] == "terminal"
    assert out["model_calls"] == 4 and out["input_tokens"] == 4000  # checked after each decision


def test_player_stops_calling_when_its_budget_is_spent():
    prov = FakeProvider([{"action": "wait", "note": ""}])
    player = ModelPlayer(prov)
    player.start({"budgets": {"max_input_tokens": 1500}})
    ep = AbuseEpisode("level01", seed=0)
    for _ in range(3):
        reply = player.decide(ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID))
        ep.step(PLAYER_ID, reply["action"])
    assert len(prov.calls) == 2 and reply["error"] == "token budget exhausted" and reply["meta"]["calls"] == 0


def test_wall_clock_budget():
    b = Budgets(max_wall_s=5.0)
    usage = {"input_tokens": 0, "output_tokens": 0}
    assert budget_stop(b, usage, 4.9) is None
    assert budget_stop(b, usage, 5.0) == "wall-clock budget exhausted"
    assert budget_stop(Budgets(), {"input_tokens": 10**9, "output_tokens": 10**9}, 10**6) is None  # 0 = no cap


# --- memory conditions -------------------------------------------------------------------------
@pytest.mark.parametrize("cond", ["M0", "M1", "M2"])
def test_memory_conditions_show_what_they_promise(cond):
    long_notes = "switch S1 opens the door. " * 40
    prov = FakeProvider([{"action": "explore right", "note": "", "notes": long_notes}])
    if cond != "M2":
        prov.answers = [{"action": "explore right", "note": ""}]
    play(prov, memory=cond, decisions=4)
    last = prov.calls[-1]
    assert ("notes" in last["schema"]["properties"]) == (cond == "M2")
    assert ("YOUR LAST 3 TURNS" in last["prompt"]) == (cond != "M0")
    assert ("AUTOMAP" in last["prompt"]) == (cond == "M2")
    assert ("YOUR NOTES: " + long_notes[:NOTES_MAX] in last["prompt"]) == (cond == "M2")
    assert long_notes[: NOTES_MAX + 1] not in last["prompt"]  # notes are capped at 600 characters


def test_history_keeps_only_the_last_8_turns():
    mem = Memory("M1")
    ep = AbuseEpisode("level01", seed=0)
    for i in range(12):
        obs = ep.observe(PLAYER_ID)
        mem.observe(obs)
        mem.record(obs["tick"], "wait" if i % 2 else "nonsense")
        ep.step(PLAYER_ID, "wait" if i % 2 else "nonsense")
    mem.observe(ep.observe(PLAYER_ID))
    text = mem.render()
    assert "YOUR LAST 8 TURNS" in text and text.count("\n  tick ") == 8
    assert "REFUSED (not in legal_actions)" in text


def test_automap_remembers_objects_off_screen_and_forgets_ones_that_vanished():
    mem = Memory("M2")
    ep = AbuseEpisode("level01", seed=0)
    first = ep.observe(PLAYER_ID)
    mem.observe(first)
    seen = {o["id"] for o in first["objects"]}
    for _ in range(25):
        ep.step(PLAYER_ID, "explore right")
    now = ep.observe(PLAYER_ID)
    mem.observe(now)
    gone_from_view = seen - {o["id"] for o in now["objects"]}
    text = mem.automap.render(now)
    for oid in gone_from_view:
        o = mem.automap.objects.get(oid)
        if o is not None:  # remembered: it must be outside the current view
            v = now["view"]
            assert not (v["x"] <= o["x"] <= v["x"] + v["w"] - 1 and v["y"] <= o["y"] <= v["y"] + v["h"] - 1)
    assert "explored x" in text


# --- prompts: only the observation, the legal actions and the memory ---------------------------
def test_prompt_is_a_pure_function_of_the_observation():
    ep = AbuseEpisode("level01", seed=3)
    obs, legal = ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID)
    assert render_turn(obs, legal) == render_turn(json.loads(json.dumps(obs)), list(legal))
    text = render_turn(obs, legal)
    assert "LEGAL ACTIONS: " + " | ".join(legal) in text
    assert "@" in text  # the player is marked on the screen map


def test_system_prompt_has_no_map_knowledge():
    for leak in ("2715", "NEXT_LEVEL", "ANT_ROOF", "aistate", "level01.spe", "rule-source-map"):
        assert leak not in SYSTEM
    assert system_prompt(True) != system_prompt(False) and '"notes"' in system_prompt(True)


def test_decision_schema_is_strict():
    for with_notes in (False, True):
        s = decision_schema(with_notes)
        assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])


# --- adapters against the real SDK types, with fake clients ------------------------------------
SCHEMA = decision_schema(False)
LIMITS = RequestLimits(timeout_s=20.0, max_output_tokens=777)


def _rec(result):
    calls = []

    def create(**kw):
        calls.append(kw)
        if isinstance(result, Exception):
            raise result
        return result
    return calls, create


def test_anthropic_adapter():
    anthropic = pytest.importorskip("anthropic")
    import httpx

    from abuse_remake.agent.providers.anthropic_provider import AnthropicProvider

    real = anthropic.Anthropic(api_key="placeholder-not-a-key", timeout=20.0, max_retries=0)
    assert real.max_retries == 0

    ok = SimpleNamespace(content=[SimpleNamespace(type="text", text='{"action": "wait", "note": "x"}')],
                         usage=SimpleNamespace(input_tokens=900, output_tokens=40, cache_read_input_tokens=100,
                                               cache_creation_input_tokens=0),
                         stop_reason="end_turn", model="m-resolved")
    calls, create = _rec(ok)
    prov = AnthropicProvider("m", LIMITS, SimpleNamespace(messages=SimpleNamespace(create=create)))
    r = prov.complete("sys", "prompt", SCHEMA)
    assert (r.text, r.input_tokens, r.output_tokens, r.model) == ('{"action": "wait", "note": "x"}', 1000, 40,
                                                                  "m-resolved")
    kw = calls[0]
    assert kw["model"] == "m" and kw["max_tokens"] == 777 and kw["system"] == "sys"
    assert kw["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert kw["messages"] == [{"role": "user", "content": "prompt"}]

    effort = AnthropicProvider("m", RequestLimits(effort="low"), SimpleNamespace(messages=SimpleNamespace(
        create=_rec(ok)[1])))
    assert effort.request("s", "p", SCHEMA)["output_config"]["effort"] == "low"

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp429 = httpx.Response(429, request=req)
    resp500 = httpx.Response(500, request=req)
    cases = [(anthropic.APITimeoutError(request=req), "timeout"),
             (anthropic.RateLimitError("slow down", response=resp429, body=None), "rate_limit"),
             (anthropic.InternalServerError("oops", response=resp500, body=None), "api_error"),
             (anthropic.APIConnectionError(request=req), "connection")]
    for exc, category in cases:
        prov = AnthropicProvider("m", LIMITS, SimpleNamespace(messages=SimpleNamespace(create=_rec(exc)[1])))
        with pytest.raises(ProviderError) as info:
            prov.complete("s", "p", SCHEMA)
        assert info.value.category == category

    for stop, category in (("refusal", "refusal"), ("max_tokens", "truncated")):
        bad = SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=5, output_tokens=777),
                              stop_reason=stop, stop_details=None, model="m")
        prov = AnthropicProvider("m", LIMITS, SimpleNamespace(messages=SimpleNamespace(create=_rec(bad)[1])))
        with pytest.raises(ProviderError) as info:
            prov.complete("s", "p", SCHEMA)
        assert info.value.category == category and info.value.output_tokens == 777  # billed tokens still count


def test_openai_adapter():
    openai = pytest.importorskip("openai")
    import httpx

    from abuse_remake.agent.providers.openai_provider import OpenAIProvider

    assert openai.OpenAI(api_key="placeholder-not-a-key", timeout=20.0, max_retries=0).max_retries == 0

    def completion(content, finish="stop", refusal=None):
        msg = SimpleNamespace(content=content, refusal=refusal)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)],
                               usage=SimpleNamespace(prompt_tokens=800, completion_tokens=25), model="o-resolved")

    calls, create = _rec(completion('{"action": "wait", "note": ""}'))
    prov = OpenAIProvider("o", LIMITS, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=create))))
    r = prov.complete("sys", "prompt", SCHEMA)
    assert (r.input_tokens, r.output_tokens, r.model) == (800, 25, "o-resolved")
    kw = calls[0]
    assert kw["model"] == "o" and kw["max_completion_tokens"] == 777 and "reasoning_effort" not in kw
    assert kw["response_format"]["json_schema"]["strict"] is True
    assert kw["response_format"]["json_schema"]["schema"] == SCHEMA
    assert kw["messages"][0] == {"role": "system", "content": "sys"}

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    for exc, category in [(openai.APITimeoutError(request=req), "timeout"),
                          (openai.RateLimitError("slow", response=httpx.Response(429, request=req), body=None),
                           "rate_limit"),
                          (openai.APIConnectionError(request=req), "connection")]:
        prov = OpenAIProvider("o", LIMITS, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=_rec(exc)[1]))))
        with pytest.raises(ProviderError) as info:
            prov.complete("s", "p", SCHEMA)
        assert info.value.category == category
    for bad, category in [(completion(None, refusal="no"), "refusal"), (completion("{", "length"), "truncated"),
                          (completion("", "stop"), "empty")]:
        prov = OpenAIProvider("o", LIMITS, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=_rec(bad)[1]))))
        with pytest.raises(ProviderError) as info:
            prov.complete("s", "p", SCHEMA)
        assert info.value.category == category


def test_vertex_adapter(monkeypatch):
    errors = pytest.importorskip("google.genai.errors")
    import httpx

    from abuse_remake.agent.providers.vertex import VertexProvider

    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ProviderConfigError):
        VertexProvider("g", LIMITS)  # fails before any client or credential is touched

    def response(text, finish="STOP", thoughts=12):
        return SimpleNamespace(text=text, prompt_feedback=None,
                               candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
                               usage_metadata=SimpleNamespace(prompt_token_count=700, candidates_token_count=20,
                                                              thoughts_token_count=thoughts))

    calls = []

    def gen(**kw):
        calls.append(kw)
        return response('{"action": "wait", "note": ""}')

    prov = VertexProvider("g", RequestLimits(max_output_tokens=777, thinking_budget=0),
                          SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    r = prov.complete("sys", "prompt", SCHEMA)
    assert (r.input_tokens, r.output_tokens) == (700, 32)  # thinking tokens are billed as output
    cfg = calls[0]["config"]
    assert calls[0]["model"] == "g" and calls[0]["contents"] == "prompt"
    assert cfg["response_mime_type"] == "application/json" and cfg["response_json_schema"] == SCHEMA
    assert cfg["max_output_tokens"] == 777 and cfg["thinking_config"] == {"thinking_budget": 0}
    assert cfg["system_instruction"] == "sys"
    from google.genai import types
    types.GenerateContentConfig(**cfg)  # the dict is a valid SDK config

    def raising(exc):
        def gen(**kw):
            raise exc
        return SimpleNamespace(models=SimpleNamespace(generate_content=gen))

    for exc, category in [(errors.ClientError(429, {"error": {"message": "quota"}}), "rate_limit"),
                          (errors.ServerError(503, {"error": {"message": "down"}}), "api_error"),
                          (httpx.ReadTimeout("slow"), "timeout"), (ConnectionError("reset"), "connection")]:
        with pytest.raises(ProviderError) as info:
            VertexProvider("g", LIMITS, raising(exc)).complete("s", "p", SCHEMA)
        assert info.value.category == category
    for resp, category in [(response("{", "MAX_TOKENS"), "truncated"), (response("", "SAFETY"), "refusal"),
                           (response("", "STOP"), "empty")]:
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda resp=resp, **kw: resp))
        with pytest.raises(ProviderError) as info:
            VertexProvider("g", LIMITS, client).complete("s", "p", SCHEMA)
        assert info.value.category == category and info.value.input_tokens == 700
