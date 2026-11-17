"""Original Cocoa game frontend plus a private, read-only telemetry channel."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .build import ROOT
from .desktop import PyAutoGUIDesktop
from .tasks import Task, parse_save


class TathamBackend:
    def __init__(self):
        self.process = None
        self.desktop = None
        self.log = None

    def start(self, task: Task, private_dir: Path, session: str):
        if sys.platform != "darwin":
            raise RuntimeError("Native frontend currently implemented for macOS; Linux GTK adapter is not yet implemented")
        binary = ROOT / "build/tatham/bin/ScreenPlayPuzzles.app/Contents/MacOS/ScreenPlayPuzzles"
        if not binary.exists():
            raise RuntimeError("Run screenplay build tatham first")
        self.state_file = private_dir / "latest_state.json"
        self.session = session
        env = dict(os.environ, SCREENPLAY_SESSION=session, SCREENPLAY_GAME=task.game,
                   SCREENPLAY_GAME_ID=task.game_id, SCREENPLAY_STATE_FILE=str(self.state_file))
        self.log = (private_dir / "game_process.log").open("w")
        self.process = subprocess.Popen([str(binary)], cwd=private_dir, env=env,
                                        stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Game exited during startup; see {private_dir / 'game_process.log'}")
            if self.state_file.exists():
                state = self.state()
                fields = dict(parse_save(state["serialized"]))
                if fields.get("GAME") != task.game:
                    raise RuntimeError("Wrong game initialized")
                if task.expected_desc and fields.get("DESC") != task.expected_desc:
                    raise RuntimeError("Wrong task initialized")
                if state["status"] == 1:
                    raise RuntimeError("Initial task is already solved")
                self.initial_desc = fields["DESC"]
                return state
            time.sleep(.05)
        raise RuntimeError("Game did not report readiness within 15 seconds")

    def state(self) -> dict:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Game process is not running")
        state = json.loads(self.state_file.read_text())
        if state.get("session") != self.session or state.get("pid") != self.process.pid:
            raise RuntimeError("Telemetry session mismatch")
        if time.time() - state["captured_at"] > 2:
            raise RuntimeError("Game telemetry is stale")
        parse_save(state["serialized"])
        return state

    def _desktop(self):
        if self.desktop is None:
            self.desktop = PyAutoGUIDesktop(self.process.pid)
        return self.desktop

    def capture(self):
        # Pair the frame with stable puzzle state; animations are not gameplay dynamics.
        for _ in range(5):
            before = self.state()
            image = self._desktop().capture(before["viewport"])
            after = self.state()
            if before["serialized"] == after["serialized"] and before["viewport"] == after["viewport"]:
                return image, after
            time.sleep(.1)
        raise RuntimeError("Puzzle changed while capturing its frame")

    def execute(self, action):
        self._desktop().execute(action, self.state()["viewport"])
        time.sleep(.20)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.log:
            self.log.close()
