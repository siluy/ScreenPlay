"""Episode lifecycle, public/private logging, budgets and idempotent actions."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import fcntl
import io
import json
from pathlib import Path
import threading
import time
import uuid
from pydantic import ValidationError
from .build import ROOT, source_spec
from .protocol import ActionRequest, Finish, validate_action
from .tasks import Task, evaluate
from .tatham import TathamBackend


class ProtocolError(ValueError):
    pass


def write_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def append_json(path: Path, value: dict):
    with path.open("a") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")


class Episode:
    def __init__(self, task: Task, output: Path | None = None, backend=None):
        self.task = task
        if backend is not None:
            self.backend = backend
        elif task.package == "openttd":
            from .openttd import OpenTTDBackend
            self.backend = OpenTTDBackend()
        elif task.package != "tatham":
            from .native import NativeBackend
            self.backend = NativeBackend()
        else:
            self.backend = TathamBackend()
        self.id = uuid.uuid4().hex
        self.directory = (output or ROOT / "runs" / self.id).resolve()
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.private = self.directory / "private"
        self.private.mkdir(mode=0o700)
        (self.directory / "frames").mkdir()
        self.steps = 0
        self.observation_id = 0
        self.ended = False
        self.cached = {}
        self.lock = threading.RLock()
        self.desktop_lease = None
        self.last_response = None
        self.requested_stop_reason = None
        self.started_at = time.monotonic()

    def start(self):
        lease_path = ROOT / ".cache/desktop.lock"
        lease_path.parent.mkdir(exist_ok=True, parents=True)
        self.desktop_lease = lease_path.open("a")
        try:
            fcntl.flock(self.desktop_lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.backend.start(self.task, self.private, self.id)
            write_json(self.private / "task.json", self.task.__dict__)
            write_json(self.directory / "run_meta.json", {
                "protocol_version": "0.1", "episode_id": self.id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "task": self.task.public_view(), "source": source_spec(self.task.package),
                "backend": getattr(self.backend, "name", "native_cocoa"), "input": "pyautogui", "capture": "desktop_crop",
                "isolation": "shared-desktop-development-only", "agent": "external-unspecified",
                "time_mode": self.task.time_mode, "model_tokens": None,
                "input_timing": {"pointer_settle_ms": 80},
            })
            self.last_response = self._observe({"status": "ready"})
            return self.last_response
        except Exception:
            self.close()
            raise

    def _observe(self, receipt: dict) -> dict:
        image, state = self.backend.capture()
        self.width, self.height = image.size
        frame_name = f"frames/{self.observation_id:06d}.png"
        image.save(self.directory / frame_name)
        output = io.BytesIO()
        image.save(output, format="PNG")
        append_json(self.private / "states.jsonl", {"observation_id": self.observation_id, "state": state})
        if hasattr(self.backend, "evaluate"):
            score = self.backend.evaluate(state)
        else:
            score = evaluate(state, self.backend.initial_desc, self.task.game)
        self.last_score = score
        response = {"protocol_version": "0.1", "episode_id": self.id,
                    "observation_id": self.observation_id, "task": self.task.public_view(),
                    "image": {"format": "png", "width": self.width, "height": self.height,
                              "base64": base64.b64encode(output.getvalue()).decode()},
                    "decision_index": self.steps,
                    "budget_remaining": {"decisions": max(0, self.task.max_decisions-self.steps)},
                    "receipt": receipt, "ended": self.ended}
        if "processed_updates" in state and "max_updates" in self.task.parameters:
            response["budget_remaining"]["simulation_updates"] = max(0, self.task.parameters["max_updates"] - state["processed_updates"])
        if score["success"]:
            self._finalize("success")
        elif score["violations"]:
            self._finalize("task_integrity_violation")
        elif score.get("terminal_failure"):
            self._finalize(score.get("failure_reason", "task_failed"))
        elif self.steps >= self.task.max_decisions:
            self._finalize("decision_budget_exhausted")
        elif self.requested_stop_reason:
            self._finalize(self.requested_stop_reason)
        if self.ended:
            response["ended"] = True
            response["result"] = self.public_result
        return response

    def _finalize(self, reason: str):
        self.ended = True
        self.public_result = {"success": self.last_score["success"], "score": self.last_score["score"],
                              "stop_reason": reason, "decisions": self.steps}
        write_json(self.directory / "result.json", {**self.public_result,
                   "wall_seconds": round(time.monotonic()-self.started_at, 3)})
        write_json(self.private / "evaluation.json", self.last_score)

    def abort(self, reason: str, *, valid_failure=False):
        if self.ended:
            return
        self.ended = True
        self.public_result = {"success": False if valid_failure else None,
                              "score": 0.0 if valid_failure else None,
                              "stop_reason": reason, "decisions": self.steps}
        write_json(self.directory / "result.json", {**self.public_result,
                   "wall_seconds": round(time.monotonic()-self.started_at, 3)})
        if hasattr(self, "last_score"):
            write_json(self.private / "evaluation.json", self.last_score)
        if self.last_response is not None:
            self.last_response = {**self.last_response, "ended": True, "result": self.public_result}

    def act(self, raw: dict, *, agent_context: dict | None = None) -> dict:
        request = ActionRequest.model_validate(raw)
        with self.lock:
            if request.episode_id != self.id:
                raise ProtocolError("episode_mismatch")
            canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
            if request.action_id in self.cached:
                previous, response = self.cached[request.action_id]
                if previous != canonical:
                    raise ProtocolError("action_id_payload_conflict")
                return response
            if self.ended:
                raise ProtocolError("episode_finished")
            if request.based_on_observation_id != self.observation_id:
                raise ProtocolError("stale_observation")
            before = self.observation_id
            self.steps += 1
            started = time.monotonic()
            simulation = None
            try:
                action = validate_action(request.action, self.width, self.height)
            except (ValueError, ValidationError):
                receipt = {"action_id": request.action_id, "status": "rejected", "error": "invalid_action"}
                action = None
            else:
                receipt = {"action_id": request.action_id, "status": "executed"}
            try:
                if isinstance(action, Finish):
                    self.requested_stop_reason = "agent_finished"
                elif action is not None:
                    simulation = self.backend.execute(action)
                self.observation_id += 1
                response = self._observe(receipt)
            except Exception as exc:
                # An input may already have executed: terminate instead of retrying it blindly.
                self.abort("environment_error")
                append_json(self.private / "errors.jsonl", {"type": type(exc).__name__, "message": str(exc)})
                response = {"episode_id": self.id, "ended": True,
                            "receipt": {"action_id": request.action_id, "status": "uncertain"},
                            "result": {"success": None, "score": None, "stop_reason": "environment_error"}}
            append_json(self.directory / "interactions.jsonl", {
                "step": self.steps, "observation_id": before, "action_id": request.action_id,
                "action": request.action, "receipt": response["receipt"],
                "frame_before": f"frames/{before:06d}.png",
                "frame_after": f"frames/{self.observation_id:06d}.png" if "image" in response else None,
                "execution_wall_ms": round((time.monotonic()-started)*1000, 3),
                "simulation": simulation,
                "input_provider": "pyautogui", "human_intervention": "not-monitored-in-development-mode",
                "agent_context": agent_context,
            })
            self.cached[request.action_id] = (canonical, response)
            self.last_response = response
            return response

    def close(self):
        try:
            if not self.ended:
                self.abort("interrupted" if self.last_response is not None else "startup_error")
            self.backend.close()
        finally:
            if self.desktop_lease:
                self.desktop_lease.close()
                self.desktop_lease = None
