# ruff: noqa: E501
"""Browser-execution test against a clean Compose stack (base + docker-compose.execution-test.yml).

Runs on the Docker host with the Python standard library only. Drives the real API, reads the
synthetic receiver's own ledger as the oracle, inspects containers with `docker`, and runs a
probe inside the browser container. Every scenario uses the deployment launch path: worker ->
browser-runner (sandboxed Chromium, unprivileged user) -> egress-proxy -> receiver.

Usage (from the repository root, after `docker compose up`): see scripts/compose-execution-test.sh
Prints PASS/FAIL lines and a JSON summary; exits non-zero on any failure.
"""

import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

API = "http://127.0.0.1:8000/api"
RECEIVER_IN_STACK = "http://receiver:8799"  # what jobs point at; reachable only via the proxy
ADMIN = os.environ["RECEIVER_ADMIN_TOKEN"]
PDF = b"%PDF-1.4\n% synthetic resume for the compose execution test\n"
RESULTS: list[dict] = []
NO_PROXY = urllib.request.ProxyHandler({})
NODE = "/usr/local/lib/python3.12/site-packages/playwright/driver/node"  # in the runner image
PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_probe.js")
PROXY_PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_probe.js")


def _api_reachable() -> bool:
    try:
        urllib.request.build_opener(NO_PROXY).open(API + "/health", timeout=5).close()
        return True
    except OSError:
        return False


def check(name: str, ok: bool, detail="") -> bool:
    RESULTS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)
    return ok


