"""Text serialization of the original Singularity dialogs, not a strategy API."""
import os
import sys

from screenplay.build import ROOT
from .native_process import NativeTextProcess
from .structured import function


def game_tools():
    control = {"type": "string"}
    return [
        function("click", "Activate one listed visible button or list row.", {"control": control}),
        function("set_value", "Set one visible slider to a value in its displayed range; one native slider callback.",
                 {"control": control, "value": {"type": "integer", "minimum": 0}}),
        function("type_text", "Replace one visible text entry (e.g. a base name); does not confirm the dialog.",
                 {"control": control, "text": {"type": "string"}}),
        function("wait", "Spend update opportunities; only the map advances game time, at the selected speed.",
                 {"duration_ms": {"type": "integer", "minimum": 0, "maximum": 5000}}),
        function("finish", "End and evaluate the current native state."),
    ]


class SingularityText(NativeTextProcess):
    game_name = "Endgame: Singularity"
    interface_profile = "singularity-native-visible-widgets-v0"
    tools = staticmethod(game_tools)
    action_rules = (
        "Experimental text interface: only the active native dialog's visible text and controls are listed. "
        "Control IDs belong to the current observation. Select rows, scroll and confirm dialogs separately. "
        "Slider values are exact integers; type_text replaces one entry. No adapter-supplied research planning, "
        "prerequisite completion, construction sequence or wait-until-complete. The original Auto-build items "
        "button and its confirmation are retained. Menu/save/load/quit/debug controls are unavailable. "
        "Each ordinary input consumes six update opportunities; wait consumes ceil(duration_ms/33). "
        "Time advances only on the map and at the selected game speed. Thinking is frozen. "
        "Invalid actions consume a decision."
    )

    def __init__(self, task_id, condition="text-symbolic", max_decisions=None):
        super().__init__(task_id, condition, max_decisions)
        prepared = ROOT / ".cache/prepared/singularity"
        self.launch([sys.executable, str(ROOT / "research/text-ablation/native/singularity_text.py")],
                    extra_env={"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
                               "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(prepared)])})

