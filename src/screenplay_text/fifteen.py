"""Visible-board text observations backed by the original Fifteen engine.

The trusted host replays accepted inputs in screenplay-engine. The evaluated policy sees
only the observation and a restricted action schema, never saves or engine commands.
No desktop window, screenshot, solver, or network request is used here.
"""
from __future__ import annotations

import copy
import json
import re

from screenplay.tasks import catalog, evaluate, load_task, parse_save
from screenplay.validation import engine_run


CONDITIONS = ("text-symbolic", "text-coordinate")


def task_ids() -> list[str]:
    return sorted(k for k, v in catalog().items() if v["game"] == "Fifteen")


def tools(condition: str, game: str = "Fifteen") -> list[dict]:
    if game != "Fifteen":
        from .tatham import game_tools
        return game_tools(game, condition)
    if condition not in CONDITIONS:
        raise ValueError("Unknown text condition")
    if condition == "text-symbolic":
        name, description = "slide", "Click one cell, using one-based row and column. An aligned run slides toward the blank."
        properties = {k: {"type": "integer", "minimum": 1} for k in ("row", "column")}
    else:
        name, description = "click", "Left-click one point in the board viewport, using pixel x and y."
        properties = {k: {"type": "integer", "minimum": 0} for k in ("x", "y")}
    specs = [(name, description, properties)] + [
        ("undo", "Undo one native move, without refunding the decision budget.", {}),
        ("redo", "Redo one undone native move, without refunding the decision budget.", {}),
        ("restart", "Restore this puzzle's initial board, without resetting the decision budget.", {}),
        ("wait", "Leave the board unchanged and consume one decision.", {}),
        ("finish", "End the attempt and evaluate the current native state.", {}),
    ]
    return [{"type": "function", "function": {"name": n, "description": d,
             "parameters": {"type": "object", "properties": p,
                            "required": list(p), "additionalProperties": False}}}
            for n, d, p in specs]


