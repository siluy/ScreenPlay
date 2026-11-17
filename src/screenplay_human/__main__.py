"""Run one shared ScreenPlay version for participants and developers."""
import argparse
import fcntl
import json
from pathlib import Path
import signal
import threading

from . import __version__
from .server import create_server, csv_export
from .study import Study


def main():
    parser = argparse.ArgumentParser(description="ScreenPlay human study portal")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--data", type=Path, default=Path("runs/human-study"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8790)
    serve.add_argument("--public-origin")
    serve.add_argument("--trusted-proxy", action="store_true", help="Trust client IP only from the configured loopback Cloudflare gateway")
    serve.add_argument("--decisions", type=int, default=100)
    serve.add_argument("--wall-seconds", type=int, default=3600)
    serve.add_argument("--text-workers", type=int, default=4)
    serve.add_argument("--validation", action="store_true", help="Label operator/test runs separately from human research data")
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.data / "server.lock").open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("This study is already served; use that server or a different data directory")
        study = Study(args.data, decisions=args.decisions, wall_seconds=args.wall_seconds,
                      max_text_workers=args.text_workers, validation_only=args.validation)
        server = None
        try:
            server = create_server(study, args.host, args.port, args.public_origin, args.trusted_proxy)
            def stop(*_):
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            print(json.dumps({"name": "ScreenPlay", "version": __version__,
                              "participant_url": args.public_origin or f"http://127.0.0.1:{server.server_address[1]}",
                              "admin_token_file": str((args.data / "admin-token.txt").resolve()),
                              "data_directory": str(args.data.resolve()), "model_requests": 0}), flush=True)
            server.serve_forever(poll_interval=.25)
        finally:
            if server:
                server.server_close()
            study.close()


if __name__ == "__main__":
    main()
