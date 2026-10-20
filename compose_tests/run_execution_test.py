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
import time
import urllib.error
import urllib.request
import uuid

API = "http://127.0.0.1:8000/api"
RECEIVER = "http://127.0.0.1:8799"  # host view (admin + fetching fixture HTML)
RECEIVER_IN_STACK = "http://receiver:8799"  # what jobs point at; reachable only via the proxy
ADMIN = os.environ["RECEIVER_ADMIN_TOKEN"]
PDF = b"%PDF-1.4\n% synthetic resume for the compose execution test\n"
RESULTS: list[dict] = []
NO_PROXY = urllib.request.ProxyHandler({})


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


def receiver(path, body=None):
    req = urllib.request.Request(
        f"{RECEIVER}/_admin/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"X-Admin-Token": ADMIN, "Content-Type": "application/json"},
    )
    with urllib.request.build_opener(NO_PROXY).open(req, timeout=30) as r:
        return json.loads(r.read())


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
    with urllib.request.build_opener(NO_PROXY).open(f"{RECEIVER}/apply/{slug}", timeout=30) as r:
        html = r.read().decode()
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
    nets = sorted(k.split("_", 1)[-1] for k in i["NetworkSettings"]["Networks"])
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
        print(f"     {svc} networks: {sorted(k.split('_', 1)[-1] for k in n)}")


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
    node = "/usr/local/lib/python3.12/site-packages/playwright/driver/node"
    with open(os.path.join(os.path.dirname(__file__), "browser_probe.js"), "rb") as f:
        out = compose("exec", "-T", "browser-runner", node, "-", stdin=f.read())
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
    check("probe: database, broker, API, web, receiver, canary, metadata, internet unreachable",
          all(v != "open" for v in closed.values()), closed)  # fmt: skip
    check("probe: only the proxy port is reachable; its control API refuses without the token",
          p["reach"]["egress-proxy:3128"] == "open" and p["proxy_control_without_token"] == 401,
          {"proxy": p["reach"]["egress-proxy:3128"], "control": p["proxy_control_without_token"]})  # fmt: skip


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
    code_del, _ = a.call("DELETE", f"/applications/{app_id}/evidence")
    check("cleanup: evidence can be deleted after the attempt",
          code_del == 200 and attempt(a, app_id)["evidence"] == [], code_del)  # fmt: skip
    h = worker_check()["runner_health"][1]
    check("cleanup: no browser session left open", h.get("sessions") == 0, h)
    tmp = compose("exec", "-T", "browser-runner", "sh", "-c", "ls -A /tmp").split()
    check("cleanup: no browser profile left in the runner's /tmp",
          not [t for t in tmp if t.startswith("playwright")], tmp)  # fmt: skip


def s_hostile_page():
    receiver("config", {"mode": "hostile", "canary": "http://canary:8798"})
    a = candidate()
    app_id = generic_app(a, f"hostile-{uuid.uuid4().hex[:6]}")
    queue(a, app_id)
    att = final_state(a, app_id)
    receiver("config", {"mode": "normal"})
    eg = next((e["data"] for e in (att or {}).get("evidence", []) if e["kind"] == "egress"), {})
    hits = compose("logs", "--no-color", "canary").count("CANARY-HIT")
    check("hostile page: still submitted to the approved destination",
          att and att["state"] == "confirmed", att and att["state"])  # fmt: skip
    check("hostile page: canary on an internal network received nothing", hits == 0, hits)
    check("hostile page: blocked requests recorded", eg.get("blocked_requests", 0) >= 1, eg)


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
    compose("up", "-d", "browser-runner")
    healthy = wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)
    check("process loss: runner restarts healthy", bool(healthy))
    time.sleep(25)  # past the receiver's delay
    n = ledger_for(slug)["accepted"]
    check("process loss: at most one acceptance at the receiver", n <= 1, n)
    receiver("config", {"mode": "normal", "delay_s": 0})


def s_runner_unavailable():
    compose("stop", "browser-runner")
    a = candidate()
    slug = f"down-{uuid.uuid4().hex[:6]}"
    app_id = generic_app(a, slug)
    queue(a, app_id)
    att = final_state(a, app_id, timeout=120)
    compose("up", "-d", "browser-runner")
    check("isolation startup failure: runner down -> failed_safe, nothing disclosed",
          att and att["state"] == "failed_safe" and ledger_for(slug)["disclosures"] == [],
          att and (att["state"], att["outcome_detail"]))  # fmt: skip
    wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)


def s_sandbox_unavailable():
    env = dict(os.environ, BROWSER_SECCOMP_PROFILE="./compose_tests/seccomp-docker-default.json")
    subprocess.run(["docker", "compose", "up", "-d", "--force-recreate", "browser-runner"],
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
          att and att["outcome_detail"])  # fmt: skip
    compose("up", "-d", "--force-recreate", "browser-runner")
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
          att and (att["state"], att["outcome_detail"]))  # fmt: skip
    i = json.loads(sh("docker", "inspect", container_id("browser-runner")))[0]["State"]
    up = wait_for(lambda: worker_check()["runner_health"][0] == 200, 120, 3)
    check("memory exhaustion: contained by the container limit; runner serving again",
          bool(up), {"oom_killed": i.get("OOMKilled"), "restarts": i.get("RestartCount")})  # fmt: skip


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
          att and (att["state"], att["outcome_detail"]))  # fmt: skip


SCENARIOS = [
    s_container_configuration,
    s_sandbox_selfcheck,
    s_browser_container_probe,
    s_greenhouse_security_code_flow,
    s_hostile_page,
    s_unknown_then_duplicate_delivery,
    s_runner_lost_during_submission,
    s_runner_unavailable,
    s_sandbox_unavailable,
    s_memory_exhaustion,
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
    failed = [r for r in RESULTS if not r["ok"]]
    print(json.dumps({"checks": len(RESULTS), "failed": len(failed)}))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
