"""Shared lifecycle for native games with private, atomic state telemetry."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from .build import ROOT
from .desktop import PyAutoGUIDesktop
from .protocol import Wait


class NativeBackend:
    def __init__(self):
        self.process = self.log = self.desktop = None
        self.sequence = 0

    def start(self, task, private_dir: Path, session: str):
        if sys.platform != "darwin":
            raise RuntimeError("These native desktop adapters currently support macOS")
        self.task, self.session = task, session
        self.name = f"native_{task.package}"
        self.state_file = private_dir / "latest_state.json"
        self.control_file = private_dir / "advance.txt"
        self.control_file.write_text("-1 0\n" if task.package == "enigma" else "0 0\n")
        (private_dir / "fixture.json").write_text(json.dumps(task.parameters))
        if task.package == "endless_sky":
            if "native_fixture" in task.parameters:
                (private_dir / "fixture.txt").write_text(task.parameters["native_fixture"])
            (private_dir / "preferences.txt").write_text('"window size" 1100 720\nzoom 100\nfullscreen 0\n')
        receipt = ROOT / "build" / task.package / "build_receipt.json"
        if not receipt.exists():
            raise RuntimeError(f"Run screenplay build {task.package} first")
        built = json.loads(receipt.read_text())
        env = dict(os.environ, SCREENPLAY_SESSION=session, SCREENPLAY_SCENARIO=task.game_id,
                   SCREENPLAY_STATE_FILE=str(self.state_file), SCREENPLAY_CONTROL_FILE=str(self.control_file),
                   SCREENPLAY_PRIVATE_DIR=str(private_dir), SDL_VIDEO_WINDOW_POS="80,100",
                   PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT / ".cache/prepared" / task.package))
        self.log = (private_dir / "game_process.log").open("w")
        command = [part.format(private=str(private_dir), scenario=task.game_id) for part in built["command"]]
        if task.package == "enigma":
            # Execute the exact level copy retained with this episode's evidence.
            level = ROOT / "game_packages/enigma/levels" / f"{task.game_id}.xml"
            snapshot = private_dir / "level.xml"
            snapshot.write_bytes(level.read_bytes())
            command[-1] = str(snapshot)
        self.process = subprocess.Popen(command, cwd=built["cwd"], env=env,
                                        stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{task.game} exited; see {private_dir / 'game_process.log'}")
            if self.state_file.exists():
                state = self.state()
                if state.get("error"):
                    raise RuntimeError(state["error"])
                if state.get("ready"):
                    if state.get("success"):
                        raise RuntimeError("Initial fixture is already complete")
                    self.desktop = PyAutoGUIDesktop(self.process.pid)
                    if task.package == "enigma":
                        self.desktop.focus()
                        view = self.viewport()
                        self.desktop.gui.moveTo(view["x"] + 400, view["y"] + 292)
                        time.sleep(.2)
                        self.control_file.write_text("0 0\n")
                        arm_deadline = time.monotonic() + 3
                        while self.state()["control_sequence"] != 0:
                            if time.monotonic() > arm_deadline:
                                raise RuntimeError("Enigma input initialization was not acknowledged")
                            time.sleep(.02)
                        state = self.state()
                    self.initial_state = state
                    return state
            time.sleep(.05)
        raise RuntimeError(f"{task.game} did not become ready")

    def state(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Native game process is not running")
        value = json.loads(self.state_file.read_text())
        if value.get("session") != self.session or value.get("pid") != self.process.pid:
            raise RuntimeError("Native telemetry session mismatch")
        if time.time() - value["captured_at"] > 5:
            raise RuntimeError("Native telemetry is stale")
        return value

    def viewport(self):
        import Quartz
        windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        windows = [w for w in windows if w.get("kCGWindowOwnerPID") == self.process.pid
                   and w.get("kCGWindowLayer") == 0 and w["kCGWindowBounds"]["Width"] >= 300
                   and w["kCGWindowBounds"]["Height"] >= 200]
        if not windows:
            raise RuntimeError("Native game window is not visible")
        w = max(windows, key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
        b = w["kCGWindowBounds"]
        return {"x": round(b["X"]), "y": round(b["Y"]), "width": round(b["Width"]), "height": round(b["Height"])}

    def capture(self):
        self.desktop.focus()
        for _ in range(20):
            view = self.viewport()
            time.sleep(.10)
            if self.viewport() != view:
                continue
            before = self.state()
            if not before.get("frozen", True):
                raise RuntimeError("Native game is advancing during capture")
            image = self.desktop.capture(view)
            after = self.state()
            if self.viewport() == view and before.get("processed_updates") == after.get("processed_updates"):
                after["viewport"] = view
                return image, after
        raise RuntimeError("Native window did not settle for capture")

    def execute(self, action):
        before = self.state()
        if not isinstance(action, Wait):
            self.desktop.execute(action, self.viewport())
        if "max_updates" not in self.task.parameters:
            if isinstance(action, Wait):
                time.sleep(action.duration_ms / 1000)
            time.sleep(.20)
            return
        count = math.ceil(action.duration_ms / self.task.parameters.get("update_ms", 33)) if isinstance(action, Wait) else 6
        count = min(count, max(0, self.task.parameters["max_updates"] - before["processed_updates"]))
        self.sequence += 1
        target = before["processed_updates"] + count
        temp = self.control_file.with_suffix(".tmp")
        temp.write_text(f"{self.sequence} {target}\n")
        temp.replace(self.control_file)
        deadline = time.monotonic() + max(20, count * .15)
        while time.monotonic() < deadline:
            after = self.state()
            if after["control_sequence"] == self.sequence and after["processed_updates"] >= target and after["frozen"]:
                return {"updates": count, "native_time": after.get("native_time")}
            time.sleep(.025)
        raise RuntimeError("Native simulation advance was not acknowledged")

    def evaluate(self, state):
        violations = state.get("violations", [])
        success = bool(state.get("success")) and not violations and not state.get("lost", False)
        exhausted = "max_updates" in self.task.parameters and state["processed_updates"] >= self.task.parameters["max_updates"]
        return {"success": success, "score": float(success), "violations": violations,
                "progress": state.get("progress"), "evaluator": f"{self.task.package}-native-v1",
                "terminal_failure": bool(state.get("lost")) or (exhausted and not success),
                "failure_reason": "game_lost" if state.get("lost") else "simulation_budget_exhausted"}

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
