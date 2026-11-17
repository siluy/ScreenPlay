"""A bounded, authenticated public endpoint; never serves workspace files."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from .runner import ProtocolError
from pydantic import ValidationError


def create_server(episode, token: str, host: str = "127.0.0.1", port: int = 8788):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body):
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, {"error": "unauthorized"})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == "/v1/observation":
                with episode.lock:
                    self.reply(200, episode.last_response)
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != "/v1/action":
                self.reply(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    self.reply(413, {"error": "invalid_body_size"})
                    return
                request = json.loads(self.rfile.read(size))
                response = episode.act(request)
            except ProtocolError as exc:
                self.reply(409, {"error": str(exc)})
                return
            except (ValueError, ValidationError, TypeError):
                self.reply(400, {"error": "invalid_request"})
                return
            self.reply(200, response)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def serve(episode, token: str, host: str = "127.0.0.1", port: int = 8788):
    server = create_server(episode, token, host, port)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
