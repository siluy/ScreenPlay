"""Isolated experimental text drivers; private engine state never enters observations."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
import uuid

from screenplay.build import ROOT
from screenplay.native import NativeBackend
from screenplay.tasks import load_task
from .structured import StructuredText


class NativeTextProcess(StructuredText):
    """One trusted child and one request at a time, with the existing decision budget."""

    input_updates = 6
    wait_quantum_ms = None

    def __init__(self, task_id, condition="text-symbolic", max_decisions=None):
        if max_decisions is None:
            max_decisions = load_task(task_id).max_decisions
        super().__init__(task_id, condition, max_decisions)
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.private = Path(tempfile.mkdtemp(prefix="text-prototype-", dir=ROOT / "tmp"))
        self.session = "text-" + uuid.uuid4().hex
        (self.private / "fixture.json").write_text(json.dumps(self.task.parameters))
        (self.private / "advance.txt").write_text("0 0\n")
        self.process = None
        self._buffer = b""
        self._log = (self.private / "native.log").open("wb")
        self._evaluator = NativeBackend()
        self._evaluator.task = self.task
        self.sequence = 0

    def launch(self, command, *, cwd=ROOT, extra_env=None):
        env = dict(os.environ, SCREENPLAY_SESSION=self.session,
                   SCREENPLAY_SCENARIO=self.task.game_id,
                   SCREENPLAY_PRIVATE_DIR=str(self.private),
                   SCREENPLAY_STATE_FILE=str(self.private / "state.json"),
                   SCREENPLAY_CONTROL_FILE=str(self.private / "advance.txt"),
                   PYTHONPATH=str(ROOT / "src"))
        env.update(extra_env or {})
        for name in ("SANKUAI_AUTH_TOKEN", "SCREENPLAY_API_KEY", "SUB2API_API_KEY", "OPENAI_API_KEY"):
            env.pop(name, None)
        try:
            self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self._log)
            self._state = self.read_reply()
            if self.score()["success"]:
                raise RuntimeError("Initial task already solved")
        except BaseException:
            self.close()
            raise

    def read_reply(self, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                if line.startswith(b"GWSTATE "):
                    value = json.loads(line[8:])
                    if (value.get("session") != self.session or value.get("pid") != self.process.pid
                            or value.get("control_sequence") != self.sequence):
                        raise RuntimeError(f"Native text response identity/sequence mismatch; diagnostics: {self.private}")
                    return value
                self._log.write(line + b"\n")
                self._log.flush()
                continue
            ready, _, _ = select.select([self.process.stdout], [], [], max(0, deadline-time.monotonic()))
            if not ready:
                break
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError(f"Native text driver exited; diagnostics: {self.private}")
            self._buffer += data
        raise RuntimeError(f"Native text driver timed out; diagnostics: {self.private}")

    def apply(self, action):
        self.sequence += 1
        remaining = self.task.parameters["max_updates"] - self._state["processed_updates"]
        quantum = self.wait_quantum_ms or self.task.parameters.get("update_ms", 33)
        updates = (math.ceil(action["duration_ms"] / quantum)
                   if action["type"] == "wait" else self.input_updates)
        message = {"sequence": self.sequence, "updates": min(updates, max(0, remaining)), "action": action}
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()
        self._state = self.read_reply(timeout=max(45, updates * .15))
        if self._state.get("action_error"):
            raise ValueError("Rejected native UI action")

    def score(self):
        return self._evaluator.evaluate(self._state)

    def describe(self):
        return self._state["text"]

    def observe(self):
        observation = super().observe()
        observation["experimental"] = True
        observation["interface_profile"] = self.interface_profile
        observation["simulation_updates_remaining"] = max(0, self.task.parameters["max_updates"]-self._state["processed_updates"])
        return observation

    def native_state(self):
        return json.loads(json.dumps(self._state))

    def close(self):
        if self.process is not None:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            if self.process.stdout:
                self.process.stdout.close()
        self._log.close()

