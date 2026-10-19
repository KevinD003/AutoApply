"""Test/dev helper: run a Celery worker with beat, plus a tiny health endpoint so Playwright's
webServer can wait for it. Not used in production.

Usage: python scripts/e2e_worker.py HEALTH_PORT
"""

import http.server
import os
import signal
import subprocess
import sys
import threading

port = int(sys.argv[1])
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.worker",
        "worker",
        "-B",
        "-P",
        "prefork",
        "-c",
        "2",
        "--loglevel=INFO",
        "--without-gossip",
        "--without-mingle",
        "--without-heartbeat",
        "-s",
        f"/tmp/celerybeat-e2e-{port}",
    ],
    cwd=here,
    # Same process group as this supervisor: Playwright stops a webServer by killing its group,
    # so the worker must not escape into its own session.
)


class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        ok = proc.poll() is None
        self.send_response(200 if ok else 503)
        self.end_headers()

    def log_message(self, *a):
        pass


def stop(*_):
    proc.terminate()
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
srv = http.server.HTTPServer(("127.0.0.1", port), Health)
threading.Thread(target=srv.serve_forever, daemon=True).start()
proc.wait()
