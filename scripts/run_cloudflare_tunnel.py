"""Run an existing Cloudflare-managed tunnel without putting its token in argv."""
import argparse
import getpass
import os
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloudflared", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundled = root / ".tools/cloudflared/2026.10.5/cloudflared"
    binary = args.cloudflared or (bundled if bundled.is_file() else shutil.which("cloudflared"))
    if not binary:
        parser.error("Install cloudflared from Cloudflare first; on macOS: brew install cloudflared")
    token = getpass.getpass("Cloudflare Tunnel token（粘贴后回车，输入不显示）: ").strip()
    if len(token) < 40 or any(c.isspace() for c in token):
        parser.error("Paste only the tunnel token, not the entire install command")
    keep = {"HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["TUNNEL_TOKEN"] = token
    print("正在连接 Cloudflare。保持此终端运行；Ctrl+C 可停止隧道。", flush=True)
    os.execvpe(str(binary), [str(binary), "tunnel", "--no-autoupdate", "run"], env)


if __name__ == "__main__":
    main()