def sh(*args: str, timeout=300, stdin: bytes | None = None) -> str:
    r = subprocess.run(args, input=stdin, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {r.stderr.decode()[-600:]}")
    return r.stdout.decode()


def compose(*args: str, **kw) -> str:
    return sh("docker", "compose", *args, **kw)


def net_names(networks: dict) -> list[str]:
    prefix = os.environ.get("COMPOSE_PROJECT_NAME", "") + "_"
    return sorted(k.removeprefix(prefix) for k in networks)


def container_id(service: str) -> str:
    return compose("ps", "-q", service).strip()


# -- HTTP -------------------------------------------------------------------------------------
class Api:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            NO_PROXY, urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.csrf = ""

    def call(self, method, path, body=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(API + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", ctype)
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def ok(self, method, path, body=None, **kw):
        code, out = self.call(method, path, body, **kw)
        if code >= 300:
            raise RuntimeError(f"{method} {path} -> {code}: {out}")
        return out

    def upload(self, path, filename, content, fields):
        b = uuid.uuid4().hex
        parts = [
            f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, v in fields.items()
        ]
        parts.append(
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n".encode()
            + content
            + b"\r\n"
        )
        return self.ok("POST", path, raw=b"".join(parts) + f"--{b}--\r\n".encode(),
                       ctype=f"multipart/form-data; boundary={b}")  # fmt: skip


# The receiver has no published port (it lives on an internal network); the test reaches it
# from inside its own container.
_RECEIVER_CALL = """
import sys, urllib.request
method, path, body, token = sys.argv[1:5]
req = urllib.request.Request("http://127.0.0.1:8799" + path, data=body.encode() or None,
    method=method,
    headers={"X-Admin-Token": token, "Content-Type": "application/json"})
sys.stdout.write(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=30).read().decode())
"""


def receiver_raw(path: str, body: str = "", method: str = "GET") -> str:
    return compose("exec", "-T", "receiver", "python", "-c", _RECEIVER_CALL, method, path, body,
                   ADMIN)  # fmt: skip


def receiver(path, body=None):
    """GET /_admin/ledger; POST /_admin/config and /_admin/reset (as the receiver defines)."""
    method = "GET" if path == "ledger" else "POST"
    payload = json.dumps(body or {}) if method == "POST" else ""
    return json.loads(receiver_raw(f"/_admin/{path}", payload, method))


def ledger_for(slug):
    led = receiver("ledger")
    return {
        "accepted": sum(1 for a in led["acceptances"] if a["slug"] == slug),
        "disclosures": [d for d in led["disclosures"] if d["slug"] == slug],
        "acceptances": [a for a in led["acceptances"] if a["slug"] == slug],
        "challenges": led["challenges"],
    }


def wait_for(pred, timeout=120, every=1.0):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(every)
    return None


def runner_health() -> list:
    """[status, body] of the runner's /health, read inside the runner (works while the worker
    is down)."""
    js = ("require('http').get('http://127.0.0.1:9330/health', r => { let b = '';"
          " r.on('data', c => b += c); r.on('end', () => console.log(JSON.stringify([r.statusCode,"
          " JSON.parse(b)]))); }).on('error', e => console.log(JSON.stringify([0, {error: e.code}])))")  # fmt: skip
    return json.loads(compose("exec", "-T", "browser-runner", NODE, "-e", js).strip().splitlines()[-1])


def recreate_worker(**env_overrides) -> None:
    env = dict(os.environ, **env_overrides)
    subprocess.run(["docker", "compose", "up", "-d", "--force-recreate", "--no-deps", "worker"],
                   env=env, check=True, capture_output=True, timeout=300)  # fmt: skip
    wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 2)


def worker_py(code: str, **env) -> dict:
    """Run Python inside the worker container (it holds the control token and socket); the
    snippet prints one JSON line."""
    args = ["exec", "-T"] + [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
    out = compose(*args, "worker", "python", "-c", code)
    return json.loads(out.strip().splitlines()[-1])


def runner_node(script_path: str, **env) -> dict:
    args = ["exec", "-T"] + [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
    with open(script_path, "rb") as f:
        out = compose(*args, "browser-runner", NODE, "-", stdin=f.read())
    return json.loads(out.strip().splitlines()[-1])


def proxy_open_ports() -> list:
    return runner_node(PROBE)["proxy_open_ports"]


_OWN_SESSION = """
import json
from app.modules.execution.browser import RemoteBrowser
r = RemoteBrowser("receiver", 8799, True)
made = r._proxy("POST", "/sessions", {"allow": [["receiver", 8799]], "allow_private": [["receiver", 8799]]})
seen = r._proxy("GET", f"/sessions/{made['id']}/decisions")
print(json.dumps({"id": made["id"], "token": made["token"], "decisions": seen}))
"""

_DELETE_SESSION = """
import json, os
from app.core.config import get_settings
from app.modules.execution.browser import control_request
s = get_settings()
sid = os.environ["SID"]
d = control_request(s.egress_control_socket, s.egress_control_token, "DELETE", f"/sessions/{sid}")
g = control_request(s.egress_control_socket, s.egress_control_token, "GET", f"/sessions/{sid}/decisions")
no_token = control_request(s.egress_control_socket, "", "POST", "/sessions", {"allow": [["x", 1]]})
print(json.dumps({"delete": d[0], "after": g[0], "without_token": no_token[0]}))
"""


def canary_hits() -> int:
    return compose("logs", "--no-color", "canary").count("CANARY-HIT")


def worker_check() -> dict:
    out = compose("exec", "-T", "worker", "python", "-m", "app.modules.execution.container_check")
    return json.loads(out.strip().splitlines()[-1])


# -- candidate and applications ---------------------------------------------------------------
def candidate() -> Api:
    a = Api()
    code, out = a.call(
        "POST",
        "/auth/register",
        {
            "email": f"compose.{uuid.uuid4().hex[:10]}@example.com",
            "password": "synthetic-password-1",
        },
    )
    assert code == 201, out
    a.csrf = out["csrf_token"]
    a.ok("PUT", "/profile", {
        "full_name": "Sam Synthetic", "given_name": "Sam", "family_name": "Synthetic",
        "contact_email": "sam.synthetic@example.com", "phone": "+1 555 0100",
        "residence_country": "US", "residence_city": "Springfield", "links": [],
    })  # fmt: skip
    a.ok("POST", "/profile/work-authorizations", {
        "country_code": "US", "authorized": "yes",
        "sponsorship_needed_now": "no", "sponsorship_needed_future": "no",
    })  # fmt: skip
    a.upload("/documents", "resume.pdf", PDF, {"kind": "resume"})
    return a


def approve(a: Api, app_id: str, pkg: dict):
    assert not pkg["content"]["unresolved"], pkg["content"]["unresolved"]
    a.ok("POST", f"/applications/{app_id}/package/approve",
         {"version": pkg["version"], "content_hash": pkg["content_hash"]})  # fmt: skip


def generic_app(a: Api, slug: str) -> str:
    job = a.ok("POST", "/jobs", {"url": f"{RECEIVER_IN_STACK}/apply/{slug}",
                                 "title": "Clinic Assistant", "employer": "Example (fictional)"})  # fmt: skip
    html = receiver_raw(f"/apply/{slug}")
    a.ok("POST", f"/jobs/{job['job']['id']}/form", {"html": html})
    app_id = a.ok("POST", "/applications", {"job_id": job["job"]["id"]})["id"]
    a.ok("PUT", f"/applications/{app_id}/answers/hear_about", {"value": {"label": "Referral"}})
    pkg = a.ok("PUT", f"/applications/{app_id}/consents/privacy_ack", {"choice": "agree"})
    approve(a, app_id, pkg["package"])
    return app_id


def greenhouse_app(a: Api) -> str:
    job = a.ok("POST", "/jobs", {"url": f"{RECEIVER_IN_STACK}/gh/examplehealth/jobs/4012001",
                                 "title": "Patient Services Coordinator",
                                 "employer": "Example Health Network (fictional)"})  # fmt: skip
    a.ok("POST", f"/jobs/{job['job']['id']}/form/greenhouse")
    app_id = a.ok("POST", "/applications", {"job_id": job["job"]["id"]})["id"]
    for k, v in (("question_7004", {"label": "Referral"}), ("question_7005", {"label": "No"})):
        a.ok("PUT", f"/applications/{app_id}/answers/{k}", {"value": v})
    a.ok("PUT", f"/applications/{app_id}/consents/question_7009", {"choice": "withhold"})
    pkg = a.ok("PUT", f"/applications/{app_id}/consents/gdpr_processing_consent_given",
               {"choice": "agree"})  # fmt: skip
    approve(a, app_id, pkg["package"])
    return app_id


def queue(a: Api, app_id: str) -> None:
    a.ok("POST", f"/applications/{app_id}/transition", {"to": "queued"})


def attempt(a: Api, app_id: str) -> dict | None:
    atts = a.ok("GET", f"/applications/{app_id}/attempts")
    return atts[0] if atts else None


def final_state(a, app_id, states=("confirmed", "unknown", "rejected", "failed_safe", "abandoned"),
                timeout=150):  # fmt: skip
    return wait_for(lambda: (x := attempt(a, app_id)) and x["state"] in states and x, timeout)


# -- scenarios --------------------------------------------------------------------------------
def s_container_configuration():
    cid = container_id("browser-runner")
    i = json.loads(sh("docker", "inspect", cid))[0]
    hc = i["HostConfig"]
    nets = net_names(i["NetworkSettings"]["Networks"])
    check("runner: unprivileged user", i["Config"]["User"] == "10002:10002", i["Config"]["User"])
    check("runner: not privileged, all capabilities dropped",
          not hc["Privileged"] and hc["CapDrop"] == ["ALL"] and not hc["CapAdd"], hc["CapDrop"])  # fmt: skip
    check(
        "runner: read-only root, tmpfs /tmp", hc["ReadonlyRootfs"] and "/tmp" in (hc["Tmpfs"] or {})
    )
    sec = hc["SecurityOpt"] or []
    check("runner: no-new-privileges + custom seccomp profile",
          "no-new-privileges:true" in sec and any(s.startswith("seccomp=") for s in sec),
          [s[:40] for s in sec])  # fmt: skip
    check("runner: memory / CPU / pids limits",
          hc["Memory"] == 1536 * 2**20 and hc["NanoCpus"] == 1_500_000_000 and hc["PidsLimit"] == 512,
          {"memory": hc["Memory"], "nano_cpus": hc["NanoCpus"], "pids": hc["PidsLimit"]})  # fmt: skip
    mounts = [m["Destination"] for m in i["Mounts"]]
    check("runner: no host or volume mounts, no docker socket", mounts == [], mounts)
    check("runner: not on host network; only the two execution networks",
          hc["NetworkMode"] != "host" and nets == ["exec_control", "exec_egress"], nets)  # fmt: skip
    for svc in ("worker", "egress-proxy"):
        n = json.loads(sh("docker", "inspect", container_id(svc)))[0]["NetworkSettings"]["Networks"]
        print(f"     {svc} networks: {net_names(n)}")


def s_sandbox_selfcheck():
    c = worker_check()
    code, health = c["runner_health"]
    _, sc = c["runner_selfcheck"]
    renderers = [p for p in sc.get("processes", []) if p["type"] == "renderer"]
    check("sandbox: runner health reports a verified Chromium sandbox",
          code == 200 and health.get("sandbox_ok") is True, health)  # fmt: skip
    check("sandbox: renderers under seccomp-bpf, no --no-sandbox, no root",
          bool(renderers) and all(p["seccomp"] == "2" for p in renderers)
          and not any(p["no_sandbox_flag"] or p["uid"] == 0 for p in sc["processes"]),
          {"renderers": renderers, "runner_uid": sc.get("runner_uid")})  # fmt: skip
    return c


def s_browser_container_probe():
    with open(PROBE, "rb") as f:
        out = compose("exec", "-T", "browser-runner", NODE, "-", stdin=f.read())
    p = json.loads(out.strip().splitlines()[-1])
    check("probe: uid 10002, no capabilities, no-new-privs, seccomp filter",
          p["uid"] == 10002 and set(p["cap_eff"]) <= {"0"} and set(p["cap_bnd"]) <= {"0"}
          and p["no_new_privs"] == "1" and p["seccomp"] == "2",
          {k: p[k] for k in ("uid", "cap_eff", "cap_bnd", "no_new_privs", "seccomp")})  # fmt: skip
    check("probe: no database, broker, proxy-control or other credentials in the environment",
          p["credential_like_env"] == [], p["env_keys"])  # fmt: skip
    check("probe: no application code, storage, .env, docker socket or secrets mounted",
          p["paths_present"] == [], p["paths_present"])  # fmt: skip
    check("probe: root filesystem read-only, /tmp writable",
          not p["root_writable"] and not p["etc_writable"] and p["tmp_writable"])  # fmt: skip
    closed = {k: v for k, v in p["reach"].items() if k != "egress-proxy:3128"}
    check("probe: no external name resolution (no DNS side channel)",
          not p["external_dns"].startswith("resolved"), p["external_dns"])  # fmt: skip
    check("probe: database, broker, API, web, worker, receiver, canary, metadata, internet unreachable",
          all(v != "open" for v in closed.values()), closed)  # fmt: skip
    check("probe: of all 65535 TCP ports on the egress proxy, only 3128 accepts a connection",
          p["reach"]["egress-proxy:3128"] == "open" and p["proxy_open_ports"] == [3128],
          p["proxy_open_ports"])  # fmt: skip
    check("probe: the proxy's control socket is not visible in the browser container",
          not any(x.startswith("/run/egress-control") for x in p["paths_present"]), p["paths_present"])  # fmt: skip


def s_probe_detects_an_insecure_configuration():
    """Control for the probe above: the same probe and image, deliberately misconfigured (fake
    credentials in the environment, a mounted fake secret, attached to the application
    network), must report each problem. No real secret is used."""
    image = json.loads(sh("docker", "inspect", container_id("browser-runner")))[0]["Config"]["Image"]
    net = os.environ["COMPOSE_PROJECT_NAME"] + "_default"
    with tempfile.TemporaryDirectory() as d, open(PROBE, "rb") as f:
        with open(os.path.join(d, "fake-secret"), "w") as fs:
            fs.write("synthetic-not-a-secret")
        out = sh("docker", "run", "--rm", "-i", "--network", net, "-e", "SCAN=0",
                 "-e", "NOEFFORTS_DATABASE_URL=postgresql://fake:fake@postgres/fake",
                 "-e", "EGRESS_CONTROL_TOKEN=synthetic-control-token",
                 "-v", f"{d}:/run/secrets:ro", "--entrypoint", NODE, image, "-", stdin=f.read())  # fmt: skip
    p = json.loads(out.strip().splitlines()[-1])
    check("probe control: flags credential-like environment variables",
          {"NOEFFORTS_DATABASE_URL", "EGRESS_CONTROL_TOKEN"} <= set(p["credential_like_env"]),
          p["credential_like_env"])  # fmt: skip
    check("probe control: flags a mounted secrets directory", "/run/secrets" in p["paths_present"],
          p["paths_present"])  # fmt: skip
    check("probe control: flags a reachable database and broker",
          p["reach"]["postgres:5432"] == "open" and p["reach"]["redis:6379"] == "open",
          {k: p["reach"][k] for k in ("postgres:5432", "redis:6379")})  # fmt: skip


def s_control_plane_separation():
    """The proxy's management API is a UNIX socket on a volume only the proxy and the worker
    mount. Checked as reachability (TCP connects), not by HTTP status."""
    # 1. The worker manages its own session over the socket (token still required).
    sess = worker_py(_OWN_SESSION)
    check("control plane: worker created and inspected its session over the socket",
          bool(sess.get("id")) and sess["decisions"] == {"allowed": 0, "denied": []}, sess.get("decisions"))  # fmt: skip
    # 2. With those real credentials, the browser cannot use the proxy to reach management or
    #    the proxy itself; the session's own destination works (positive control).
    via = runner_node(PROXY_PROBE, SESSION_ID=sess["id"], SESSION_TOKEN=sess["token"])
    others = {k: v for k, v in via.items() if k != "CONNECT receiver:8799"}
    check("control plane: valid session credentials reach the allowed destination",
          via["CONNECT receiver:8799"].startswith("HTTP/1.1 200"), via["CONNECT receiver:8799"])  # fmt: skip
    check("control plane: management and the proxy itself are refused through the proxy (403)",
          all(" 403 " in v for v in others.values()), others)  # fmt: skip
    gone = worker_py(_DELETE_SESSION, SID=sess["id"])
    check("control plane: session deleted; control API still refuses without the token",
          gone == {"delete": 200, "after": 404, "without_token": 401}, gone)  # fmt: skip
    # 3. Sensitivity: the scan finds a listener bound to all interfaces on the proxy container.
    compose("exec", "-d", "egress-proxy", "python", "-c",
            "import socket,time; s=socket.socket(); s.bind(('0.0.0.0', 3199)); s.listen(); time.sleep(60)")  # fmt: skip
    seen = wait_for(lambda: 3199 in (p := proxy_open_ports()) and p, 20, 1)
    check("control plane: the scan detects a deliberately exposed listener (sensitivity control)",
          bool(seen) and 3199 in seen and 3129 not in seen, seen)  # fmt: skip
    # 4. Restarting the proxy does not bring a network listener back; the worker reconnects.
    compose("restart", "egress-proxy")
    healthy = wait_for(lambda: worker_check()["proxy_health"][0] == 200, 60, 2)
    after = proxy_open_ports()
    check("control plane: after a proxy restart only 3128 is open; worker reaches control again",
          bool(healthy) and after == [3128], {"open": after, "proxy_health": bool(healthy)})  # fmt: skip
    # 5. Normal approved execution still works after the restart.
    a = candidate()
    slug = f"ctl-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id)
    check("control plane: approved fixture run still confirmed (1 acceptance)",
          att and att["state"] == "confirmed" and ledger_for(slug)["accepted"] == 1, att and att["state"])  # fmt: skip


_OPEN_RUNNER_SESSION = """
import json
from app.modules.execution.browser import RemoteBrowser
r = RemoteBrowser("receiver", 8799, True)
ws = r.open()
print(json.dumps({"ws": ws, "runner": r.runner_session["id"], "proxy": r.proxy_session["id"]}))
"""

_RECONNECT_OLD = """
import json, os
from playwright.sync_api import sync_playwright
from app.core.config import get_settings
from app.modules.execution.browser import RemoteBrowser, control_request
s = get_settings()
out = {}
with sync_playwright() as p:
    try:
        p.chromium.connect(os.environ["WS"], timeout=10000, headers={"X-Runner-Token": s.browser_runner_token})
        out["reconnect"] = "connected"
    except Exception as e:
        out["reconnect"] = "refused: " + str(e).splitlines()[0][:120]
r = RemoteBrowser("receiver", 8799, True)
try:
    r._runner("DELETE", "/sessions/" + os.environ["RID"])
    out["old_runner_session"] = "still known"
except Exception as e:
    out["old_runner_session"] = "unknown: " + str(e)[:80]
pid = os.environ["PID_"]
out["proxy_delete"] = control_request(s.egress_control_socket, s.egress_control_token, "DELETE", "/sessions/" + pid)[0]
print(json.dumps(out))
"""


def s_runner_restart_recovery():
    """A runner restart (the same path as an OOM kill and restart) invalidates its sessions:
    the old endpoint and secret cannot attach to anything, temporary files are gone, and a new
    attempt runs normally."""
    old = worker_py(_OPEN_RUNNER_SESSION)
    check("recovery: a runner session was open before the restart",
          runner_health()[1].get("sessions") == 1, old.get("runner"))  # fmt: skip
    compose("restart", "browser-runner")
    wait_for(lambda: runner_health()[0] == 200, 120, 2)
    h = runner_health()
    check("recovery: restarted runner is healthy with no sessions", h[0] == 200 and h[1].get("sessions") == 0, h)
    r = worker_py(_RECONNECT_OLD, WS=old["ws"], RID=old["runner"], PID_=old["proxy"])
    check("recovery: the old endpoint and secret cannot attach to the restarted runner",
          r["reconnect"].startswith("refused") and r["old_runner_session"].startswith("unknown"), r)  # fmt: skip
    check("recovery: the old proxy session is removed by the worker's cleanup", r["proxy_delete"] == 200, r)
    tmp = compose("exec", "-T", "browser-runner", "sh", "-c", "ls -A /tmp").split()
    check("recovery: no browser profile or temp dir survived the restart",
          not [t for t in tmp if t.startswith("playwright")], tmp)  # fmt: skip
    a = candidate()
    slug = f"recover-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id)
    check("recovery: a new attempt after the restart is confirmed (1 acceptance)",
          att and att["state"] == "confirmed" and ledger_for(slug)["accepted"] == 1, att and att["state"])  # fmt: skip


_OBSERVE = """
import json
from app.modules.preparation import gh_readonly as ro
obs = ro.observe_page("examplehealth", "4012001", base="http://receiver:8799")
r = obs["rendered"]
print(json.dumps({"status": obs["status"], "bot_check": obs["bot_check"],
                  "blocked": obs["blocked_non_get"], "fields": len(r.fields) if r else None}))
"""


def s_readonly_observation_in_container():
    """Permission B's code path (observe only) through the real runner and session proxy, on
    the fixture: a page that POSTs on load is blocked, nothing is disclosed."""
    receiver("config", {"mode": "gh_post_on_load"})
    before = ledger_for("gh-examplehealth-4012001")
    obs = worker_py(_OBSERVE, NOEFFORTS_READONLY_GREENHOUSE_APPROVED="examplehealth/4012001")
    after = ledger_for("gh-examplehealth-4012001")
    receiver("config", {"mode": "normal"})
    check("read-only observation: form read in the isolated browser",
          obs.get("status") == 200 and obs.get("fields", 0) >= 8 and obs.get("bot_check") is False, obs)  # fmt: skip
    check("read-only observation: the page's own POST was blocked before leaving the browser",
          any(b["method"] == "POST" for b in obs.get("blocked", [])), obs.get("blocked"))  # fmt: skip
    check("read-only observation: nothing disclosed or accepted at the receiver",
          after["disclosures"] == before["disclosures"] and after["accepted"] == before["accepted"],
          {"disclosures": len(after["disclosures"]) - len(before["disclosures"])})  # fmt: skip


_OBSERVE_MAPPING = """
import json, os
from app.modules.preparation import gh_readonly as ro
api = json.loads(os.environ["API_JSON"])
obs = ro.observe_page("northwind", "5020001", base="http://receiver:8799", prefix="gh2",
                      api_json=api)
m = obs["mapping"]
pub = ro.publishable(api, {"name": api["company_name"]}, "5020001", obs)
try:
    ro.guard(pub, ro.sensitive_values("northwind", "5020001", api, None))
    guard = "passed"
except ro.Leak:
    guard = "refused"
print(json.dumps({"status": obs["status"], "by_status": {k: len(v) for k, v in m["by_status"].items()},
                  "unique": all(f["id_candidates"] == 1 for f in m["fields"]),
                  "visible": [f["control"]["visible"] for f in m["fields"] if f["control"]],
                  "blocked": obs["blocked_non_get"], "guard": guard,
                  "incomplete": obs["rendering"]["may_be_incomplete"]}))
"""


def s_readonly_mapping_in_container():
    """The follow-up observation's code path (B2: per-field mapping evidence, DOM reads only)
    through the real runner and session proxy, on the second (v2) fixture."""
    slug = "gh2-northwind-5020001"
    api = receiver_raw("/gh2-api/v1/boards/northwind/jobs/5020001?questions=true")
    before = ledger_for(slug)
    obs = worker_py(_OBSERVE_MAPPING, API_JSON=api,
                    NOEFFORTS_READONLY_GREENHOUSE_APPROVED="northwind/5020001")  # fmt: skip
    after = ledger_for(slug)
    check("read-only mapping: every API field has one id-matched, labelled control",
          obs.get("status") == 200 and obs.get("by_status") == {"mapped": 12} and obs.get("unique"),
          obs)  # fmt: skip
    check("read-only mapping: visibility read in the isolated browser (hidden question seen)",
          False in obs.get("visible", []) and True in obs.get("visible", []), obs.get("visible"))  # fmt: skip
    check("read-only mapping: the published summary passes the privacy guard",
          obs.get("guard") == "passed" and obs.get("incomplete") is False, obs)  # fmt: skip
    check("read-only mapping: nothing disclosed or accepted at the receiver",
          after["disclosures"] == before["disclosures"] and after["accepted"] == before["accepted"],
          {"disclosures": len(after["disclosures"]) - len(before["disclosures"])})  # fmt: skip


def s_greenhouse_security_code_flow():
    receiver("config", {"mode": "gh_security_code"})
    slug = "gh-examplehealth-4012001"
    before = ledger_for(slug)
    a = candidate()
    app_id = greenhouse_app(a)
    queue(a, app_id)
    cp = wait_for(
        lambda: (
            (x := attempt(a, app_id))
            and next((c for c in x["checkpoints"] if c["status"] == "open"), None)
        ),
        120,
    )
    check("greenhouse: security-code checkpoint opened in the isolated browser", bool(cp))
    if not cp:
        return
    mid = ledger_for(slug)
    check("greenhouse: not accepted before the code", mid["accepted"] == before["accepted"])
    code = mid["challenges"][-1]["code"]
    a.ok("POST", f"/applications/{app_id}/checkpoints/{cp['id']}/code",
         {"round": cp["round"], "code": code})  # fmt: skip
    att = final_state(a, app_id)
    after = ledger_for(slug)
    check("greenhouse: confirmed", att and att["state"] == "confirmed", att and att["state"])
    check("greenhouse: receiver counted exactly one more acceptance",
          after["accepted"] == before["accepted"] + 1,
          {"before": before["accepted"], "after": after["accepted"]})  # fmt: skip
    pkg = a.ok("GET", f"/applications/{app_id}/package")["package"]["content"]
    new_uploads = after["disclosures"][len(before["disclosures"]) :]
    digests = {json.loads(d["detail"])["sha256"] for d in new_uploads if d["kind"] == "upload"}
    check("greenhouse: one attachment disclosure with the approved document's bytes",
          len(new_uploads) == 1 and digests == {pkg["documents"][0]["sha256"]}, len(new_uploads))  # fmt: skip
    ev = {e["kind"]: e for e in (att or {}).get("evidence", [])}
    check("greenhouse: confirmation evidence + disclosure evidence, each with a retention date",
          "receipt" in ev and "disclosure" in ev
          and all(e.get("retain_until") for e in att["evidence"]),
          sorted(ev))  # fmt: skip
    check(
        "greenhouse: code not stored after use",
        all(c["status"] != "open" for c in attempt(a, app_id)["checkpoints"]),
    )
    logs = compose("logs", "--no-color")
    leaked = [name for name, v in (("security code", code),
                                   ("runner token", os.environ["BROWSER_RUNNER_TOKEN"]),
                                   ("proxy control token", os.environ["EGRESS_CONTROL_TOKEN"]),
                                   ("receiver admin token", ADMIN)) if v in logs]  # fmt: skip
    check("logs: no security code or service token in any service's logs", leaked == [], leaked)
    code_del, _ = a.call("DELETE", f"/applications/{app_id}/evidence")
    check("cleanup: evidence can be deleted after the attempt",
          code_del == 200 and attempt(a, app_id)["evidence"] == [], code_del)  # fmt: skip
    h = worker_check()["runner_health"][1]
    check("cleanup: no browser session left open", h.get("sessions") == 0, h)
    tmp = compose("exec", "-T", "browser-runner", "sh", "-c", "ls -A /tmp").split()
    check("cleanup: no browser profile left in the runner's /tmp",
          not [t for t in tmp if t.startswith("playwright")], tmp)  # fmt: skip


def s_hostile_page():
    before = canary_hits()
    receiver("config", {"mode": "hostile", "canary": "http://canary:8798"})
    a = candidate()
    app_id = generic_app(a, f"hostile-{uuid.uuid4().hex[:6]}")
    queue(a, app_id)
    att = final_state(a, app_id)
    receiver("config", {"mode": "normal"})
    eg = next((e["data"] for e in (att or {}).get("evidence", []) if e["kind"] == "egress"), {})
    hits = canary_hits() - before
    check("hostile page: still submitted to the approved destination",
          att and att["state"] == "confirmed", att and att["state"])  # fmt: skip
    check("hostile page: canary on an internal network received nothing", hits == 0, hits)
    check("hostile page: blocked requests recorded", eg.get("blocked_requests", 0) >= 1, eg)


def s_infrastructure_only_egress():
    """The worker's in-process interception switched off (test-only setting): only the runner's
    launch settings and the per-session proxy stand between the hostile page and the canary."""
    recreate_worker(EXEC_TEST_DISABLE_INTERCEPTION="true")
    try:
        before = canary_hits()
        receiver("config", {"mode": "hostile", "canary": "http://canary:8798"})
        a = candidate()
        slug = f"nointercept-{uuid.uuid4().hex[:6]}"
        app_id = generic_app(a, slug)
        queue(a, app_id)
        att = final_state(a, app_id)
        receiver("config", {"mode": "normal"})
        eg = next((e["data"] for e in (att or {}).get("evidence", []) if e["kind"] == "egress"), {})
        hits = canary_hits() - before
        check("no interception: approved destination still works (confirmed, 1 acceptance)",
              att and att["state"] == "confirmed" and ledger_for(slug)["accepted"] == 1,
              att and att["state"])  # fmt: skip
        check("no interception: the in-process layer really was off (0 requests blocked by it)",
              eg.get("blocked_requests", 0) == 0, eg)  # fmt: skip
        check("no interception: canary received nothing", hits == 0, hits)
        check("no interception: the session proxy denied the off-destination requests",
              any(d.startswith("canary:") for d in eg.get("proxy_denied", [])), eg.get("proxy_denied"))  # fmt: skip
    finally:
        recreate_worker(EXEC_TEST_DISABLE_INTERCEPTION="false")


def s_unknown_then_duplicate_delivery():
    receiver("config", {"mode": "drop_after_accept"})
    a = candidate()
    slug = f"unknown-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id)
    receiver("config", {"mode": "normal"})
    check("unknown: accepted but unanswered submit is 'unknown'",
          att and att["state"] == "unknown", att and att["state"])  # fmt: skip
    check(
        "unknown: application quarantined as submitted_unconfirmed",
        a.ok("GET", f"/applications/{app_id}")["state"] == "submitted_unconfirmed",
    )
    n = ledger_for(slug)["accepted"]
    compose("exec", "-T", "worker", "python", "-c",
            "import sys; from app.worker import execute_attempt; "
            f"execute_attempt.delay('{att['id']}')")  # fmt: skip
    time.sleep(15)  # bounded observation window for a duplicate send
    check("duplicate delivery after an ambiguous outcome: no second send",
          ledger_for(slug)["accepted"] == n == 1 and attempt(a, app_id)["state"] == "unknown",
          {"accepted": ledger_for(slug)["accepted"]})  # fmt: skip
    logs = compose("logs", "--no-color", "--since", "60s", "worker")
    check("duplicate delivery: the worker ignored it", "'ignored'" in logs)


def s_runner_lost_during_submission():
    receiver("config", {"mode": "delay", "delay_s": 20})
    a = candidate()
    slug = f"loss-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    sending = wait_for(lambda: (x := attempt(a, app_id)) and x["state"] == "sending", 120, 0.3)
    check("process loss: attempt reached the submit step", bool(sending))
    compose("kill", "browser-runner")
    att = final_state(a, app_id, timeout=90)
    check("process loss: browser container killed mid-submit -> 'unknown', never resent",
          att and att["state"] == "unknown", att and att["state"])  # fmt: skip
    compose("up", "-d", "--no-deps", "browser-runner")
    healthy = wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)
    check("process loss: runner restarts healthy", bool(healthy))
    time.sleep(25)  # past the receiver's delay
    n = ledger_for(slug)["accepted"]
    check("process loss: at most one acceptance at the receiver", n <= 1, n)
    receiver("config", {"mode": "normal", "delay_s": 0})


def s_worker_killed_mid_submit():
    """The orchestrating worker dies while the final POST is in flight: the runner must close
    the orphaned browser, the attempt must end 'unknown' (swept after the lease), and nothing
    may be sent again."""
    receiver("config", {"mode": "delay", "delay_s": 20})
    a = candidate()
    slug = f"wkill-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    sending = wait_for(lambda: (x := attempt(a, app_id)) and x["state"] == "sending", 120, 0.3)
    check("worker loss: attempt reached the submit step", bool(sending))
    compose("kill", "worker")
    closed = wait_for(lambda: runner_health()[1].get("sessions") == 0, 20, 0.5)
    check("worker loss: runner closed the orphaned browser within 20 s", bool(closed), runner_health())
    compose("up", "-d", "--no-deps", "worker")
    att = final_state(a, app_id, timeout=180)
    check("worker loss: swept to 'unknown' after the lease, not retried",
          att and att["state"] == "unknown" and att["retry_count"] == 0,
          att and (att["state"], att["outcome"]))  # fmt: skip
    check("worker loss: application quarantined as submitted_unconfirmed",
          a.ok("GET", f"/applications/{app_id}")["state"] == "submitted_unconfirmed")
    n = ledger_for(slug)["accepted"]
    check("worker loss: at most one acceptance at the receiver (no resend)", n <= 1, n)
    receiver("config", {"mode": "normal", "delay_s": 0})
    wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 2)


def s_runner_unavailable():
    compose("stop", "browser-runner")
    a = candidate()
    slug = f"down-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id, timeout=120)
    compose("up", "-d", "--no-deps", "browser-runner")
    check("isolation startup failure: runner down -> failed_safe, nothing disclosed",
          att and att["state"] == "failed_safe" and ledger_for(slug)["disclosures"] == [],
          att and (att["state"], att["outcome"]))  # fmt: skip
    wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)


def s_sandbox_unavailable():
    env = dict(os.environ, BROWSER_SECCOMP_PROFILE="./compose_tests/seccomp-docker-default.json")
    subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "browser-runner"],
                   env=env, check=True, capture_output=True, timeout=300)  # fmt: skip
    rep = wait_for(
        lambda: (c := worker_check()["runner_health"]) and c[0] in (200, 503) and c, 120, 3
    )
    check("sandbox unavailable: with Docker's default seccomp the runner reports no sandbox",
          rep and rep[0] == 503 and rep[1].get("sandbox_ok") is False, rep)  # fmt: skip
    a = candidate()
    slug = f"nosandbox-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id, timeout=120)
    check("sandbox unavailable: attempt refused (failed_safe), no --no-sandbox fallback",
          att and att["state"] == "failed_safe" and ledger_for(slug)["disclosures"] == [],
          att and att["outcome"])  # fmt: skip
    compose("up", "-d", "--no-deps", "--force-recreate", "browser-runner")
    wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)


