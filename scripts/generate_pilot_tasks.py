"""Author deterministic development fixtures; reference actions are not agent rollouts."""
from pathlib import Path
import json
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gameworld.tasks import parse_save


def fifteen(scramble: int, seed: int):
    board = list(range(1, 9)) + [0]
    rng = random.Random(seed)
    blank, previous = 8, None
    undo = []
    for _ in range(scramble):
        choices = [p for p in range(9) if abs(p//3-blank//3)+abs(p%3-blank%3) == 1 and p != previous]
        target = rng.choice(choices)
        undo.append(blank)
        board[blank], board[target] = board[target], board[blank]
        previous, blank = blank, target
    actions = [{"type": "click", "x": 48 + (p % 3)*48, "y": 48 + (p//3)*48} for p in reversed(undo)]
    return ",".join(map(str, board)), actions


tasks = {}
for n, seed in [(1, 7), (12, 17), (24, 31)]:
    desc, actions = fifteen(n, seed)
    tasks[f"fifteen-{n:02d}"] = {
        "game": "Fifteen", "game_id": "3x3:"+desc,
        "instruction": "Arrange the numbered tiles in ascending row-major order, with the empty cell at bottom right.",
        "rules": "Click a tile in the same row or column as the gap to slide it. Undo and restart are allowed. Solve and changing the puzzle are prohibited.",
        "max_decisions": 200, "expected_desc": desc,
        "reference": {"provenance": "fixture-author inverse legal scramble; not an autonomous agent trajectory", "actions": actions},
    }
for name, configurations, rules, instruction in [
    ("Net", [("3x3",42), ("5x5",43), ("7x7",44)],
     "Rotate tiles with left/right click to connect all wires to the central power source. No wires may end without a matching connection. Middle click locks a tile. Undo is allowed; Solve and changing the puzzle are prohibited.",
     "Rotate the wire tiles until the entire network is connected with no dangling ends."),
    ("Untangle", [("6",42), ("10",43), ("15",44)],
     "Drag circular nodes to move them. Remove every crossing between edges. Undo is allowed; Solve and changing the puzzle are prohibited.",
     "Reposition the nodes so that no two edges cross."),
]:
    for params, seed in configurations:
        tasks[f"{name.lower()}-{params}"] = {"game":name,"game_id":f"{params}#{seed}",
            "instruction":instruction,"rules":rules,"max_decisions":400}

engine = ROOT / "build/tatham/bin/gw-engine"
for task in tasks.values():
    result = subprocess.run([str(engine),task["game"],task["game_id"]],input="save\n",text=True,check=True,capture_output=True)
    save = result.stdout.split("SAVE_BEGIN\n",1)[1].split("SAVE_END",1)[0]
    task["expected_desc"] = dict(parse_save(save))["DESC"]
(ROOT / "game_packages/tatham/tasks.json").write_text(json.dumps(tasks,indent=2)+"\n")
print(f"Wrote {len(tasks)} development fixtures in one upstream family")
# The v1 curriculum owns the complete 15-task family and native reference replay.
subprocess.run([sys.executable, str(ROOT / 'scripts/author_puzzles_expansion.py')], check=True)
