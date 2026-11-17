"""Check native Cocoa startup/rendering and telemetry; does NOT test PyAutoGUI."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from gameworld.tatham import TathamBackend
from gameworld.tasks import catalog, load_task, evaluate
from gameworld.desktop import permissions

artifacts=ROOT/"artifacts/native-initial-frames"
artifacts.mkdir(parents=True,exist_ok=True)
results=[]
try:
    for name in catalog():
        if catalog()[name]["package"] != "tatham": continue
        run_id="native-"+uuid.uuid4().hex
        private=ROOT/"runs"/run_id/"private"
        private.mkdir(parents=True)
        frame=artifacts/(name+".png")
        if frame.exists(): frame.unlink()
        os.environ["GAMEWORLD_RENDER_FILE"]=str(frame)
        backend=TathamBackend()
        try:
            task=load_task(name)
            state=backend.start(task,private,run_id)
            deadline=time.monotonic()+3
            while not frame.exists() and time.monotonic()<deadline: time.sleep(.05)
            with Image.open(frame) as image:
                width,height=image.size
                nonblank=len(image.convert("RGB").getcolors(maxcolors=1_000_000) or [])>2
            score=evaluate(state,backend.initial_desc,task.game)
            results.append({"task":name,"passed":nonblank and not score["success"],
                "frame":str(frame.relative_to(ROOT)),"render_size":[width,height],
                "viewport":state["viewport"],"score":score["score"]})
        finally:
            backend.close()
finally:
    os.environ.pop("GAMEWORLD_RENDER_FILE",None)
report={"created_at":datetime.now(timezone.utc).isoformat(),"passed":all(r["passed"] for r in results),
        "scope":"original Cocoa frontend launch, own render buffer and read-only native state; not desktop screenshot/input validation",
        "permissions":permissions(),"results":results}
(ROOT/"artifacts/native-smoke.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
