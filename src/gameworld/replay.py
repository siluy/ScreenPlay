"""A self-contained replay with images and executed public actions only."""
import base64
import html
import json
from pathlib import Path


def export_replay(directory: Path) -> Path:
    rows = []
    interactions = directory / "interactions.jsonl"
    by_frame = {}
    if interactions.exists():
        for line in interactions.read_text().splitlines():
            row = json.loads(line)
            by_frame[row["frame_before"]] = row
    for frame in sorted((directory / "frames").glob("*.png")):
        row = by_frame.get("frames/" + frame.name, {})
        rows.append({"name": frame.stem, "image": base64.b64encode(frame.read_bytes()).decode(), "record": row})
    data = json.dumps(rows).replace("<", "\\u003c")
    result = (directory / "result.json").read_text() if (directory / "result.json").exists() else "Run not finalized"
    meta_path = directory / "run_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    task = meta.get("task", {})
    task_text = task.get("instruction", "") + "\n" + task.get("rules", "")
    page = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>GameWorld Replay</title>
<style>body{font:16px system-ui;max-width:1000px;margin:32px auto;padding:0 24px;color:#17212b;background:#fafafa}
img{max-width:100%;border:1px solid #ccc;image-rendering:auto}pre{white-space:pre-wrap;background:#eee;padding:16px}
button{padding:8px 16px}input{width:60%}.stage{min-height:260px;margin:24px 0}</style>
<h1>GameWorld 轨迹回放</h1><p>原生游戏截图与动作记录。此页面不包含评分器私有状态。</p>
<pre>TASK_DESCRIPTION</pre>
<button id="prev">上一步</button> <input id="seek" type="range" min="0" value="0"> <button id="next">下一步</button>
<span id="label"></span><div class="stage"><img id="frame"></div><pre id="record"></pre>
<h2>运行结果</h2><pre>RESULT</pre><script>const rows=DATA;let i=0;const s=document.getElementById('seek');
s.max=Math.max(0,rows.length-1);function show(){if(!rows.length)return;s.value=i;
document.getElementById('frame').src='data:image/png;base64,'+rows[i].image;
document.getElementById('record').textContent=JSON.stringify(rows[i].record,null,2);
document.getElementById('label').textContent=(i+1)+' / '+rows.length;}
s.oninput=()=>{i=Number(s.value);show()};document.getElementById('prev').onclick=()=>{i=Math.max(0,i-1);show()};
document.getElementById('next').onclick=()=>{i=Math.min(rows.length-1,i+1);show()};show();</script></html>'''
    output = directory / "replay.html"
    rendered = page.replace("const rows=DATA;", "const rows=" + data + ";")
    rendered = rendered.replace("<pre>RESULT</pre>", "<pre>" + html.escape(result) + "</pre>")
    rendered = rendered.replace("<pre>TASK_DESCRIPTION</pre>", "<pre>" + html.escape(task_text) + "</pre>")
    output.write_text(rendered)
    return output
