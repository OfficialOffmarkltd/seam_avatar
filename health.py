import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

def start_health_server(port: int, ready_flag: threading.Event) -> None:
    """
    Starts a minimal HTTP server in a daemon thread.
    GET /health       → 200 {"status": "ok"}     always (process alive)
    GET /health/ready → 200 {"status": "ready"}   when ready_flag is set
                        503 {"status": "loading"} before ready_flag is set
    """

    class HealthHandler(BaseHTTPRequestHandler):

        def do_GET(self):
            if self.path == "/health":
                self._respond(200, {"status": "ok"})
            elif self.path == "/health/ready":
                if ready_flag.is_set():
                    self._respond(200, { "status": "ready" })
                else:
                    self._respond(503, { "status": "loading", "detail": "initialising" })
            else:
                self._respond(404, { "status": "not found" })

        def _respond(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server listening on :{port}")