def s_memory_exhaustion():
    receiver("config", {"mode": "hog"})
    a = candidate()
    slug = f"hog-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id, timeout=150)
    receiver("config", {"mode": "normal"})
    check("memory exhaustion: page that eats memory stops safely, nothing accepted",
          att and att["state"] in ("failed_safe", "abandoned") and ledger_for(slug)["accepted"] == 0,
          att and (att["state"], att["outcome"]))  # fmt: skip
    i = json.loads(sh("docker", "inspect", container_id("browser-runner")))[0]["State"]
    up = wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)
    check("memory exhaustion: contained by the container limit; runner serving again",
          bool(up), {"oom_killed": i.get("OOMKilled"), "restarts": i.get("RestartCount")})  # fmt: skip
    tmp = compose("exec", "-T", "browser-runner", "sh", "-c", "ls -A /tmp").split()
    check("memory exhaustion: no browser profile left after recovery",
          not [t for t in tmp if t.startswith("playwright")], tmp)  # fmt: skip
    b = candidate()
    slug2 = f"after-hog-{uuid.uuid4().hex[:6]}"
    app2 = generic_app(b, slug2)
    queue(b, app2)
    att2 = final_state(b, app2)
    check("memory exhaustion: a new attempt after recovery is confirmed (1 acceptance)",
          att2 and att2["state"] == "confirmed" and ledger_for(slug2)["accepted"] == 1, att2 and att2["state"])  # fmt: skip
    atts = a.ok("GET", f"/applications/{app_id}/attempts")
    check("memory exhaustion: the interrupted attempt was not replayed (one attempt, retry 0, 0 accepted)",
          len(atts) == 1 and atts[0]["retry_count"] == 0 and ledger_for(slug)["accepted"] == 0,
          [(x["state"], x["retry_count"]) for x in atts])  # fmt: skip


