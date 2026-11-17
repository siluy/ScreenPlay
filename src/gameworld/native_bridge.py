"""Trusted in-process telemetry support. Never imported by the public action server."""
import json
import os
from pathlib import Path
import time

private = Path(os.environ["GAMEWORLD_PRIVATE_DIR"])
parameters = json.loads((private / "fixture.json").read_text())
processed = sequence = target = 0


def quota():
    global processed, sequence, target
    sequence, target = map(int, Path(os.environ["GAMEWORLD_CONTROL_FILE"]).read_text().split())
    if processed < target:
        processed += 1
        return True
    return False


def publish(**state):
    value = dict(session=os.environ["GAMEWORLD_SESSION"], pid=os.getpid(), captured_at=time.time(),
                 scenario=os.environ["GAMEWORLD_SCENARIO"], ready=True,
                 processed_updates=processed, control_sequence=sequence, frozen=processed >= target,
                 **state)
    path = Path(os.environ["GAMEWORLD_STATE_FILE"])
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value))
    temp.replace(path)
