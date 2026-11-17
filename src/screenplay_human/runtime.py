"""Bounded IPC to native workers. There is no model/API client in this path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


class NativeRuntime:
    @staticmethod
    def ensure_desktop_ready():
        if sys.platform == "darwin":
            import Quartz
            if (Quartz.CGSessionCopyCurrentDictionary() or {}).get("CGSSessionScreenIsLocked", False):
                raise RuntimeError("desktop_locked")
        from gameworld.desktop import require_permissions
        require_permissions()

    def __init__(self, task_id, condition, decisions, directory, *, actor="human"):
        self.directory = Path(directory)
        self.directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.log = self.directory.parent.joinpath(self.directory.name + ".worker.log").open("ab")
        # In particular, do not inherit API keys or the historical provider shims.
        keep = {"HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "DISPLAY", "XAUTHORITY"}
        env = {k: v for k, v in os.environ.items() if k in keep}
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        self.process = subprocess.Popen([
            sys.executable, "-m", "screenplay_human.worker", "--task", task_id,
            "--condition", condition, "--decisions", str(decisions),
            "--directory", str(self.directory), "--actor", actor,
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            start_new_session=True, env=env)
        self.awake = None
        if sys.platform == "darwin":
            flags = ["-d", "-i", "-s"] if condition == "gui" else ["-i", "-s"]
            self.awake = subprocess.Popen(["/usr/bin/caffeinate", *flags, "-w", str(self.process.pid)],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.buffer = b""
        try:
            self.initial = self._read(60)
        except BaseException:
            self.close()
            raise

    def _read(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                value = json.loads(line)
                if "error" in value:
                    raise RuntimeError("environment_error")
                return value
            ready, _, _ = select.select([self.process.stdout], [], [], max(0, deadline-time.monotonic()))
            if not ready:
                break
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError("worker_exited")
            self.buffer += data
            if len(self.buffer) > 16 * 1024 * 1024:
                raise RuntimeError("observation_too_large")
        raise TimeoutError("environment_timeout")

    def act(self, action_id, observation_id, action):
        request = {"method": "action", "action_id": action_id,
                   "observation_id": observation_id, "action": action}
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        self.process.stdin.flush()
        return self._read(35)

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write(b'{"method":"close"}\n')
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    self.process.wait(timeout=3)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
        for stream in [self.process.stdin, self.process.stdout, self.log]:
            stream.close()
        if self.awake and self.awake.poll() is None:
            self.awake.terminate()
            self.awake.wait(timeout=3)
