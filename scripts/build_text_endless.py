"""Link a separate headless driver; never rebuild or modify the GUI executable."""
from pathlib import Path
import json
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/prepared/endless_sky/source"
GUI_BUILD = ROOT / "build/endless_sky"
OUTPUT = ROOT / "build/text_endless_sky"


def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    commands = subprocess.check_output([str(ROOT/".venv/bin/ninja"), "-C", str(GUI_BUILD),
                                       "-t", "commands", "endless-sky"], text=True).splitlines()
    template = shlex.split(next(c for c in commands if " -c " in c and c.endswith("/HiringPanel.cpp")))
    text = (SOURCE / "HiringPanel.cpp").read_text()
    anchor = "hiring->Draw(info, this);"
    if text.count(anchor) != 1:
        raise RuntimeError("Native hiring render boundary changed")
    (OUTPUT / "HiringPanel.cpp").write_text(text.replace(anchor, "/* Headless: skip rendering; retain native capacity calculation. */"))
    for source, target in [(OUTPUT/"HiringPanel.cpp", OUTPUT/"HiringPanel.o"),
                           (ROOT/"research/text-ablation/native/endless_text.cpp", OUTPUT/"main.o")]:
        args=[]; index=0
        while index < len(template):
            arg=template[index]
            if arg in {"-MT","-MF"}:
                index += 2; continue
            if arg == "-MD":
                index += 1; continue
            if arg in {"-o","-c"}:
                args.extend([arg,str(target if arg == "-o" else source)]); index += 2; continue
            args.append(arg);index += 1
        args += ["-I",str(SOURCE)]
        subprocess.run(args,cwd=GUI_BUILD,check=True)
    link=shlex.split(commands[-1])
    if link[:2] == [":","&&"]:link=link[2:]
    if link[-2:] == ["&&",":"]:link=link[:-2]
    for i,arg in enumerate(link):
        if arg.endswith("/HiringPanel.cpp.o"):link[i]=str(OUTPUT/"HiringPanel.o")
        if arg.endswith("/source/main.cpp.o"):link[i]=str(OUTPUT/"main.o")
    link[link.index("-o")+1]=str(OUTPUT/"endless-text")
    subprocess.run(link,cwd=GUI_BUILD,check=True)
    receipt={"binary":str(OUTPUT/"endless-text"),"linked_original_game_objects":True,
             "source_receipt":"build/endless_sky/build_receipt.json",
             "gui_binary_modified":False,"patch":"HiringPanel::Draw final interface rendering call omitted only",
             "scope":"Pinned original port trading/hiring/cargo/ship/account objects; no window, rendering, travel or flight simulation."}
    (OUTPUT/"build_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt))


if __name__ == "__main__":build()
