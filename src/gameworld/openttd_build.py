"""Build a pinned OpenTTD with a narrowly scoped native state/time adapter."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from .build import ROOT, source_spec, run, replace_once


def fetch() -> Path:
    spec = source_spec("openttd")
    source = ROOT / ".cache/sources/openttd"
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--branch", spec["release"], spec["repo"], str(source)])
    actual = run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if actual != spec["base_commit"]:
        raise RuntimeError("OpenTTD source revision does not match its manifest")
    if run(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], capture_output=True).stdout:
        raise RuntimeError("OpenTTD upstream checkout has tracked modifications")
    return source


def assets() -> Path:
    root = ROOT / ".cache/assets/openttd"
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "opengfx-8.0-all.zip"
    if not archive.exists():
        temporary = archive.with_suffix(".part")
        run(["curl", "-fL", "--retry", "2", "-A", "Mozilla/5.0",
             source_spec("openttd")["graphics"]["url"], "-o", str(temporary)])
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as z:
        if any(Path(n).is_absolute() or ".." in Path(n).parts for n in z.namelist()):
            raise RuntimeError("Invalid path in graphics archive")
        z.extractall(root)
    with tarfile.open(root / "opengfx-8.0.tar") as t:
        t.extractall(root, filter="data")
    return root / "opengfx-8.0"


def prepare(source: Path) -> Path:
    prepared = ROOT / ".cache/prepared/openttd"
    shutil.copytree(source, prepared, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    for name in ["gameworld_bridge.cpp", "gameworld_bridge.h"]:
        shutil.copyfile(ROOT / "game_packages/openttd/native" / name, prepared / "src" / name)
    manifest = source_spec("openttd")
    (prepared / ".ottdrev").write_text(f"15.3-gameworld\t20260404\t2\t{manifest['base_commit']}\t0\t0\n")
    path = prepared / "src/openttd.cpp"
    text = path.read_text()
    text = replace_once(text, '#include "stdafx.h"', '#include "stdafx.h"\n#include "gameworld_bridge.h"')
    marker = "\tCheckEngines();\n\tCheckIndustries();\n\tMarkWholeScreenDirty();"
    text = replace_once(text, marker, "\tCheckEngines();\n\tif (!GameWorldEnabled()) CheckIndustries();\n\tMarkWholeScreenDirty();\n\tGameWorldNewGame();")
    text = replace_once(text, "GenerateWorld(from_heightmap ? GWM_HEIGHTMAP : GWM_NEWGAME,",
                        "GenerateWorld(GameWorldEnabled() ? GWM_EMPTY : (from_heightmap ? GWM_HEIGHTMAP : GWM_NEWGAME),")
    text = replace_once(text, "void StateGameLoop()\n{", "void StateGameLoop()\n{\n\tif (!GameWorldAllowUpdate()) return;")
    text = replace_once(text, "void SwitchToMode(SwitchMode new_mode)\n{",
        "void SwitchToMode(SwitchMode new_mode)\n{\n\tif (new_mode != SM_SAVE_GAME && new_mode != SM_SAVE_HEIGHTMAP && GameWorldRejectModeSwitch()) return;")
    text = replace_once(text, "\tSocialIntegration::RunCallbacks();", "\tSocialIntegration::RunCallbacks();\n\tGameWorldPublish();")
    path.write_text(text)
    for filename, anchor in [
        ("console.cpp", "void IConsoleCmdExec(std::string_view command_string, const uint recurse_count)\n{"),
        ("cheat_gui.cpp", "void ShowCheatWindow()\n{"),
    ]:
        path = prepared / "src" / filename
        text = path.read_text()
        text = replace_once(text, '#include "stdafx.h"', '#include "stdafx.h"\n#include "gameworld_bridge.h"')
        text = replace_once(text, anchor, anchor + "\n\tif (GameWorldEnabled()) return;")
        path.write_text(text)
    path = prepared / "CMakeLists.txt"
    path.write_text(path.read_text() + '\n# GameWorld native adapter\ntarget_sources(${BINARY_NAME} PRIVATE src/gameworld_bridge.cpp)\n')
    return prepared


def build() -> dict:
    prepared = prepare(fetch())
    gfx = assets()
    output = ROOT / "build/openttd-native"
    cmake = Path(sys.executable).parent / "cmake"
    env = dict(os.environ, PATH=str(cmake.parent) + os.pathsep + os.environ.get("PATH", ""))
    run([str(cmake), "-S", str(prepared), "-B", str(output), "-G", "Ninja",
         "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=/opt/homebrew", "-DOPTION_USE_ASSERTS=ON"], env=env)
    run([str(cmake), "--build", str(output), "--target", "openttd", "--parallel", "6"], env=env)
    shutil.copyfile(ROOT / ".cache/sources/openttd/COPYING.md", output / "OPENTTD-COPYING.md")
    receipt = {"source": source_spec("openttd"), "build_dir": str(output), "graphics": str(gfx),
               "adapter": "native-cocoa-read-only-state-and-controlled-updates", "platform": sys.platform}
    (output / "build_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
