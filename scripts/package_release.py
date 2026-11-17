"""Build one reviewed source snapshot for both participants and developers.

No Git history, private experiments, credentials, study data or native build
caches are copied. The output must be a new directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TREES = ("src", "game_packages", "tests", "scripts/release", ".github", "deploy/cloudflare")
FILES = (
    "paper/screenplay.pdf", ".gitattributes", "README.md", "NOTICE.md", "CONTRIBUTING.md", "pyproject.toml", "uv.lock",
    "docs/development.md", "docs/participants.md", "docs/http-api.md", "docs/validation.md", "docs/remote-access.md",
    "docs/human-data.md", "docs/text-interface-prototypes.md",
    "scripts/package_release.py", "scripts/build_text_endless.py", "scripts/verify_human_portal.py", "scripts/run_cloudflare_tunnel.py",
    "scripts/serve_remote.py",
    "scripts/build_text_remaining.py", "scripts/run_text_remaining.py",
    "research/text-ablation/native/endless_text.cpp",
    "research/text-ablation/native/singularity_text.py", "research/text-ablation/native/openttd_text.inc",
    "research/text-ablation/native/enigma_text.hh",
    "scripts/verify_text_cards_port.py", "scripts/verify_text_fifteen.py", "scripts/verify_text_tatham.py",
    "scripts/author_freecell_expansion.py", "scripts/author_puzzles_expansion.py",
    "scripts/author_singularity_enigma_gui.py", "scripts/author_transport_gui.py",
    "scripts/author_transport_space.py", "scripts/enigma_author_routes.py",
    "scripts/singularity_author_routes.py", "scripts/verify_singularity_enigma_references.py",
    "scripts/export_curriculum.py", "scripts/generate_pilot_tasks.py", "scripts/native_smoke.py",
    "scripts/run_enigma_author_batch.py", "scripts/run_singularity_author_batch.py",
    "configs/agents/openai-compatible.json",
)
SKIP_PARTS = {"__pycache__", ".DS_Store", ".pytest_cache"}
SECRET = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def selected_files():
    selected = {ROOT / name for name in FILES}
    for tree in TREES:
        selected.update(p for p in (ROOT / tree).rglob("*") if p.is_file())
    return sorted(p for p in selected if not (set(p.relative_to(ROOT).parts) & SKIP_PARTS)
                  and p.suffix not in {".pyc", ".pyo"})


def package(output: Path):
    output = output.resolve()
    archive = output.parent / (output.name + ".zip")
    if output.exists() or archive.exists():
        raise ValueError("Output directory or archive exists; choose a new output path")
    paths = selected_files()
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or linked release input: {path.relative_to(ROOT)}")
        if SECRET.search(path.read_bytes()):
            raise ValueError(f"Potential credential in release input: {path.relative_to(ROOT)}")
    output.mkdir(parents=True)
    for path in paths:
        dest = output / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    shutil.copyfile(ROOT / "scripts/release/env.example", output / ".env.example")
    shutil.copyfile(ROOT / "scripts/release/gitignore", output / ".gitignore")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    files = [{"path": str(p.relative_to(output)), "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(output.rglob("*")) if p.is_file()]
    manifest = {"name": "ScreenPlay", "version": version, "shared_participant_developer_version": True,
                "human_app_version": re.search(r'__version__ = "([^"]+)"', (ROOT / "src/screenplay_human/__init__.py").read_text()).group(1),
                "gui_tasks": 90, "text_tasks": 90, "new_text_tasks": 45, "files": files}
    (output / "RELEASE-MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob("*")):
            if p.is_file():
                z.write(p, str(Path(output.name) / p.relative_to(output)))
    return {"directory": str(output), "archive": str(archive), "files": len(files)+1,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(package(parser.parse_args().output), indent=2))
