"""Report the state of the browser-execution services, from inside the worker container.

Prints JSON: the runner's health and sandbox self-check (renderer seccomp, user, no
--no-sandbox) and the egress proxy's health (over its UNIX control socket). Uses the worker's
own tokens; nothing here is reachable from outside the execution networks. Run:
    python -m app.modules.execution.container_check
"""

import json
import urllib.error
import urllib.request

from app.core.config import get_settings
from app.modules.execution.browser import control_request


def _get(url: str, headers: dict | None = None) -> tuple[int, dict]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with opener.open(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except OSError as e:
        return 0, {"error": type(e).__name__}


def main() -> None:
    s = get_settings()
    out = {"isolation": s.browser_isolation}
    out["runner_health"] = _get(f"{s.browser_runner_url}/health")
    out["runner_selfcheck"] = _get(
        f"{s.browser_runner_url}/selfcheck", {"X-Runner-Token": s.browser_runner_token}
    )
    try:
        out["proxy_health"] = control_request(s.egress_control_socket, "", "GET", "/health")
    except OSError as e:
        out["proxy_health"] = (0, {"error": type(e).__name__})
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