def s_session_time_limit():
    limit = int(os.environ.get("BROWSER_MAX_SESSION_SECONDS", "0"))
    a = candidate()
    slug = f"ttl-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)  # form captured first; only the worker's load is slowed
    receiver("config", {"form_delay_s": limit + 20})
    queue(a, app_id)
    att = final_state(a, app_id, timeout=limit + 90)
    receiver("config", {"form_delay_s": 0})
    check(f"execution-time limit: runner ends a session after {limit}s; attempt stops safely",
          att and att["state"] == "failed_safe" and ledger_for(slug)["disclosures"] == [],
          att and (att["state"], att["outcome"]))  # fmt: skip


SCENARIOS = [
    s_container_configuration,
    s_sandbox_selfcheck,
    s_browser_container_probe,
    s_probe_detects_an_insecure_configuration,
    s_control_plane_separation,
    s_readonly_observation_in_container,
    s_readonly_mapping_in_container,
    s_greenhouse_security_code_flow,
    s_hostile_page,
    s_infrastructure_only_egress,
    s_unknown_then_duplicate_delivery,
    s_runner_lost_during_submission,
    s_worker_killed_mid_submit,
    s_runner_unavailable,
    s_sandbox_unavailable,
    s_memory_exhaustion,
    s_runner_restart_recovery,
    s_session_time_limit,
]


def main():
    receiver("reset")
    for s in SCENARIOS:
        print(f"--- {s.__name__}", flush=True)
        try:
            s()
        except Exception as e:  # noqa: BLE001 - report and continue with the next scenario
            check(f"{s.__name__} raised", False, repr(e)[:500])
        if not wait_for(_api_reachable, 60, 2):
            check(f"API reachable after {s.__name__}", False, compose("ps", "-a")[-1500:])
    failed = [r for r in RESULTS if not r["ok"]]
    print(json.dumps({"checks": len(RESULTS), "failed": len(failed)}))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
