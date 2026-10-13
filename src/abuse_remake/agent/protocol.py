"""JSON-lines protocol between the runner and a player program.

The player is a separate process, so it can only know what the runner sends it. Any program
in any language that speaks this protocol is a valid "executable player".

runner -> player, one JSON object per line:
    {"type": "start", "player_id": "player", "scenario": ..., "budgets": {...}}
    {"type": "decide", "observation": {...}, "legal_actions": [...]}
    {"type": "end", "outcome": {...}}
player -> runner, one JSON object per line, in reply to each "decide":
    {"action": "<one of legal_actions>", "note": "<optional>", "meta": {<optional usage data>}}

The player writes protocol messages to stdout only; logs go to stderr. If a reply is late
(``decision_timeout``), not a JSON object, or missing, the runner sends no action to ``step``
(the raw text is kept for the trace), so the episode refuses and counts it like any other invalid
action.
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
            reply = policy.decide(msg["observation"], msg["legal_actions"])
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
        child_env = dict(os.environ if env is None else env)
        child_env.setdefault("PYTHONUNBUFFERED", "1")
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
        self._send({"type": "decide", "observation": observation, "legal_actions": legal_actions})
        t0 = time.monotonic()
        try:
            line = self._lines.get(timeout=self.timeout)
        except queue.Empty:
            return {"action": None, "error": f"no reply within {self.timeout:.0f} s", "raw": None,
                    "wall_s": time.monotonic() - t0}
        if line is None:
            return {"action": None, "error": "player process ended", "raw": None, "wall_s": time.monotonic() - t0}
        try:
            reply = json.loads(line)
            if not isinstance(reply, dict):
                raise ValueError("reply is not an object")
        except ValueError:  # refused, never read as an action: a bare "wait" must not slip through
            return {"action": None, "error": "reply is not a JSON object", "raw": line.strip()[:500],
                    "wall_s": time.monotonic() - t0}
        reply.setdefault("raw", line.strip()[:2000])
        reply["wall_s"] = time.monotonic() - t0
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
