"""Native OpenTTD backend. State and simulation controls stay on the trusted side."""
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


def binary_path() -> Path:
    return ROOT / "build/openttd-native/openttd"


class OpenTTDBackend:
    name = "native_openttd_cocoa"

    def __init__(self):
        self.process = None
        self.log = None
        self.desktop = None
        self.control_sequence = 0

    def start(self, task, private_dir: Path, session: str):
        if sys.platform != "darwin":
            raise RuntimeError("The OpenTTD desktop adapter currently supports macOS")
        binary = binary_path()
        if not binary.exists():
            raise RuntimeError("Run screenplay build openttd first")
        self.task, self.session = task, session
        (private_dir / "fixture.json").write_text(json.dumps(task.parameters))
        self.state_file = private_dir / "latest_state.json"
        self.control_file = private_dir / "advance.txt"
        self.control_file.write_text("0 0\n")
        config = private_dir / "openttd.cfg"
        config.write_text("""[misc]
language = english.lng
display_opt = SHOW_TOWN_NAMES|SHOW_STATION_NAMES|SHOW_SIGNS|FULL_ANIMATION|FULL_DETAIL|WAYPOINTS
[gui]
autosave_interval = 0
pause_on_newgame = false
show_finances = false
new_nonstop = false
right_mouse_btn_emulation = false
[game_creation]
map_x = 6
map_y = 6
starting_year = 1950
se_flat_world_height = 1
landscape = temperate
[difficulty]
vehicle_breakdowns = 0
disasters = false
max_no_competitors = 0
[economy]
inflation = false
town_growth_rate = 0
[locale]
currency = GBP
[graphicsset]
name = OpenGFX
""")
        # -c makes this directory the personal directory; -X excludes global paths.
        for dirname, source in [("baseset", ROOT / "build/openttd-native/baseset"),
                                 ("lang", ROOT / "build/openttd-native/lang")]:
            destination = private_dir / dirname
            destination.mkdir(exist_ok=True)
            if source.is_dir():
                for item in source.iterdir():
                    target = destination / item.name
                    if not target.exists(): target.symlink_to(item)
        gfx = private_dir / "baseset/opengfx-8.0"
        gfx.symlink_to(ROOT / ".cache/assets/openttd/opengfx-8.0", target_is_directory=True)
        env = dict(os.environ, SCREENPLAY_PRIVATE_DIR=str(private_dir), SCREENPLAY_SESSION=session, SCREENPLAY_SCENARIO=task.game_id,
                   SCREENPLAY_STATE_FILE=str(self.state_file), SCREENPLAY_CONTROL_FILE=str(self.control_file))
        self.log = (private_dir / "game_process.log").open("w")
        self.process = subprocess.Popen([str(binary), "-c", str(config), "-X", "-x", "-g",
            "-G", str(task.parameters.get("seed", 20260914)), "-r", "1024x640", "-v", "cocoa:no_threads", "-s", "null", "-m", "null"],
            cwd=private_dir, env=env, stdout=self.log, stderr=self.log)
        (private_dir / "process.json").write_text(json.dumps({"pid": self.process.pid, "session": session}) + "\n")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"OpenTTD exited during startup; see {private_dir / 'game_process.log'}")
            if self.state_file.exists():
                state = self.state()
                if state.get("error"):
                    raise RuntimeError("OpenTTD fixture setup: " + state["error"])
                if state.get("ready"):
                    if state["scenario"] != task.game_id or state["map_size"] != [64,64]:
                        raise RuntimeError("OpenTTD initialized the wrong scenario")
                    if state["visited_west"] or state["visited_east"] or not state["bus"]["stopped"]:
                        raise RuntimeError("OpenTTD initial bus state is invalid")
                    self.initial_state = state
                    self.desktop = PyAutoGUIDesktop(self.process.pid)
                    # Native fixture readiness can precede Quartz registering
                    # the Cocoa window during a rapid cross-game reset.
                    window_deadline = time.monotonic() + 5
                    while True:
                        try:
                            self.viewport()
                            break
                        except RuntimeError:
                            if time.monotonic() >= window_deadline:
                                raise
                            time.sleep(.05)
                    return state
            time.sleep(.1)
        raise RuntimeError("OpenTTD fixture did not become ready within 30 seconds")

    def state(self) -> dict:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("OpenTTD process is not running")
        state = json.loads(self.state_file.read_text())
        if state.get("session") != self.session or state.get("pid") != self.process.pid:
            raise RuntimeError("OpenTTD telemetry session mismatch")
        if time.time() - state["captured_at"] > 3:
            raise RuntimeError("OpenTTD telemetry is stale")
        return state

    def viewport(self) -> dict:
        import Quartz
        windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,
                                                   Quartz.kCGNullWindowID)
        candidates = [w for w in windows if w.get("kCGWindowOwnerPID") == self.process.pid
                      and w.get("kCGWindowLayer", 0) == 0 and w["kCGWindowBounds"]["Width"] > 300]
        if not candidates:
            raise RuntimeError("OpenTTD native window not found")
        bounds = max(candidates, key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])["kCGWindowBounds"]
        return {"x": bounds["X"], "y": bounds["Y"], "width": bounds["Width"], "height": bounds["Height"]}

    def capture(self):
        self.desktop.focus()
        # WindowServer reports intermediate bounds during macOS opening animations.
        # Wait for actual geometry; do not scale a partially cropped screenshot.
        for _ in range(3):
            view = self.viewport()
            stable_since = time.monotonic()
            deadline = stable_since + 3
            while time.monotonic() < deadline:
                time.sleep(.03)
                current = self.viewport()
                if current != view:
                    view, stable_since = current, time.monotonic()
                elif time.monotonic() - stable_since >= .15:
                    break
            else:
                raise RuntimeError("OpenTTD window geometry did not settle")
            before = self.state()
            if not before["frozen"]:
                raise RuntimeError("Cannot capture while the OpenTTD simulation is advancing")
            image = self.desktop.capture(view)
            after = self.state()
            if before["native_tick"] != after["native_tick"] or not after["frozen"]:
                raise RuntimeError("OpenTTD simulation advanced during screenshot capture")
            if self.viewport() == view:
                after["viewport"] = view
                return image, after
        raise RuntimeError("OpenTTD window moved while capturing its frame")

    def execute(self, action):
        before = self.state()
        if isinstance(action, Wait):
            count = math.ceil(action.duration_ms / 30)
        else:
            self.desktop.execute(action, self.viewport())
            count = 8
        count = min(count, max(0, self.task.parameters["max_updates"] - before["processed_updates"]))
        self.control_sequence += 1
        target = before["processed_updates"] + count
        temporary = self.control_file.with_suffix(".tmp")
        temporary.write_text(f"{self.control_sequence} {target}\n")
        temporary.replace(self.control_file)
        deadline = time.monotonic() + max(15, count * .10)
        while time.monotonic() < deadline:
            after = self.state()
            if after["control_sequence"] == self.control_sequence and after["processed_updates"] >= target and after["frozen"]:
                return {"updates": count, "native_ticks": after["native_tick"]-before["native_tick"],
                        "native_tick_after": after["native_tick"]}
            time.sleep(.025)
        raise RuntimeError("OpenTTD did not acknowledge the requested simulation advance")

    def evaluate(self, state):
        violations = []
        if state["reset_violation"]: violations.append("forbidden_game_switch")
        if not state["company_present"]: violations.append("company_removed")
        if not state["bus_present"]: violations.append("inspection_bus_removed")
        if not state["stations_present"]: violations.append("required_stop_removed")
        if state.get("loan_violation"): violations.append("loan_taken")
        if state.get("min_cash",0) < self.task.parameters["cash_floor"]: violations.append("cash_floor_violated")
        if state.get("bus",{}).get("crashed"): violations.append("bus_crashed")
        goal = self.task.parameters["goal"]
        conditions = [state["missing_road_sections"] == 0, state["visited_west"], state["visited_east"]]
        if goal.get("central"): conditions.append(state["visited_central"])
        if "orders" in goal: conditions.append(state.get("orders") == goal["orders"])
        if goal.get("normal_loading"): conditions.append(state.get("normal_loading", False))
        if goal.get("stopped"): conditions.append(state.get("bus", {}).get("stopped", False))
        if goal.get("depot"): conditions.append(state.get("in_depot", False))
        success = all(conditions) and not violations
        return {"success": success, "score": float(success), "violations": violations,
            "progress": sum(map(int, conditions))/len(conditions),
            "terminal_failure": state["processed_updates"] >= self.task.parameters["max_updates"] and not success,
            "failure_reason": "simulation_budget_exhausted", "evaluator": "openttd-native-route-v2"}

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=3)
        if self.log: self.log.close()
