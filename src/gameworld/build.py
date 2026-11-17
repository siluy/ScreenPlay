"""Fetch a pinned repository and build its original desktop frontend."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, text=True, **kwargs)


def source_spec(package: str = "tatham") -> dict:
    if package not in {"tatham", "openttd", "singularity", "pysolfc", "enigma", "endless_sky"}:
        raise ValueError("Unknown game package")
    return json.loads((ROOT / "game_packages" / package / "source.json").read_text())


def fetch(package: str = "tatham") -> Path:
    if package not in {"tatham", "openttd"}:
        from .native_build import fetch as fetch_native
        return fetch_native(package)
    if package == "openttd":
        from .openttd_build import fetch as fetch_openttd
        return fetch_openttd()
    spec = source_spec()
    source = ROOT / ".cache/sources/tatham"
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--no-checkout", "--filter=blob:none", spec["repo"], str(source)])
        run(["git", "-C", str(source), "checkout", "--detach", spec["base_commit"]])
    actual = run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if actual != spec["base_commit"]:
        raise RuntimeError(f"Source revision mismatch: {actual}; expected {spec['base_commit']}")
    changes = run(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], capture_output=True).stdout
    if changes:
        raise RuntimeError("Pinned upstream source has modifications; refusing to build it")
    return source


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Source patch anchor is not unique: {old[:100]!r}")
    return text.replace(old, new, 1)


def prepare(source: Path) -> Path:
    prepared = ROOT / ".cache/prepared/tatham"
    if prepared.exists():
        shutil.rmtree(prepared)
    shutil.copytree(source, prepared, ignore=shutil.ignore_patterns(".git"))
    p = prepared / "midend.c"
    text = p.read_text()
    # All solver entry points pass through this function, including keyboard shortcuts.
    anchor = "const char *midend_solve(midend *me)\n{"
    text = replace_once(text, anchor, anchor + '\n    if (getenv("GAMEWORLD_SESSION")) return "Solve is disabled in GameWorld";')
    p.write_text(text)
    p = prepared / "osx.m"
    text = p.read_text()
    text = replace_once(text, "@implementation GameWindow\n", """static void gw_write_data(void *ctx, const void *buf, int len) {
    [(NSMutableData *)ctx appendBytes:buf length:(NSUInteger)len];
}
@implementation GameWindow
""" + (ROOT / "game_packages/tatham/native/telemetry.m.inc").read_text())
    text = replace_once(text, "    load_prefs(me);", '    if (!getenv("GAMEWORLD_SESSION")) load_prefs(me);')
    marker = "    midend_new_game(me);\n    w = h = INT_MAX;"
    text = replace_once(text, marker, """    const char *gw_id = getenv("GAMEWORLD_GAME_ID");
    if (gw_id) {
        const char *err = midend_game_id(me, gw_id);
        if (err) { fprintf(stderr, "Invalid game ID: %s\\n", err); exit(2); }
    }
""" + marker)
    marker = "    [self setIgnoresMouseEvents:NO];\n\n    [self center];\t\t       /* :-) */"
    text = replace_once(text, marker, marker + """
    if (getenv("GAMEWORLD_SESSION")) {
        [self setFrameTopLeftPoint:NSMakePoint(80, [[[NSScreen screens] objectAtIndex:0] frame].size.height - 100)];
        [NSTimer scheduledTimerWithTimeInterval:0.05 target:self selector:@selector(gameworldTelemetry:) userInfo:nil repeats:YES];
    }
""")
    marker = "- (void)processKey:(int)b\n{"
    text = replace_once(text, marker, marker + """
    if (getenv("GAMEWORLD_SESSION") && (b == UI_NEWGAME || b == 'n' || b == 'N' || b == 14)) return;
""")
    marker = "- (BOOL)validateMenuItem:(NSMenuItem *)item\n{"
    text = replace_once(text, marker, marker + """
    if (getenv("GAMEWORLD_SESSION")) {
        SEL a = [item action];
        if (a != @selector(undoMove:) && a != @selector(redoMove:) &&
            a != @selector(restartGame:) && a != @selector(performClose:)) return NO;
    }
""")
    marker = "@implementation AppController\n"
    text = replace_once(text, marker, marker + """
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
    const char *name = getenv("GAMEWORLD_GAME");
    if (!name) return;
    for (int i = 0; i < gamecount; i++) {
        if (strcmp(name, gamelist[i]->name)) continue;
        id win = [[GameWindow alloc] initWithGame:gamelist[i]];
        [win makeKeyAndOrderFront:self];
        [app activateIgnoringOtherApps:YES];
        return;
    }
    fprintf(stderr, "Unknown GameWorld game\\n"); exit(2);
}
""")
    text = replace_once(text, "    [app setApplicationIconImage:icon];", "    [app setApplicationIconImage:icon];\n    [app setActivationPolicy:NSApplicationActivationPolicyRegular];")
    # The dock must not allow new game windows to replace a task's initial state.
    marker = "- (void)newGameWindow:(id)sender\n{"
    text = replace_once(text, marker, marker + '\n    if (getenv("GAMEWORLD_SESSION")) return;')
    p.write_text(text)
    return prepared


def build(package: str = "tatham") -> dict:
    if package not in {"tatham", "openttd"}:
        from .native_build import build as build_native
        return build_native(package)
    if package == "openttd":
        from .openttd_build import build as build_openttd
        return build_openttd()
    source = fetch()
    prepared = prepare(source)
    output = ROOT / "build/tatham"
    cmake = Path(sys.executable).parent / "cmake"
    cmake_exe = str(cmake) if cmake.exists() else "cmake"
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    run([cmake_exe, "-S", str(ROOT / "game_packages/tatham/native"), "-B", str(output),
         "-G", "Ninja", f"-DPUZZLES_SOURCE={prepared}", "-DCMAKE_BUILD_TYPE=Release"], env=env)
    run([cmake_exe, "--build", str(output), "--parallel", "4"], env=env)
    shutil.copyfile(source / "LICENCE", output / "TATHAM-LICENCE.txt")
    receipt = {"source": source_spec(), "python": sys.version, "platform": sys.platform,
               "build_dir": str(output), "adapter": "original-frontend-with-state-telemetry"}
    (output / "build_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
