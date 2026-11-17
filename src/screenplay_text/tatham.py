"""Net and Untangle text observations, with every action executed by screenplay-engine."""
from __future__ import annotations

import copy
import math
import re

from screenplay.tasks import evaluate, load_task, parse_save
from screenplay.validation import engine_run
from .fifteen import FifteenText, tools as fifteen_tools


def game_tools(game: str, condition: str) -> list[dict]:
    if game in {"Endgame: Singularity", "OpenTTD", "Enigma"}:
        if condition != "text-symbolic":
            raise ValueError("Experimental adapters support text-symbolic only")
        from importlib import import_module
        module = {"Endgame: Singularity": "singularity", "OpenTTD": "openttd", "Enigma": "enigma"}[game]
        return import_module("screenplay_text." + module).game_tools()
    if game in {"PySolFC FreeCell", "Endless Sky"}:
        if condition != "text-symbolic":
            raise ValueError("This game supports text-symbolic only")
        if game == "PySolFC FreeCell":
            from .freecell import game_tools as selected_tools
        else:
            from .endless import game_tools as selected_tools
        return selected_tools()
    if game not in {"Net", "Untangle"} or condition != "text-symbolic":
        raise ValueError("Net and Untangle currently support text-symbolic only")
    integer = {"type": "integer", "minimum": 1}
    if game == "Net":
        specs = [
            ("rotate", "Rotate one unlocked cell by 90 degrees, as one native click.", {
                "row": integer, "column": integer,
                "direction": {"type": "string", "enum": ["clockwise", "counterclockwise"]}}),
            ("toggle_lock", "Toggle the visible lock of one cell, as one native middle click.",
             {"row": integer, "column": integer}),
        ]
    else:
        specs = [("move_node", "Drag from this node's current center to one pixel point. Native picking applies if nodes overlap.",
                  {"node": integer, "x": {"type": "integer", "minimum": 0},
                   "y": {"type": "integer", "minimum": 0}})]
    result = [{"type": "function", "function": {"name": name, "description": description,
               "parameters": {"type": "object", "properties": properties,
                              "required": list(properties), "additionalProperties": False}}}
              for name, description, properties in specs]
    return result + fifteen_tools("text-symbolic")[1:]


class NativeBoardText(FifteenText):
    def __init__(self, task_id: str, condition: str = "text-symbolic", max_decisions: int = 100):
        game_tools(self.game_name, condition)
        super().__init__(task_id, condition, max_decisions)

    def _refresh(self):
        self._native = engine_run({"game": self.task.game, "game_id": self.task.game_id},
                                  "\n".join(self._commands) or "status")
        entries = parse_save(self._native["serialized"])
        fields = dict(entries)
        self.viewport = self._native["size"]
        self._score = evaluate(self._native, self.task.expected_desc, self.task.game)
        if self._score["violations"]:
            raise RuntimeError("Native puzzle integrity violation")
        self._initial(fields["PARAMS"], fields["DESC"])
        transitions = [(k, v) for k, v in entries if k in {"MOVE", "SOLVE", "RESTART"}]
        position = int(fields["STATEPOS"]) - 1
        if not 0 <= position <= len(transitions):
            raise RuntimeError("Invalid native state position")
        for kind, value in transitions[:position]:
            if kind == "RESTART":
                self._initial(fields["PARAMS"], value)
            elif kind == "MOVE":
                self._move(value)
            else:
                raise RuntimeError("Solver state is prohibited")
        self._ui = fields.get("UI", "")

    def observe(self) -> dict:
        return {"task_id": self.task.task_id, "game": self.game_name, "condition": self.condition,
                "observation_id": self.decisions, "instruction": self.task.instruction,
                "rules": self.task.rules + " " + self.action_rules +
                " Undo, redo, restart, wait, finish, invalid and ineffective actions each cost one decision. "
                "Restart does not reset the decision budget.",
                "board_text": self.describe(), "budget_remaining": self.max_decisions - self.decisions,
                "receipt": copy.deepcopy(self.receipt), "ended": self.result is not None,
                "result": copy.deepcopy(self.result)}

    def _translate(self, action: dict) -> str | None:
        if not isinstance(action, dict):
            raise ValueError("Action must be an object")
        spec = next((s["function"]["parameters"] for s in game_tools(self.game_name, self.condition)
                     if s["function"]["name"] == action.get("type")), None)
        if spec is None or set(action) != {"type", *spec["required"]}:
            raise ValueError("Invalid action or fields")
        for key, prop in spec["properties"].items():
            if prop["type"] == "integer" and (type(action[key]) is not int or action[key] < prop["minimum"]):
                raise ValueError("Invalid integer argument")
            if "enum" in prop and action[key] not in prop["enum"]:
                raise ValueError("Invalid enum argument")
        if not spec["required"]:
            return {"undo": "input 0 0 117", "redo": "input 0 0 114",
                    "restart": "restart", "wait": None, "finish": None}[action["type"]]
        return self.translate_move(action)


