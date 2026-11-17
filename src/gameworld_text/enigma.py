"""Visible-board text and bounded mouse impulses over Enigma's native physics."""
from gameworld.build import ROOT
from .native_process import NativeTextProcess
from .structured import function


def game_tools():
    impulse = {"type": "integer", "minimum": -300, "maximum": 300}
    return [
        function("push", "One relative native mouse-motion impulse. dx is rightward, dy downward; it is not a target position or path.",
                 {"dx": impulse, "dy": impulse}),
        function("activate_item", "Activate the first inventory item, as one left mouse-button press."),
        function("rotate_inventory", "Rotate inventory once, as one right mouse-button press."),
        function("wait", "Advance native inertia, collisions and animations without adding mouse force.",
                 {"duration_ms": {"type": "integer", "minimum": 0, "maximum": 5000}}),
        function("finish", "End and evaluate the native level-completion and survival flags."),
    ]


class EnigmaText(NativeTextProcess):
    game_name = "Enigma"
    interface_profile = "enigma-visible-board-impulses-v0"
    tools = staticmethod(game_tools)
    action_rules = (
        "Experimental text interface to the original Enigma physics. The current 20-by-13 board is described "
        "with zero-based tile coordinates; centers are (x+0.5,y+0.5). Marble position is rounded to 0.01 tile. "
        "push(dx,dy) adds one native mouse-motion impulse, scaled by the game's mouse sensitivity. "
        "It does not move to a destination, brake automatically, find paths, click objects or open gates. "
        "Ordinary inputs consume six 10-ms updates; wait consumes ceil(duration_ms/10). Thinking is frozen. "
        "Closed oxyd colors and switch/key target links are hidden. Colors remain masked during the first "
        "0.5 seconds of opening; no memory of closed colors is supplied. "
        "Only visible key shapes and current switch/door states are described. "
        "Inventory controls are native. Reset, solver, level switching and mouse-sensitivity changes are unavailable. "
        "Invalid and ineffective actions consume a decision."
    )

    def __init__(self, task_id, condition="text-symbolic", max_decisions=None):
        super().__init__(task_id, condition, max_decisions)
        binary = ROOT / "build/text_enigma/enigma-text"
        if not binary.exists():
            self.close()
            raise RuntimeError("Run scripts/build_text_remaining.py enigma first")
        prepared = ROOT / ".cache/prepared/enigma"
        level = ROOT / "game_packages/enigma/levels" / (self.task.game_id + ".xml")
        (self.private / "level.xml").write_bytes(level.read_bytes())
        self.launch([str(binary), "--window", "--nograb", "--log", "--nosound", "--robinson", "--lang", "en",
                     "--data", str(prepared / "data"), "--pref", str(self.private), str(self.private / "level.xml")],
                    cwd=prepared, extra_env={"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"})

