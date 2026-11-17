"""Same-origin browser application with separate participant/admin authorization."""
from __future__ import annotations

import csv
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import ipaddress
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from . import __version__
from .study import StudyError


STATIC = Path(__file__).with_name("static")
FILES = {"/": ("index.html", "text/html"), "/admin": ("index.html", "text/html"),
         "/developer": ("index.html", "text/html"), "/join": ("index.html", "text/html"),
         "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}


def csv_export(data):
    out = io.StringIO(newline="")
    columns = ["participant", "task_index", "task_id", "condition", "attempt_id", "status",
               "success", "score", "stop_reason", "decisions", "elapsed_seconds", "elapsed_source",
               "pause_count", "paused_seconds", "wall_elapsed_seconds", "app_version", "started_at", "finished_at"]
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    aliases = {p["id"]: p["alias"] for p in data["participants"]}
    for a in data["attempts"]:
        r = a["result"] or {}
        writer.writerow({"participant": aliases[a["participant_id"]], "task_index": a["task_index"]+1,
                         "task_id": a["task_id"], "condition": a["condition"], "attempt_id": a["id"],
                         "status": a["status"], "success": r.get("success"), "score": r.get("score"),
                         "stop_reason": r.get("stop_reason"), "decisions": r.get("decisions"),
                         "elapsed_seconds": a.get("elapsed_seconds"), "elapsed_source": a.get("elapsed_source"),
                         "app_version": a.get("app_version"),
                         "pause_count": a.get("pause_count"), "paused_seconds": a.get("paused_seconds"),
                         "wall_elapsed_seconds": a.get("wall_elapsed_seconds"),
                         "started_at": a["started"], "finished_at": a["finished"]})
    return "\ufeff" + out.getvalue()


def results_csv(data):
    out = io.StringIO(newline="")
    columns = ["participant", "question_number", "task_id", "project", "game", "difficulty", "condition",
               "status", "correct", "elapsed_seconds", "elapsed_source", "decisions", "stop_reason",
               "pause_count", "paused_seconds", "wall_elapsed_seconds",
               "started_at", "finished_at", "attempt_id", "attempt_count", "interrupted_attempt_count", "app_version",
               "max_decisions", "assignment_protocol"]
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in data["report"]["rows"]:
        writer.writerow({**row, "correct": int(row["correct"]) if type(row["correct"]) is bool else None})
    return "\ufeff"+out.getvalue()


def summary_csv(data):
    out = io.StringIO(newline="")
    names = list(data["report"]["views"][0]["overall"])
    writer = csv.DictWriter(out, fieldnames=["participant_scope", "participant_id", "condition", "group_type", "group_key", "group_label", *names])
    writer.writeheader()
    for view in data["report"]["views"]:
        base = {"participant_scope": "ALL" if view["participant_id"] is None else view["participant"],
                "participant_id": view["participant_id"], "condition": view["condition"]}
        writer.writerow({**base, "group_type": "overall", "group_key": "all", "group_label": "全部", **view["overall"]})
        for dimension in ("condition", "project", "game", "difficulty", "project_difficulty", "task"):
            for row in view["by_"+dimension]:
                writer.writerow({**base, "group_type": dimension, "group_key": row["key"], "group_label": row["label"],
                                 **{key: row[key] for key in names}})
    return "\ufeff"+out.getvalue()


def create_server(study, host="127.0.0.1", port=8790, public_origin=None, trusted_proxy=False):
    login_failures = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Invitation/session credentials never appear in access logs.

        def reply(self, status, value, content_type="application/json", cookie=None, filename=None):
            if content_type == "application/json":
                payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            else:
                payload = value if isinstance(value, bytes) else value.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            if filename:
                self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The idempotency ledger keeps the action acknowledgement.

        def boundary(self, mutation=False):
            host = self.headers.get("Host", "").lower()
            if host not in self.server.host_origins:
                raise StudyError("host_not_allowed", 403)
            origin = self.headers.get("Origin")
            if origin and origin != self.server.host_origins[host]:
                raise StudyError("origin_not_allowed", 403)
            if mutation and (self.headers.get("X-Study-Request") != "1" or
                             self.headers.get("Content-Type", "").split(";")[0] != "application/json"):
                raise StudyError("invalid_request_headers", 403)

        def token(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                return cookie["screenplay_session"].value if "screenplay_session" in cookie else ""
            except Exception:
                return ""

        def identity(self, role=None):
            return study.identity(self.token(), role)

        def cookie_security(self):
            origin = self.server.host_origins[self.headers.get("Host", "").lower()]
            return "; Secure" if origin.startswith("https://") else ""

        def login_address(self):
            peer = self.client_address[0]
            host = self.headers.get("Host", "").lower()
            if trusted_proxy and ipaddress.ip_address(peer).is_loopback and self.server.host_origins.get(host) == self.server.public_origin:
                try:
                    return str(ipaddress.ip_address(self.headers.get("X-Screenplay-Client-IP", "")))
                except ValueError:
                    pass
            return peer

        def do_GET(self):
            try:
                self.boundary()
                path = urlsplit(self.path).path
                if path in FILES:
                    name, mime = FILES[path]
                    self.reply(200, (STATIC / name).read_bytes(), mime)
                elif path == "/api/about":
                    tasks = study.public_catalog()
                    self.reply(200, {"name": "ScreenPlay", "version": __version__, "gui_tasks": len(tasks),
                                     "text_tasks": sum(t["text_supported"] for t in tasks),
                                     "new_text_tasks": sum(t["text_group"] == "new_text45" for t in tasks),
                                     "one_version": True})
                elif path == "/api/session":
                    who = self.identity()
                    self.reply(200, {"role": who["role"], **(study.state(who["participant_id"]) if who["role"] == "participant" else {"version": __version__})})
                elif path == "/api/admin/catalog":
                    self.identity("admin")
                    self.reply(200, {"tasks": study.public_catalog(), "protocol": study.config,
                                     "invitation_presets": study.invitation_presets(),
                                     "app_version": __version__,
                                     "participant_origin": self.server.public_origin})
                elif path == "/api/admin/overview":
                    self.identity("admin")
                    data = study.export(include_actions=False)
                    self.reply(200, data)
                elif path in {"/api/admin/export.json", "/api/admin/export.csv", "/api/admin/results.csv", "/api/admin/summary.csv"}:
                    self.identity("admin")
                    data = study.export(include_actions=path.endswith(".json"))
                    if path.endswith("/results.csv"):
                        self.reply(200, results_csv(data), "text/csv", filename="screenplay-task-results.csv")
                    elif path.endswith("/summary.csv"):
                        self.reply(200, summary_csv(data), "text/csv", filename="screenplay-summary.csv")
                    elif path.endswith(".csv"):
                        self.reply(200, csv_export(data), "text/csv", filename="screenplay-human-results.csv")
                    else:
                        self.reply(200, data, filename="screenplay-human-results.json")
                elif path.startswith("/api/attempts/") and path.endswith("/history"):
                    who = self.identity("participant")
                    parts = path.split("/")
                    if len(parts) != 5:
                        raise StudyError("not_found", 404)
                    self.reply(200, study.history(who["participant_id"], parts[3]))
                else:
                    raise StudyError("not_found", 404)
            except StudyError as exc:
                self.reply(exc.status, {"error": exc.code})
            except Exception:
                self.reply(500, {"error": "server_error"})

        def do_POST(self):
            try:
                self.boundary(mutation=True)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise StudyError("invalid_body", 400) from None
                if not 0 < size <= 65536:
                    raise StudyError("body_too_large", 413)
                self.connection.settimeout(10)
                try:
                    data = json.loads(self.rfile.read(size))
                except (ValueError, OSError):
                    raise StudyError("invalid_json", 400) from None
                if not isinstance(data, dict):
                    raise StudyError("invalid_json", 400)
                path = urlsplit(self.path).path
                if path == "/api/login":
                    key = self.login_address()
                    failures = [x for x in login_failures.get(key, []) if x > time.monotonic()-60]
                    if len(failures) >= 10:
                        raise StudyError("login_rate_limited", 429)
                    try:
                        token = study.login(data.get("kind"), data.get("code"))
                    except StudyError:
                        login_failures[key] = failures + [time.monotonic()]
                        raise
                    login_failures.pop(key, None)
                    secure = self.cookie_security()
                    self.reply(200, {"ok": True}, cookie=f"screenplay_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}")
                    return
                if path == "/api/logout":
                    study.logout(self.token())
                    self.reply(200, {"ok": True}, cookie="screenplay_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"+self.cookie_security())
                    return
                if path == "/api/admin/invitations":
                    self.identity("admin")
                    self.reply(201, study.invite(data.get("alias"), data.get("task_ids"), data.get("condition"), data.get("seed", 0)))
                    return
                who = self.identity("participant")
                pid = who["participant_id"]
                if path == "/api/consent":
                    if data.get("accepted") is not True:
                        raise StudyError("consent_required", 400)
                    study.consent(pid)
                    self.reply(200, study.state(pid))
                elif path == "/api/attempts":
                    self.reply(200, study.start(pid))
                elif path in {"/api/pause", "/api/resume", "/api/withdraw"}:
                    kind = path.rsplit("/",1)[1]
                    # Old tabs used an ambiguous exit button. Treat that legacy
                    # empty request as a reversible break, never a withdrawal.
                    if kind == "withdraw" and not data:
                        current = study.state(pid)
                        attempt = current["active"] or current["paused_attempt"]
                        data = {"request_id":"legacy-pause-"+str(time.time_ns()), "attempt_id":attempt["attempt_id"] if attempt else None,
                                "revision":current["participant"]["control_revision"]}
                        kind = "pause"
                    self.reply(200, study.participation(pid, kind, data))
                elif path.startswith("/api/attempts/") and path.endswith("/actions"):
                    parts = path.split("/")
                    if len(parts) != 5:
                        raise StudyError("not_found", 404)
                    self.reply(200, study.action(pid, parts[3], data))
                else:
                    raise StudyError("not_found", 404)
            except StudyError as exc:
                self.reply(exc.status, {"error": exc.code})
            except Exception:
                # No tracebacks, absolute paths or private native diagnostics in
                # participant responses. Durable action intent prevents replay.
                self.reply(500, {"error": "server_error"})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    actual_port = server.server_address[1]
    server.host_origins = {}
    server.public_origin = None
    if host in {"127.0.0.1", "localhost"}:
        server.host_origins = {f"{h}:{actual_port}": f"http://{h}:{actual_port}"
                               for h in ("127.0.0.1", "localhost")}
    if public_origin:
        parsed = urlsplit(public_origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            server.server_close()
            raise ValueError("public-origin must be an exact http(s) origin")
        origin = public_origin.rstrip("/")
        server.host_origins[parsed.netloc.lower()] = origin
        server.public_origin = origin
    elif not server.host_origins:
        server.server_close()
        raise ValueError("Remote binding requires --public-origin matching the participant URL")
    return server
