"""Persistent human study state; only public observations cross the HTTP boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import secrets
import sqlite3
import threading
import time
import uuid

from gameworld.tasks import catalog
from . import __version__
from .runtime import NativeRuntime
from .reporting import build_report, number
from .catalog import TEXT_PACKAGES, NEW_TEXT_PACKAGES, text_group, decision_limit, invitation_presets


class StudyError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


@dataclass
class LiveAttempt:
    runtime: object
    deadline: float
    started_monotonic: float
    paused_monotonic: float | None = None
    paused_total: float = 0.0
    pause_id: str | None = None


class Study:
    def __init__(self, directory: Path, *, decisions=100, wall_seconds=3600,
                 max_text_workers=4, runtime_factory=NativeRuntime, validation_only=False):
        if not (1 <= decisions <= 1000 and 1 <= wall_seconds <= 7200 and 1 <= max_text_workers <= 16):
            raise ValueError("Invalid study limits")
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        actor = "validation" if validation_only else "human"
        self.native_runtime = runtime_factory is NativeRuntime
        self.factory = (lambda *args: NativeRuntime(*args, actor=actor)) if runtime_factory is NativeRuntime else runtime_factory
        self.live = {}
        self.closed = False
        self.tasks = catalog()
        snapshot = self.directory / "task-catalog.snapshot.json"
        if snapshot.exists():
            if json.loads(snapshot.read_text()) != self.tasks:
                raise ValueError("Task definitions changed; use a new study directory")
        else:
            snapshot.write_text(dump(self.tasks))
        self.db = sqlite3.connect(self.directory / "study.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY, alias TEXT UNIQUE NOT NULL, code_hash TEXT UNIQUE NOT NULL,
                plan TEXT NOT NULL, created TEXT NOT NULL, consent TEXT, withdrawn TEXT, paused_at TEXT,
                control_revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, role TEXT NOT NULL, participant_id TEXT, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, task_index INTEGER NOT NULL,
                task_id TEXT NOT NULL, condition TEXT NOT NULL, status TEXT NOT NULL,
                created TEXT NOT NULL, started TEXT, deadline REAL, finished TEXT,
                public_path TEXT, result TEXT, schemas TEXT NOT NULL DEFAULT '[]',
                elapsed_seconds REAL, elapsed_source TEXT, app_version TEXT,
                paused_at TEXT, paused_seconds REAL DEFAULT 0, pause_count INTEGER DEFAULT 0,
                remaining_seconds REAL, wall_elapsed_seconds REAL);
            CREATE TABLE IF NOT EXISTS actions (
                attempt_id TEXT NOT NULL, request_id TEXT NOT NULL, canonical TEXT NOT NULL,
                received TEXT NOT NULL, observation_id INTEGER NOT NULL, response_path TEXT,
                PRIMARY KEY(attempt_id, request_id));
            CREATE TABLE IF NOT EXISTS participation_events (
                participant_id TEXT NOT NULL, request_id TEXT NOT NULL, canonical TEXT NOT NULL,
                event TEXT NOT NULL, attempt_id TEXT, created TEXT NOT NULL, details TEXT,
                PRIMARY KEY(participant_id, request_id));
            CREATE TABLE IF NOT EXISTS pause_intervals (
                id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, started TEXT NOT NULL,
                finished TEXT, duration_seconds REAL, end_reason TEXT);
        """)
        config = {"version": __version__, "max_decisions": decisions, "wall_seconds": wall_seconds,
                  "max_text_workers": max_text_workers, "observation_window": 5,
                  "actor": actor, "timer_start": "first_observation_ready",
                  "deadline_policy": "server_monotonic_wall_clock_including_disconnection"}
        old = self.db.execute("SELECT value FROM meta WHERE key='config'").fetchone()
        if old:
            previous = json.loads(old[0])
            compatible = {"0.2.0", "0.2.1", "0.2.2", "0.2.3", "0.2.4"}
            if previous.get("version") not in compatible or {k:v for k,v in previous.items() if k != "version"} != {k:v for k,v in config.items() if k != "version"}:
                raise ValueError("Existing study configuration differs; use its original limits or a new directory")
            config = previous  # Preserve the original study protocol and invitations.
        self.config = config
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('config', ?)", (dump(config),))
        self.db.commit()
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(attempts)")}
        additions = {"elapsed_seconds": "REAL", "elapsed_source": "TEXT", "app_version": "TEXT",
                     "paused_at": "TEXT", "paused_seconds": "REAL DEFAULT 0", "pause_count": "INTEGER DEFAULT 0",
                     "remaining_seconds": "REAL", "wall_elapsed_seconds": "REAL"}
        participant_columns = {r[1] for r in self.db.execute("PRAGMA table_info(participants)")}
        if set(additions)-columns or not {"paused_at","control_revision"} <= participant_columns:
            backup = self.directory / ("study-before-statistics-"+uuid.uuid4().hex+".sqlite3")
            with sqlite3.connect(backup) as destination:
                self.db.backup(destination)
            backup.chmod(0o600)
            for name, kind in additions.items():
                if name not in columns:
                    self.db.execute(f"ALTER TABLE attempts ADD COLUMN {name} {kind}")
            if "paused_at" not in participant_columns:
                self.db.execute("ALTER TABLE participants ADD COLUMN paused_at TEXT")
            if "control_revision" not in participant_columns:
                self.db.execute("ALTER TABLE participants ADD COLUMN control_revision INTEGER NOT NULL DEFAULT 0")
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('explicit_pause_policy',?)", (dump({
            "introduced_at": stamp(), "app_version": __version__, "policy": "explicit_breaks_excluded_from_active_time",
            "board_retention": "live_worker_only; paused_GUI_reserves_desktop", "disconnection": "does_not_automatically_pause"}),))
        versions = self.db.execute("SELECT value FROM meta WHERE key='app_versions'").fetchone()
        versions = json.loads(versions[0]) if versions else [config["version"]]
        if __version__ not in versions:
            versions.append(__version__)
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('app_versions',?)", (dump(versions),))
        self.db.commit()
        admin_path = self.directory / "admin-token.txt"
        if not admin_path.exists():
            with admin_path.open("x") as f:
                f.write(secrets.token_urlsafe(32) + "\n")
            admin_path.chmod(0o600)
        self.admin_hash = digest(admin_path.read_text().strip())
        # A restart never guesses whether an OS input executed. Preserve the old
        # attempt and require an explicit new start for this unscored task.
        for row in self.db.execute("SELECT * FROM attempts WHERE status IN ('starting','active','paused')").fetchall():
            self._end(row, {"success": None, "score": None, "stop_reason": "server_interrupted",
                            "decisions": self._observation(row).get("decision_index", 0)})
        self.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        self.db.commit()
        self.stop_event = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.monitor.start()

    def public_catalog(self):
        return [{"task_id": key, "game": v["game"], "package": v["package"],
                 "difficulty": v.get("parameters", {}).get("curriculum", {}).get("difficulty"),
                 "instruction": v["instruction"], "text_supported": v["package"] in TEXT_PACKAGES,
                 "text_group": text_group(v),
                 "text_max_decisions": decision_limit(v, "text", self.config["max_decisions"])}
                for key, v in sorted(self.tasks.items())]

    def invitation_presets(self):
        return invitation_presets(self.tasks)

    def _assignment_decisions(self, item):
        # Old invitations have no per-task cap and retain their original study limit.
        return item.get("max_decisions", self.config["max_decisions"])

    def invite(self, alias, task_ids, condition, seed=0):
        with self.lock:
            if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", alias):
                raise StudyError("invalid_participant_code", 400)
            if condition not in {"gui", "text", "mixed"} or type(seed) is not int:
                raise StudyError("invalid_assignment", 400)
            if not isinstance(task_ids, list) or not 1 <= len(task_ids) <= 90 or not all(isinstance(x, str) for x in task_ids):
                raise StudyError("invalid_tasks", 400)
            if len(set(task_ids)) != len(task_ids) or any(x not in self.tasks for x in task_ids):
                raise StudyError("invalid_tasks", 400)
            if condition != "gui" and any(self.tasks[x]["package"] not in TEXT_PACKAGES for x in task_ids):
                raise StudyError("text_not_supported", 400)
            ordered = list(task_ids)
            random.Random(seed).shuffle(ordered)
            plan = [{"task_id": x, "condition": ("gui" if (i + seed) % 2 == 0 else "text") if condition == "mixed" else condition}
                    for i, x in enumerate(ordered)]
            for item in plan:
                if item["condition"] == "text" and self.tasks[item["task_id"]]["package"] in NEW_TEXT_PACKAGES:
                    item["max_decisions"] = decision_limit(self.tasks[item["task_id"]], "text", self.config["max_decisions"])
                    item["assignment_protocol"] = "new-text45-task-native-v1"
            code = secrets.token_urlsafe(24)
            pid = uuid.uuid4().hex
            try:
                self.db.execute("INSERT INTO participants (id,alias,code_hash,plan,created) VALUES (?,?,?,?,?)",
                                (pid, alias, digest(code), dump(plan), stamp()))
                self.db.commit()
            except sqlite3.IntegrityError:
                raise StudyError("participant_code_exists", 409) from None
            return {"participant_id": pid, "alias": alias, "invitation_code": code,
                    "task_count": len(plan), "condition": condition, "order_seed": seed}

    def login(self, kind, code):
        with self.lock:
            if not isinstance(code, str) or not 8 <= len(code) <= 200:
                raise StudyError("invalid_login", 401)
            pid = None
            if kind == "admin":
                if not secrets.compare_digest(digest(code), self.admin_hash):
                    raise StudyError("invalid_login", 401)
            elif kind == "participant":
                row = self.db.execute("SELECT id FROM participants WHERE code_hash=?", (digest(code),)).fetchone()
                if row is None:
                    raise StudyError("invalid_login", 401)
                pid = row[0]
            else:
                raise StudyError("invalid_login", 401)
            token = secrets.token_urlsafe(32)
            self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(token), kind, pid, time.time()+43200))
            self.db.commit()
            return token

    def identity(self, token, role=None):
        with self.lock:
            row = self.db.execute("SELECT role, participant_id FROM sessions WHERE token_hash=? AND expires>?",
                                  (digest(token or ""), time.time())).fetchone()
            if not row:
                raise StudyError("login_required", 401)
            if role and row["role"] != role:
                raise StudyError("forbidden", 403)
            return dict(row)

    def logout(self, token):
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token or ""),))
            self.db.commit()

    def _participant(self, pid):
        row = self.db.execute("SELECT * FROM participants WHERE id=?", (pid,)).fetchone()
        if not row:
            raise StudyError("not_found", 404)
        return row

    def _attempt(self, pid, aid):
        row = self.db.execute("SELECT * FROM attempts WHERE id=? AND participant_id=?", (aid, pid)).fetchone()
        if not row:
            raise StudyError("not_found", 404)
        return row

    def _observation(self, row):
        return json.loads((self.directory / row["public_path"]).read_text()) if row["public_path"] else {}

    def _save(self, aid, value):
        folder = self.directory / "attempts" / aid / "observations"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        file = folder / (uuid.uuid4().hex + ".json")
        file.write_text(dump(value))
        return str(file.relative_to(self.directory))

    @staticmethod
    def _public(value):
        obs = value["observation"]
        task = obs.get("task", {})
        # Explicit whitelist: never include initial_desc, references, native
        # saves, source paths, worker logs, credentials, or private evaluations.
        out = {"observation_id": obs["observation_id"], "game": value["game"],
               "instruction": task.get("instruction", obs.get("instruction", "")),
               "rules": task.get("rules", obs.get("rules", "")),
               "decision_index": obs.get("decision_index", obs["observation_id"]),
               "budget_remaining": obs["budget_remaining"], "receipt": obs.get("receipt"),
               "ended": bool(obs.get("ended")), "result": obs.get("result"),
               "time_contract": task.get("time_contract")}
        for key in ("image", "board_text", "interface_profile", "experimental", "simulation_updates_remaining"):
            if key in obs:
                out[key] = obs[key]
        return out

    def _view(self, row):
        return {"attempt_id": row["id"], "task_id": row["task_id"], "condition": row["condition"],
                "status": row["status"], "deadline": row["deadline"], "started_at": row["started"],
                "observation": self._observation(row), "schemas": json.loads(row["schemas"])}

    def state(self, pid):
        with self.lock:
            self._expire()
            p = self._participant(pid)
            plan = json.loads(p["plan"])
            attempts = self.db.execute("SELECT * FROM attempts WHERE participant_id=? ORDER BY created,id", (pid,)).fetchall()
            completed = {a["task_index"] for a in attempts if a["status"] == "scored"}
            index = next((i for i in range(len(plan)) if i not in completed), None)
            current = next((a for a in reversed(attempts) if a["status"] == "active"), None)
            paused = next((a for a in reversed(attempts) if a["status"] == "paused"), None)
            next_task = None if index is None else {"index": index + 1, "condition": plan[index]["condition"],
                                                  "game": self.tasks[plan[index]["task_id"]]["game"],
                                                  "max_decisions": self._assignment_decisions(plan[index])}
            return {"version": __version__, "protocol": self.config,
                    "participant": {"id": p["id"], "alias": p["alias"], "consented": bool(p["consent"]),
                                    "control_revision": p["control_revision"],
                                    "paused": bool(p["paused_at"]),
                                    "withdrawn": bool(p["withdrawn"]), "total": len(plan),
                                    "completed": len(completed), "done": index is None,
                                    "next_task": next_task},
                    "active": self._view(current) if current else None,
                    "paused_attempt": {"attempt_id": paused["id"], "game": self.tasks[paused["task_id"]]["game"],
                                       "remaining_seconds": paused["remaining_seconds"],
                                       "decisions": self._observation(paused).get("decision_index", 0)} if paused else None,
                    "attempts": [{"attempt_id": a["id"], "number": a["task_index"]+1,
                                  "game": self.tasks[a["task_id"]]["game"], "condition": a["condition"],
                                  "status": a["status"], "result": json.loads(a["result"]) if a["result"] else None}
                                 for a in attempts], "server_time": time.time()}

    def consent(self, pid):
        with self.lock:
            self.db.execute("UPDATE participants SET consent=COALESCE(consent,?) WHERE id=?", (stamp(), pid))
            self.db.commit()

    def start(self, pid):
        with self.lock:
            if catalog() != self.tasks:
                raise StudyError("task_definitions_changed", 503)
            state = self.state(pid)
            if state["participant"]["withdrawn"]:
                raise StudyError("participant_withdrawn")
            if state["participant"]["paused"]:
                raise StudyError("participant_paused")
            if not state["participant"]["consented"]:
                raise StudyError("consent_required", 400)
            if state["active"]:
                return state["active"]
            if state["participant"]["done"]:
                raise StudyError("all_tasks_complete")
            index = state["participant"]["next_task"]["index"] - 1
            item = json.loads(self._participant(pid)["plan"])[index]
            if self.native_runtime and item["condition"] == "gui":
                self._desktop_ready()
            counts = CounterConditions(self.db)
            if item["condition"] == "gui" and counts["gui"]:
                raise StudyError("desktop_busy")
            if item["condition"] == "text" and counts["text"] >= self.config["max_text_workers"]:
                raise StudyError("text_capacity_busy")
            aid = uuid.uuid4().hex
            self.db.execute("INSERT INTO attempts (id,participant_id,task_index,task_id,condition,status,created,app_version) VALUES (?,?,?,?,?,'starting',?,?)",
                            (aid, pid, index, item["task_id"], item["condition"], stamp(), __version__))
            self.db.commit()
            runtime = None
            try:
                runtime = self.factory(item["task_id"], item["condition"], self._assignment_decisions(item),
                                       self.directory / "attempts" / aid / "native")
                initial = self._public(runtime.initial)
                path = self._save(aid, initial)
                deadline = time.time() + self.config["wall_seconds"]
                ready = time.monotonic()
                self.live[aid] = LiveAttempt(runtime, ready + self.config["wall_seconds"], ready)
                self.db.execute("UPDATE attempts SET status='active',started=?,deadline=?,public_path=?,schemas=? WHERE id=?",
                                (stamp(), deadline, path, dump(runtime.initial["schemas"]), aid))
                self.db.commit()
            except Exception:
                if runtime is not None:
                    runtime.close()
                self._end(self._attempt(pid, aid), {"success": None, "score": None,
                                                  "stop_reason": "environment_startup_error", "decisions": 0})
                raise StudyError("environment_startup_error", 503) from None
            return self._view(self._attempt(pid, aid))

    def _end(self, row, result):
        aid = row["id"]
        finished = stamp()
        ended = time.monotonic()
        live = self.live.pop(aid, None)
        elapsed = None
        wall_elapsed = None
        paused_total = row["paused_seconds"] or 0.0
        source = "not_started" if not row["started"] else "unavailable_after_restart"
        if live:
            paused_total = live.paused_total + (max(0.0, ended-live.paused_monotonic) if live.paused_monotonic is not None else 0)
            wall_elapsed = max(0.0, ended-live.started_monotonic)
            elapsed = max(0.0, wall_elapsed-paused_total)
            source = "monotonic_excluding_pauses" if row["pause_count"] else "monotonic"
            if result.get("stop_reason") == "wall_budget_exhausted":
                elapsed, source = float(self.config["wall_seconds"]), "budget_limit"
        elif row["status"] == "paused":
            elapsed, source = row["elapsed_seconds"], "paused_checkpoint"
        if row["status"] == "paused":
            duration = max(0.0, ended-live.paused_monotonic) if live and live.paused_monotonic is not None else None
            self.db.execute("UPDATE pause_intervals SET finished=?,duration_seconds=?,end_reason=? WHERE attempt_id=? AND finished IS NULL",
                            (finished, duration, result.get("stop_reason"), aid))
        if live:
            live.runtime.close()
        obs = self._observation(row)
        obs.update(ended=True, result=result)
        path = self._save(aid, obs)
        status = "scored" if type(result.get("success")) is bool else "interrupted"
        self.db.execute("UPDATE attempts SET status=?,finished=?,result=?,public_path=?,elapsed_seconds=?,elapsed_source=?,paused_seconds=?,wall_elapsed_seconds=?,paused_at=NULL WHERE id=?",
                        (status, finished, dump(result), path, elapsed, source, paused_total, wall_elapsed, aid))
        self.db.execute("UPDATE actions SET response_path=? WHERE attempt_id=? AND response_path IS NULL", (path, aid))
        (self.directory / "attempts" / aid / "human_result.json").write_text(dump(result))
        self.db.commit()

    def _timing(self, row):
        if row["id"] in self.live:
            live = self.live[row["id"]]
            now = live.paused_monotonic if live.paused_monotonic is not None else time.monotonic()
            return max(0.0, now-live.started_monotonic-live.paused_total), "paused_monotonic" if live.paused_monotonic is not None else "running_monotonic"
        if row["elapsed_source"]:
            return row["elapsed_seconds"], row["elapsed_source"]
        if row["started"] and row["finished"]:
            try:
                elapsed = (datetime.fromisoformat(row["finished"])-datetime.fromisoformat(row["started"])).total_seconds()
                if number(elapsed):
                    return elapsed, "legacy_wall_clock_estimate"
            except (ValueError, TypeError):
                pass
        return None, "unavailable"

    def _expire(self):
        for aid, live in list(self.live.items()):
            row = self.db.execute("SELECT * FROM attempts WHERE id=?", (aid,)).fetchone()
            process = getattr(live.runtime, "process", None)
            expired = live.paused_monotonic is None and time.monotonic() >= live.deadline
            dead = process is not None and process.poll() is not None
            if expired or dead:
                obs = self._observation(row)
                self._end(row, {"success": False if expired else None, "score": 0.0 if expired else None,
                                "stop_reason": "wall_budget_exhausted" if expired else "worker_interrupted",
                                "decisions": obs.get("decision_index", 0)})

    def action(self, pid, aid, request):
        with self.lock:
            row = self._attempt(pid, aid)
            if not isinstance(request, dict) or set(request) != {"request_id", "observation_id", "action"}:
                raise StudyError("invalid_request", 400)
            rid = request["request_id"]
            if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", rid) or type(request["observation_id"]) is not int or not isinstance(request["action"], dict):
                raise StudyError("invalid_request", 400)
            canonical = dump(request)
            old = self.db.execute("SELECT * FROM actions WHERE attempt_id=? AND request_id=?", (aid, rid)).fetchone()
            if old:
                if old["canonical"] != canonical:
                    raise StudyError("action_id_payload_conflict")
                if not old["response_path"]:
                    raise StudyError("action_pending")
                return {"attempt_id": aid, "observation": json.loads((self.directory / old["response_path"]).read_text()), "replayed": True}
            self._expire()
            row = self._attempt(pid, aid)
            if row["status"] == "paused":
                raise StudyError("attempt_paused")
            if row["status"] != "active":
                raise StudyError("attempt_finished")
            if request["observation_id"] != self._observation(row)["observation_id"]:
                raise StudyError("stale_observation")
            self.db.execute("INSERT INTO actions VALUES (?,?,?,?,?,NULL)",
                            (aid, rid, canonical, stamp(), request["observation_id"]))
            self.db.commit()  # Intent is durable before any native input.
            try:
                value = self.live[aid].runtime.act(rid, request["observation_id"], request["action"])
                obs = self._public(value)
                path = self._save(aid, obs)
                self.db.execute("UPDATE attempts SET public_path=? WHERE id=?", (path, aid))
                self.db.commit()
                if obs["ended"]:
                    self._end(self._attempt(pid, aid), obs["result"])
                else:
                    self._expire()
            except Exception:
                row = self._attempt(pid, aid)
                self._end(row, {"success": None, "score": None, "stop_reason": "environment_error",
                                "decisions": self._observation(row).get("decision_index", 0) + 1,
                                "action_outcome": "uncertain"})
            row = self._attempt(pid, aid)
            self.db.execute("UPDATE actions SET response_path=? WHERE attempt_id=? AND request_id=?", (row["public_path"], aid, rid))
            self.db.commit()
            return {"attempt_id": aid, "observation": self._observation(row), "replayed": False}

    @staticmethod
    def _desktop_ready():
        try:
            NativeRuntime.ensure_desktop_ready()
        except RuntimeError as exc:
            raise StudyError("desktop_locked" if str(exc) == "desktop_locked" else "desktop_unavailable", 503) from None

    def participation(self, pid, kind, request):
        """Explicit, idempotent lifecycle changes; never issue a native input."""
        with self.lock:
            if kind not in {"pause", "resume", "withdraw"} or not isinstance(request, dict) or set(request)-{"request_id","attempt_id","accepted","revision"}:
                raise StudyError("invalid_request", 400)
            rid, expected = request.get("request_id"), request.get("attempt_id")
            if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", rid) or (expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{32}", expected))):
                raise StudyError("invalid_request", 400)
            canonical = dump({"kind":kind, **request})
            previous = self.db.execute("SELECT canonical FROM participation_events WHERE participant_id=? AND request_id=?", (pid,rid)).fetchone()
            if previous:
                if previous[0] != canonical:
                    raise StudyError("action_id_payload_conflict")
                return self.state(pid)
            self._expire()
            p = self._participant(pid)
            if type(request.get("revision")) is not int or request["revision"] != p["control_revision"]:
                raise StudyError("participation_state_changed")
            row = self.db.execute("SELECT * FROM attempts WHERE participant_id=? AND status IN ('active','paused') ORDER BY created DESC LIMIT 1", (pid,)).fetchone()
            if expected != (row["id"] if row else None):
                raise StudyError("participation_state_changed")
            now, at = time.monotonic(), stamp()
            event, details = kind, {}
            if kind == "pause":
                if p["withdrawn"]:
                    raise StudyError("participant_withdrawn")
                if row and row["status"] == "active":
                    live = self.live[row["id"]]
                    live.paused_monotonic, live.pause_id = now, uuid.uuid4().hex
                    elapsed = max(0.0, now-live.started_monotonic-live.paused_total)
                    self.db.execute("UPDATE attempts SET status='paused',paused_at=?,remaining_seconds=?,elapsed_seconds=?,elapsed_source='paused_monotonic',pause_count=COALESCE(pause_count,0)+1 WHERE id=?",
                                    (at,max(0.0,live.deadline-now),elapsed,row["id"]))
                    self.db.execute("INSERT INTO pause_intervals (id,attempt_id,started) VALUES (?,?,?)", (live.pause_id,row["id"],at))
                self.db.execute("UPDATE participants SET paused_at=COALESCE(paused_at,?) WHERE id=?", (at,pid))
            elif kind == "resume":
                if p["withdrawn"]:
                    if request.get("accepted") is not True:
                        raise StudyError("rejoin_consent_required", 400)
                    details = {"previous_withdrawn_at":p["withdrawn"], "previous_consent_at":p["consent"]}
                    event = "rejoined"
                    self.db.execute("UPDATE participants SET withdrawn=NULL,consent=? WHERE id=?", (at,pid))
                if row and row["status"] == "paused":
                    if self.native_runtime and row["condition"] == "gui":
                        self._desktop_ready()
                    live = self.live[row["id"]]
                    duration = max(0.0, now-live.paused_monotonic)
                    live.paused_total += duration
                    live.deadline += duration
                    self.db.execute("UPDATE pause_intervals SET finished=?,duration_seconds=?,end_reason='resumed' WHERE id=?", (at,duration,live.pause_id))
                    live.paused_monotonic, live.pause_id = None, None
                    self.db.execute("UPDATE attempts SET status='active',paused_at=NULL,deadline=?,paused_seconds=?,remaining_seconds=NULL WHERE id=?",
                                    (time.time()+max(0,live.deadline-now),live.paused_total,row["id"]))
                self.db.execute("UPDATE participants SET paused_at=NULL WHERE id=?", (pid,))
            else:
                if request.get("accepted") is not True:
                    raise StudyError("withdraw_confirmation_required", 400)
                self.withdraw(pid)
            self.db.execute("INSERT INTO participation_events VALUES (?,?,?,?,?,?,?)", (pid,rid,canonical,event,expected,at,dump(details)))
            self.db.execute("UPDATE participants SET control_revision=control_revision+1 WHERE id=?", (pid,))
            self.db.commit()
            return self.state(pid)

    def withdraw(self, pid):
        with self.lock:
            self._participant(pid)
            self.db.execute("UPDATE participants SET withdrawn=COALESCE(withdrawn,?),paused_at=NULL WHERE id=?", (stamp(), pid))
            for row in self.db.execute("SELECT * FROM attempts WHERE participant_id=? AND status IN ('active','paused')", (pid,)).fetchall():
                self._end(row, {"success": None, "score": None, "stop_reason": "participant_withdrew",
                                "decisions": self._observation(row).get("decision_index", 0)})
            self.db.commit()

    def history(self, pid, aid):
        with self.lock:
            row = self._attempt(pid, aid)
            actions = self.db.execute("SELECT * FROM actions WHERE attempt_id=? ORDER BY rowid", (aid,)).fetchall()
            paths = [a["response_path"] for a in actions if a["response_path"]]
            if row["public_path"]:
                paths.append(row["public_path"])
            # Duplicate acknowledgements do not add observations.
            unique = list(dict.fromkeys(paths))[-5:]
            return {"observations": [json.loads((self.directory / p).read_text()) for p in unique],
                    "actions": [{"observation_id": a["observation_id"], "action": json.loads(a["canonical"])["action"],
                                 "received_at": a["received"]} for a in actions]}

    def export(self, *, include_actions=True):
        with self.lock:
            self._expire()
            participants = [{k: r[k] for k in ["id", "alias", "created", "consent", "withdrawn", "paused_at"]} |
                            {"assignment": [{**item, "max_decisions": self._assignment_decisions(item)}
                                            for item in json.loads(r["plan"])]}
                            for r in self.db.execute("SELECT * FROM participants ORDER BY created")]
            attempts = []
            for r in self.db.execute("SELECT * FROM attempts ORDER BY created,id"):
                v = {k: r[k] for k in ["id", "participant_id", "task_index", "task_id", "condition", "status", "created", "started", "finished"]}
                v["result"] = json.loads(r["result"]) if r["result"] else None
                v["elapsed_seconds"], v["elapsed_source"] = self._timing(r)
                v["app_version"] = r["app_version"] or self.config["version"]
                v["decisions"] = (v["result"] or {}).get("decisions")
                if r["status"] in {"active", "paused"}:
                    v["decisions"] = self._observation(r).get("decision_index")
                live = self.live.get(r["id"])
                v["pause_count"] = r["pause_count"] or 0
                v["paused_seconds"] = (live.paused_total + (max(0,time.monotonic()-live.paused_monotonic) if live.paused_monotonic is not None else 0)) if live else r["paused_seconds"]
                v["wall_elapsed_seconds"] = max(0,time.monotonic()-live.started_monotonic) if live else r["wall_elapsed_seconds"]
                v["pause_intervals"] = [dict(x) for x in self.db.execute("SELECT started,finished,duration_seconds,end_reason FROM pause_intervals WHERE attempt_id=? ORDER BY started", (r["id"],))]
                if include_actions:
                    v["actions"] = [{"request_id": a["request_id"], "received_at": a["received"],
                                 "observation_id": a["observation_id"], "action": json.loads(a["canonical"])["action"]}
                                for a in self.db.execute("SELECT * FROM actions WHERE attempt_id=? ORDER BY rowid", (r["id"],))]
                attempts.append(v)
            return {"exported_at": stamp(), "app_version": __version__, "protocol": self.config,
                    "pause_policy": json.loads(self.db.execute("SELECT value FROM meta WHERE key='explicit_pause_policy'").fetchone()[0]),
                    "participation_events": [{"participant_id":r["participant_id"],"event":r["event"],"attempt_id":r["attempt_id"],"created":r["created"],"details":json.loads(r["details"] or "{}")} for r in self.db.execute("SELECT * FROM participation_events ORDER BY rowid")],
                    "participants": participants, "attempts": attempts,
                    "report": build_report(participants, attempts, self.tasks)}

    def _monitor(self):
        while not self.stop_event.wait(.5):
            with self.lock:
                self._expire()

    def close(self):
        self.stop_event.set()
        with self.lock:
            if self.closed:
                return
            for aid in list(self.live):
                row = self.db.execute("SELECT * FROM attempts WHERE id=?", (aid,)).fetchone()
                self._end(row, {"success": None, "score": None, "stop_reason": "server_interrupted",
                                "decisions": self._observation(row).get("decision_index", 0)})
            self.closed = True
        self.monitor.join(timeout=2)
        self.db.close()


def CounterConditions(db):
    result = {"gui": 0, "text": 0}
    for r in db.execute("SELECT condition,COUNT(*) AS n FROM attempts WHERE status IN ('starting','active','paused') GROUP BY condition"):
        result[r["condition"]] = r["n"]
    return result
