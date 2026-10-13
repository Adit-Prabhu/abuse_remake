"""JSON-lines protocol between the runner and a player program.

The player is a separate process, so it can only know what the runner sends it. Any program
in any language that speaks this protocol is a valid "executable player".

runner -> player, one JSON object per line:
    {"type": "start", "player_id": "player", "scenario": ..., "budgets": {...}}
    {"type": "decide", "id": 7, "observation": {...}, "legal_actions": [...]}
    {"type": "end", "outcome": {...}}      # the episode's outcome; no evaluator-only data
player -> runner, one JSON object per line, in reply to each "decide":
    {"id": 7, "action": "<one of legal_actions>", "note": "<optional>", "meta": {<optional usage data>}}

The player writes protocol messages to stdout only; logs go to stderr. If a reply is late
(``decision_timeout``), not a JSON object, or missing, the runner sends no action to ``step``
(the raw text is kept for the trace), so the episode refuses and counts it like any other invalid
action. A reply that carries the ``id`` of an earlier request arrived too late: it is discarded,
never used for a later decision, and its usage data is passed on as ``late_meta`` so its tokens
still count. (Replies without an ``id`` are accepted, for simple players.)

Environment: a player process gets a minimal environment (``BASE_ENV``), never the runner's
whole environment. Only the model player also gets the variables its provider's SDK reads
(``MODEL_ENV_PREFIXES``); those never enter prompts, observations or traces.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Protocol


class Policy(Protocol):
    def start(self, info: dict) -> None: ...

    def decide(self, observation: dict, legal_actions: list[str]) -> dict: ...

    def end(self, outcome: dict) -> None: ...


BASE_ENV = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP",
            "SYSTEMROOT", "PYTHONPATH", "VIRTUAL_ENV", "PYTHONHASHSEED")
MODEL_ENV_PREFIXES = ("COURSE_MODEL", "GOOGLE_", "CLOUDSDK_", "GCLOUD_", "ANTHROPIC_", "OPENAI_",
                      "SSL_CERT_", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")


def player_env(with_model_credentials: bool = False, source: dict | None = None) -> dict:
    src = dict(os.environ if source is None else source)
    env = {k: v for k, v in src.items() if k in BASE_ENV}
    if with_model_credentials:
        env.update({k: v for k, v in src.items() if k.startswith(MODEL_ENV_PREFIXES)})
    env["PYTHONUNBUFFERED"] = "1"
    return env


def serve(policy: Policy, stdin=None, stdout=None) -> int:
    """Run ``policy`` as a player program over stdin/stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        kind = msg.get("type")
        if kind == "start":
            policy.start(msg)
        elif kind == "decide":
            reply = dict(policy.decide(msg["observation"], msg["legal_actions"]))
            if "id" in msg:
                reply["id"] = msg["id"]
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
        elif kind == "end":
            policy.end(msg.get("outcome", {}))
            break
    return 0


class ProcessPlayer:
    """Runner side: a player program in a child process."""

    def __init__(self, command: list[str], decision_timeout: float = 90.0, env: dict | None = None):
        self.command = command
        self.timeout = decision_timeout
        child_env = player_env() if env is None else dict(env)
        child_env.setdefault("PYTHONUNBUFFERED", "1")
        self.next_id = 0
        self.late: list[dict] = []  # usage data from replies that came after their deadline
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=sys.stderr, text=True, env=child_env)
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, msg: dict) -> None:
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def start(self, info: dict) -> None:
        self._send({"type": "start", **info})

    def decide(self, observation: dict, legal_actions: list[str]) -> dict:
        self.next_id += 1
        rid = self.next_id
        self._send({"type": "decide", "id": rid, "observation": observation, "legal_actions": legal_actions})
        t0 = time.monotonic()
        while True:
            left = self.timeout - (time.monotonic() - t0)
            try:
                line = self._lines.get(timeout=max(0.0, left))
            except queue.Empty:
                return self._attach_late({"action": None, "error": f"no reply within {self.timeout:.0f} s",
                                          "raw": None, "wall_s": time.monotonic() - t0})
            if line is None:
                return self._attach_late({"action": None, "error": "player process ended", "fatal": True,
                                          "raw": None, "wall_s": time.monotonic() - t0})
            try:
                reply = json.loads(line)
                if not isinstance(reply, dict):
                    raise ValueError("reply is not an object")
            except ValueError:  # refused, never read as an action: a bare "wait" must not slip through
                return self._attach_late({"action": None, "error": "reply is not a JSON object",
                                          "raw": line.strip()[:500], "wall_s": time.monotonic() - t0})
            if "id" in reply and reply["id"] != rid:
                if isinstance(reply.get("meta"), dict):
                    self.late.append(reply["meta"])  # an answer to an earlier request: drop it, keep its usage
                continue
            reply.setdefault("raw", line.strip()[:2000])
            reply["wall_s"] = time.monotonic() - t0
            return self._attach_late(reply)

    def _attach_late(self, reply: dict) -> dict:
        if self.late:
            reply["late_meta"], self.late = self.late, []
        return reply

    def end(self, outcome: dict) -> None:
        self._send({"type": "end", "outcome": outcome})
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()


class InProcessPlayer:
    """Runner side, for fast tests: the policy gets JSON copies, never live objects."""

    def __init__(self, policy: Policy):
        self.policy = policy

    def start(self, info: dict) -> None:
        self.policy.start(json.loads(json.dumps(info)))

    def decide(self, observation: dict, legal_actions: list[str]) -> dict:
        t0 = time.monotonic()
        reply = self.policy.decide(json.loads(json.dumps(observation)), list(legal_actions))
        reply = dict(reply)
        reply.setdefault("raw", json.dumps(reply)[:2000])
        reply["wall_s"] = time.monotonic() - t0
        return reply

    def end(self, outcome: dict) -> None:
        self.policy.end(json.loads(json.dumps(outcome)))