class FifteenText:
    game_name = "Fifteen"

    def __init__(self, task_id: str, condition: str = "text-symbolic", max_decisions: int = 100):
        if condition not in CONDITIONS:
            raise ValueError("Unknown text condition")
        if type(max_decisions) is not int or max_decisions < 1:
            raise ValueError("max_decisions must be a positive integer")
        self.task = load_task(task_id)
        if self.task.game != self.game_name:
            raise ValueError("Wrong game for this adapter")
        self.condition, self.max_decisions = condition, max_decisions
        self._commands: list[str] = []
        self.decisions = 0
        self.receipt = None
        self.result = None
        self._refresh()
        if self._score["success"]:
            raise RuntimeError("Initial board must not be solved")

    def _refresh(self):
        # Running a fresh headless engine avoids persistent children and shares no
        # mutable state, locks, or desktop resources with the active GUI experiment.
        self._native = engine_run({"game": self.task.game, "game_id": self.task.game_id},
                                  "\n".join(self._commands) or "status")
        entries = parse_save(self._native["serialized"])
        fields = dict(entries)
        match = re.fullmatch(r"(\d+)x(\d+)", fields["PARAMS"])
        if match is None:
            raise RuntimeError("Unsupported native board dimensions")
        self.width, self.height = map(int, match.groups())
        self.board = list(map(int, fields["DESC"].split(",")))
        transitions = [(k, v) for k, v in entries if k in {"MOVE", "SOLVE", "RESTART"}]
        position = int(fields["STATEPOS"]) - 1
        if not 0 <= position <= len(transitions):
            raise RuntimeError("Invalid native state position")
        for kind, value in transitions[:position]:
            if kind == "RESTART":
                self.board = list(map(int, value.split(",")))
                continue
            move = re.fullmatch(r"M(\d+),(\d+)", value) if kind == "MOVE" else None
            if move is None:
                raise RuntimeError("Unexpected native transition; never expose solver state")
            x, y = map(int, move.groups())
            gap, target = self.board.index(0), y * self.width + x
            if not (0 <= x < self.width and 0 <= y < self.height) or gap == target:
                raise RuntimeError("Invalid native move")
            if gap // self.width != y and gap % self.width != x:
                raise RuntimeError("Native move is not aligned with the gap")
            step = (1 if target > gap else -1) * (self.width if gap % self.width == x else 1)
            for index in range(gap, target, step):
                self.board[index] = self.board[index + step]
            self.board[target] = 0
        if sorted(self.board) != list(range(self.width * self.height)):
            raise RuntimeError("Invalid board recovered from native save")
        self._score = evaluate(self._native, self.task.expected_desc, self.task.game)
        self.viewport = self._native["size"]
        sx, sy = self.viewport[0] // (self.width + 1), self.viewport[1] // (self.height + 1)
        if sx != sy or sx * (self.width + 1) != self.viewport[0] or sy * (self.height + 1) != self.viewport[1]:
            raise RuntimeError("Unexpected native tile geometry")
        self.tile_size = sx

    def observe(self) -> dict:
        rows = [self.board[i:i + self.width] for i in range(0, len(self.board), self.width)]
        lines = [f"The board has {self.height} rows and {self.width} columns.",
                 "Rows run top to bottom; columns run left to right. 'blank' is the empty cell."]
        lines += [f"Row {i}: " + ", ".join(str(x) if x else "blank" for x in row)
                  for i, row in enumerate(rows, 1)]
        rules = self.task.rules + " One aligned click can slide multiple tiles; it costs one decision."
        if self.condition == "text-symbolic":
            rules += " Choose one cell with slide(row, column), using one-based indices."
        else:
            lines += [f"Viewport: {self.viewport[0]} by {self.viewport[1]} pixels; origin at top left.",
                      f"Cell (row r, column c), using one-based indices, has center "
                      f"(x={self.tile_size}*c, y={self.tile_size}*r); tile size {self.tile_size} pixels."]
            rules += " Choose one viewport point with click(x, y)."
        rules += " Invalid or ineffective actions, undo, redo, restart, wait, and finish each consume one decision."
        return {"task_id": self.task.task_id, "condition": self.condition,
                "observation_id": self.decisions, "instruction": self.task.instruction,
                "rules": rules, "board_text": "\n".join(lines),
                "budget_remaining": self.max_decisions - self.decisions,
                "receipt": copy.deepcopy(self.receipt), "ended": self.result is not None,
                "result": copy.deepcopy(self.result)}

    def _translate(self, action: dict) -> str | None:
        if not isinstance(action, dict):
            raise ValueError("Action must be an object")
        kind = action.get("type")
        spec = next((s["function"]["parameters"] for s in tools(self.condition)
                     if s["function"]["name"] == kind), None)
        if spec is None or set(action) != {"type", *spec["required"]}:
            raise ValueError("Invalid action or fields")
        if any(type(action[k]) is not int for k in spec["required"]):
            raise ValueError("Coordinates must be integers")
        if kind == "slide":
            row, column = action["row"], action["column"]
            if not (1 <= row <= self.height and 1 <= column <= self.width):
                raise ValueError("Cell outside board")
            x, y = column * self.tile_size, row * self.tile_size
        elif kind == "click":
            x, y = action["x"], action["y"]
            if not (0 <= x < self.viewport[0] and 0 <= y < self.viewport[1]):
                raise ValueError("Point outside viewport")
        else:
            return {"undo": "input 0 0 117", "redo": "input 0 0 114",
                    "restart": "restart", "wait": None, "finish": None}[kind]
        return f"input {x} {y} 512\ninput {x} {y} 518"

    def step(self, action: dict) -> dict:
        if self.result is not None:
            raise RuntimeError("Episode has ended")
        self.decisions += 1
        valid = True
        try:
            command = self._translate(action)
        except ValueError:
            valid = False
            self.receipt = {"status": "rejected", "error": "invalid_action"}
        else:
            if command is not None:
                self._commands.append(command)
                self._refresh()
            self.receipt = {"status": "executed"}
        reason = ("success" if self._score["success"] else
                  "agent_finished" if valid and action["type"] == "finish" else
                  "decision_budget_exhausted" if self.decisions >= self.max_decisions else None)
        if reason:
            self.result = {"success": self._score["success"], "score": self._score["score"],
                           "stop_reason": reason, "decisions": self.decisions,
                           "evaluator": self._score["evaluator"]}
        return self.observe()


def build_request(turns: list[dict], current: dict, *, window: int = 5) -> dict:
    """Provider-neutral request; add model/provider generation settings outside it.

    A turn contains observation, assistant (original full message), and receipt.
    Only the board descriptions age out. Text/actions/receipts/reasoning stay intact.
    """
    if type(window) is not int or window < 1:
        raise ValueError("window must be a positive integer including the current board")
    messages = [{"role": "system", "content":
                 "Solve the game using only the supplied text observations and listed actions. "
                 "Submit exactly one action per decision. Inspect the resulting board and receipt. "
                 "No solver, code execution, files, external tools, or batched action sequences are available. "
                 "Finish only when you believe the goal is satisfied."}]
    for index, turn in enumerate(turns):
        observation = copy.deepcopy(turn["observation"])
        if index < len(turns) - (window - 1):
            observation["board_text"] = "[Older board omitted by the observation-window policy.]"
        messages.append({"role": "user", "content": json.dumps(observation, ensure_ascii=False)})
        assistant = copy.deepcopy(turn["assistant"])
        messages.append(assistant)
        for call in assistant.get("tool_calls") or []:
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(turn["receipt"], ensure_ascii=False)})
    messages.append({"role": "user", "content": json.dumps(current, ensure_ascii=False)})
    return {"messages": messages, "tools": tools(current["condition"], current.get("game", "Fifteen")),
            "tool_choice": "required", "parallel_tool_calls": False, "stream": False, "n": 1}