class NetText(NativeBoardText):
    game_name = "Net"
    action_rules = ("Rows/columns are one-based. rotate changes one cell by exactly 90 degrees: "
                    "clockwise corresponds to a right click; counterclockwise to a left click. "
                    "toggle_lock corresponds to one middle click. Locked cells do not rotate.")

    def _initial(self, params: str, desc: str):
        match = re.fullmatch(r"(\d+)x(\d+)(w?)", params)
        if match is None:
            raise RuntimeError("Unsupported Net parameters")
        self.width, self.height = int(match[1]), int(match[2])
        self.wrapping = bool(match[3])
        tokens = re.findall(r"([0-9a-fA-F])([hv]*)", desc)
        if "".join(a+b for a,b in tokens) != desc or len(tokens) != self.width * self.height:
            raise RuntimeError("Invalid Net descriptor")
        self.tiles = [int(a, 16) for a, _ in tokens]
        self.barriers = [0] * len(tokens)
        for i, (_, flags) in enumerate(tokens):
            x, y = i % self.width, i // self.width
            if "v" in flags:
                self.barriers[i] |= 1
                self.barriers[y*self.width+(x+1) % self.width] |= 4
            if "h" in flags:
                self.barriers[i] |= 8
                self.barriers[((y+1) % self.height)*self.width+x] |= 2
        if not self.wrapping:
            for y in range(self.height):
                self.barriers[y*self.width] |= 4
                self.barriers[(y+1)*self.width-1] |= 1
            for x in range(self.width):
                self.barriers[x] |= 2
                self.barriers[(self.height-1)*self.width+x] |= 8
        if self.viewport != [32*self.width+33, 32*self.height+33]:
            raise RuntimeError("Unexpected Net native geometry")

    def _move(self, value: str):
        tokens = re.findall(r"([ACFL])(\d+),(\d+);?", value)
        if not tokens or "".join(f"{a}{x},{y};" for a,x,y in tokens).rstrip(";") != value.rstrip(";"):
            raise RuntimeError("Unsupported native Net move")
        for operation, x, y in tokens:
            x, y = int(x), int(y)
            if not (0 <= x < self.width and 0 <= y < self.height):
                raise RuntimeError("Invalid native Net coordinate")
            i = y*self.width+x; tile = self.tiles[i]
            self.tiles[i] = {"A": ((tile & 7) << 1) | ((tile & 8) >> 3),
                             "C": ((tile & 14) >> 1) | ((tile & 1) << 3),
                             "F": ((tile & 12) >> 2) | ((tile & 3) << 2),
                             "L": tile ^ 16}[operation]

    def describe(self) -> str:
        center = re.search(r"C(\d+),(\d+)", self._ui)
        cx, cy = (int(center[1]), int(center[2])) if center else (self.width//2, self.height//2)
        lines = [f"Net board: {self.height} rows, {self.width} columns. Rows top-to-bottom; columns left-to-right.",
                 "Directions are U=up, R=right, D=down, L=left. Wire ends and barriers are current visible geometry.",
                 f"Power source: row {cy+1}, column {cx+1}.",
                 "Opposite board edges wrap around." if self.wrapping else "Board edges do not wrap; outward connections are blocked."]
        for i, tile in enumerate(self.tiles):
            ends = "".join(name for bit,name in [(2,"U"),(1,"R"),(8,"D"),(4,"L")] if tile & bit) or "none"
            barriers = "".join(name for bit,name in [(2,"U"),(1,"R"),(8,"D"),(4,"L")] if self.barriers[i] & bit) or "none"
            lines.append(f"Cell ({i//self.width+1},{i%self.width+1}): wire ends {ends}; barriers {barriers}; locked {'yes' if tile & 16 else 'no'}.")
        return "\n".join(lines)

    def translate_move(self, action: dict) -> str:
        row, column = action["row"], action["column"]
        if not (1 <= row <= self.height and 1 <= column <= self.width):
            raise ValueError("Cell outside board")
        button = 513 if action["type"] == "toggle_lock" else 514 if action["direction"] == "clockwise" else 512
        x, y = column*32, row*32
        return f"input {x} {y} {button}\ninput {x} {y} {button+6}"


class UntangleText(NativeBoardText):
    game_name = "Untangle"
    action_rules = ("Node IDs are stable one-based labels for this text condition. Pixel origin is top-left. "
                    "move_node drags from the selected node's current center to (x,y), as one native drag. "
                    "If nodes overlap, native picking selects the lowest-numbered node at the shared center; "
                    "there is no automatic disambiguation. No crossing list or solution layout is supplied.")

    def _initial(self, params: str, desc: str):
        if not params.isdigit():
            raise RuntimeError("Unsupported Untangle parameters")
        self.node_count = int(params)
        side = math.isqrt(3*self.node_count)*64
        if self.viewport != [side, side]:
            raise RuntimeError("Unexpected Untangle native geometry")
        radius, center = side*3//7, side//2
        self.points = [(int(center+radius*math.sin(i*2*math.pi/self.node_count)+.5),
                        int(center-radius*math.cos(i*2*math.pi/self.node_count)+.5))
                       for i in range(self.node_count)]
        self.edges = [tuple(map(int, pair.split("-"))) for pair in desc.split(",")]
        if any(not (0 <= a < b < self.node_count) for a,b in self.edges):
            raise RuntimeError("Invalid native graph")

    def _move(self, value: str):
        tokens = re.findall(r"P(\d+):(\d+),(\d+)/(\d+);?", value)
        if not tokens or ";".join(f"P{i}:{x},{y}/{d}" for i,x,y,d in tokens) != value.rstrip(";"):
            raise RuntimeError("Unsupported native Untangle move")
        for node,x,y,denominator in tokens:
            node,x,y,denominator = map(int,(node,x,y,denominator))
            if not 0 <= node < self.node_count or denominator <= 0:
                raise RuntimeError("Invalid native node coordinate")
            self.points[node] = (x*64//denominator, y*64//denominator)

    def describe(self) -> str:
        lines = [f"Untangle canvas: {self.viewport[0]} by {self.viewport[1]} pixels; x increases rightward, y downward.",
                 "The following stable labels and exact edge endpoints are an ideal structural transcription; they are not a proposed solution."]
        lines += [f"Node {i+1}: x={x}, y={y}." for i,(x,y) in enumerate(self.points)]
        lines.append("Edges (undirected): " + ", ".join(f"{a+1}-{b+1}" for a,b in self.edges) + ".")
        return "\n".join(lines)

    def translate_move(self, action: dict) -> str:
        node, x, y = action["node"], action["x"], action["y"]
        if not (1 <= node <= self.node_count and x < self.viewport[0] and y < self.viewport[1]):
            raise ValueError("Node or target outside canvas")
        sx, sy = self.points[node-1]
        return f"input {sx} {sy} 512\ninput {x} {y} 515\ninput {x} {y} 518"


def make_environment(task_id: str, condition: str = "text-symbolic", max_decisions: int | None = None):
    game = load_task(task_id).game
    if game in {"Endgame: Singularity", "OpenTTD", "Enigma"}:
        from importlib import import_module
        module, name = {"Endgame: Singularity": ("singularity", "SingularityText"),
                        "OpenTTD": ("openttd", "OpenTTDText"), "Enigma": ("enigma", "EnigmaText")}[game]
        return getattr(import_module("screenplay_text." + module), name)(task_id, condition, max_decisions)
    if max_decisions is None:
        max_decisions = 100
    if game == "PySolFC FreeCell":
        from .freecell import FreeCellText
        return FreeCellText(task_id, condition, max_decisions)
    if game == "Endless Sky":
        from .endless import EndlessText
        return EndlessText(task_id, condition, max_decisions)
    cls = {"Fifteen": FifteenText, "Net": NetText, "Untangle": UntangleText}.get(game)
    if cls is None:
        raise ValueError("Unsupported text game")
    return cls(task_id, condition, max_decisions)
