"""Link experimental native text binaries without modifying GUI sources or binaries."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def replace_once(value, old, new):
    if value.count(old) != 1:
        raise RuntimeError(f"Non-unique native patch anchor: {old[:80]}")
    return value.replace(old, new, 1)


def relink(package, unit, source, binary, extra_sources=None):
    original = ROOT / "build" / ("openttd-native" if package == "openttd" else package)
    output = ROOT / "build" / ("text_" + package)
    output.mkdir(parents=True, exist_ok=True)
    target = "openttd" if package == "openttd" else "src/enigma"
    gui_hash = hashlib.sha256((original / target).read_bytes()).hexdigest()
    commands = subprocess.check_output([str(ROOT / ".venv/bin/ninja"), "-C", str(original),
                                       "-t", "commands", target], text=True).splitlines()
    sources = {unit: source, **(extra_sources or {})}
    for unit_name, unit_source in sources.items():
        template = shlex.split(next(c for c in commands if " -c " in c and c.endswith("/" + unit_name)))
        generated = output / unit_name
        generated.write_text(unit_source)
        obj = output / (unit_name + ".o")
        args = []
        i = 0
        while i < len(template):
            arg = template[i]
            if arg in {"-MT", "-MF"}:
                i += 2
                continue
            if arg == "-MD":
                i += 1
                continue
            if arg in {"-o", "-c"}:
                args.extend([arg, str(obj if arg == "-o" else generated)])
                i += 2
                continue
            args.append(arg)
            i += 1
        args += ["-I", str(ROOT / ".cache/prepared" / package / "src")]
        subprocess.run(args, cwd=original, check=True)
    link = shlex.split(commands[-1])
    if link[:2] == [":", "&&"]:
        link = link[2:]
    if link[-2:] == ["&&", ":"]:
        link = link[:-2]
    if any(a in {"&&", ";", "|"} for a in link):
        raise RuntimeError("Unexpected native linker command")
    replaced = 0
    for i, arg in enumerate(link):
        for unit_name in sources:
            if arg.endswith("/" + unit_name + ".o"):
                link[i] = str(output / (unit_name + ".o"))
                replaced += 1
    if replaced != len(sources):
        raise RuntimeError("Expected one native object replacement per source")
    link[link.index("-o")+1] = str(output / binary)
    subprocess.run(link, cwd=original, check=True)
    if hashlib.sha256((original / target).read_bytes()).hexdigest() != gui_hash:
        raise RuntimeError("Original GUI executable changed during text build")
    receipt = {"package": package, "binary": str(output / binary), "gui_binary_modified": False,
               "original_build_receipt": str(original / "build_receipt.json"),
               "original_gui_sha256_before_and_after": gui_hash,
               "replaced_translation_units": list(sources),
               "source_sha256": {name: hashlib.sha256(value.encode()).hexdigest() for name,value in sources.items()},
               "scope": "Experimental restricted text controls; original game state, rules and evaluator."}
    if package == "enigma":
        receipt["text_header_sha256"] = hashlib.sha256((ROOT / "research/text-ablation/native/enigma_text.hh").read_bytes()).hexdigest()
    (output / "build_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


def build_openttd():
    source = (ROOT / "game_packages/openttd/native/gameworld_bridge.cpp").read_text()
    source = replace_once(source, "namespace {", "static void TextPublish(nlohmann::json &j);\n\nnamespace {")
    source = replace_once(source, "    try {\n        const std::string temporary", "    TextPublish(j);\n    try {\n        const std::string temporary")
    source += "\n" + (ROOT / "research/text-ablation/native/openttd_text.inc").read_text()
    main = (ROOT / ".cache/prepared/openttd/src/openttd.cpp").read_text()
    main = replace_once(main, "/* In a dedicated server, the server does not play */\n\tif (!VideoDriver::GetInstance()->HasGUI()) {",
                        "/* The text driver retains the ordinary single-player company setup. */\n\tif (!VideoDriver::GetInstance()->HasGUI() && !GameWorldEnabled()) {")
    relink("openttd", "gameworld_bridge.cpp", source, "openttd-text", {"openttd.cpp": main})


def build_enigma():
    source = (ROOT / ".cache/prepared/enigma/src/game.cc").read_text()
    source = replace_once(source, '#include "../gameworld_bridge.hh"',
                          '#include "' + str(ROOT / ".cache/prepared/enigma/gameworld_bridge.hh") + '"')
    source = replace_once(source, '#include "game.hh"', '#include "game.hh"\n#include "' +
                          str(ROOT / "research/text-ablation/native/enigma_text.hh") + '"')
    source = replace_once(source, "                gw::publish();", "                gw::publish();\n                gwtext::publish();")
    relink("enigma", "game.cc", source, "enigma-text")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package", choices=["openttd", "enigma", "all"])
    package = parser.parse_args().package
    if package in {"openttd", "all"}:
        build_openttd()
    if package in {"enigma", "all"}:
        build_enigma()

