"""Restricted map, vehicle and order panels over the original OpenTTD commands."""
from gameworld.build import ROOT
from gameworld.openttd import OpenTTDBackend
from .native_process import NativeTextProcess
from .structured import function


def game_tools():
    coordinate = {"type": "integer", "minimum": 1, "maximum": 62}
    return [
        function("open_panel", "Open one text panel; costs one decision.",
                 {"panel": {"type": "string", "enum": ["map", "vehicle", "orders", "road"]}}),
        function("click", "Activate one control of the current panel; unavailable controls are rejected.",
                 {"control": {"type": "string", "enum": ["start_stop", "send_to_depot", "turn_around",
                    "go_to", "delete_order", "toggle_full_load", "skip_order", "build_x", "build_y", "remove_x", "remove_y"]}}),
        function("select_order", "Select one displayed native order, or the displayed end-of-orders row.",
                 {"index": {"type": "integer", "minimum": 1}}),
        function("click_tile", "In orders/go_to mode, click one visible station to insert one order before the selection.",
                 {"x": coordinate, "y": coordinate}),
        function("draw_road", "One straight full-tile road drag with the selected X/Y build/remove tool; native costs and legality apply.",
                 {key: coordinate for key in ("x1", "y1", "x2", "y2")}),
        function("pan_map", "Center the bounded text map view on one map tile.", {"x": coordinate, "y": coordinate}),
        function("wait", "Advance the native simulation for a bounded duration.",
                 {"duration_ms": {"type": "integer", "minimum": 0, "maximum": 5000}}),
        function("finish", "End and evaluate the native route, bus, cash and infrastructure state."),
    ]


class OpenTTDText(NativeTextProcess):
    game_name = "OpenTTD"
    interface_profile = "openttd-restricted-panels-map-v0"
    input_updates = 8
    wait_quantum_ms = 30
    tools = staticmethod(game_tools)
    action_rules = (
        "Experimental restricted text panels; original OpenTTD commands, simulation and scoring. "
        "The map is a movable 25-by-13-tile text viewport, not an exact serialization of GUI pixel visibility. "
        "Map coordinates are native x/y, not screen directions. Road X joins x-1 and x+1; road Y joins y-1 and y+1. "
        "Choose a road tool before drawing one aligned full-tile segment. "
        "To add an order, select its insertion row (or end), click go_to, then click a station tile. "
        "Orders, selected rows and vehicle details are panel-local. No automatic route repair, route planning, "
        "visit history, goal progress, borrowing, vehicle purchasing, terrain or station construction is exposed. "
        "Ordinary actions consume eight updates; waits consume ceil(duration_ms/30); thinking is frozen. "
        "Invalid and ineffective actions consume a decision."
    )

    def __init__(self, task_id, condition="text-symbolic", max_decisions=None):
        super().__init__(task_id, condition, max_decisions)
        self._evaluator = OpenTTDBackend()
        self._evaluator.task = self.task
        binary = ROOT / "build/text_openttd/openttd-text"
        if not binary.exists():
            self.close()
            raise RuntimeError("Run scripts/build_text_remaining.py openttd first")
        for name in ("baseset", "lang"):
            (self.private / name).mkdir()
            for item in (ROOT / "build/openttd-native" / name).iterdir():
                (self.private / name / item.name).symlink_to(item)
        (self.private / "baseset/opengfx-8.0").symlink_to(ROOT / ".cache/assets/openttd/opengfx-8.0")
        config = self.private / "openttd.cfg"
        config.write_text("""[misc]
language = english.lng
[gui]
autosave_interval = 0
pause_on_newgame = false
show_finances = false
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
        self.launch([str(binary), "-c", str(config), "-X", "-x", "-g", "-G",
                     str(self.task.parameters.get("seed", 20260914)), "-r", "1024x640",
                     "-v", "null:ticks=100000000", "-s", "null", "-m", "null"], cwd=self.private)

