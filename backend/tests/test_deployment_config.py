"""The owner's Docker Compose setup (docs/deployment.md): secrets, ports, start order, checker.

Reads docker-compose.yml, .env.example and backend/Dockerfile as files and runs
scripts/check_env.py; nothing here starts Docker (the docker-smoke CI job does)."""

import importlib.util
import re
import secrets
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_env.py"


def checker():
    spec = importlib.util.spec_from_file_location("check_env", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def run_checker(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(CHECKER), str(path)], capture_output=True, text=True
    )


def good_values() -> dict[str, str]:
    return {
        "AUDIT_REF_KEY": secrets.token_hex(32),
        "BROWSER_RUNNER_TOKEN": secrets.token_hex(16),
        "EGRESS_CONTROL_TOKEN": secrets.token_hex(16),
        "POSTGRES_PASSWORD": secrets.token_hex(12),
    }


def write_env(tmp_path: Path, values: dict[str, str]) -> Path:
    path = tmp_path / ".env"
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    return path


def test_every_required_compose_variable_is_in_the_example_and_the_checker():
    text = (ROOT / "docker-compose.yml").read_text()
    required = set(re.findall(r"\$\{([A-Z_]+):\?", text))
    assert required == {"AUDIT_REF_KEY", "BROWSER_RUNNER_TOKEN", "EGRESS_CONTROL_TOKEN"}
    assert set(checker().REQUIRED) == required
    example = checker().parse((ROOT / ".env.example").read_text())
    assert required <= set(example)  # `cp .env.example .env` names every one


# .env.example keys Compose does not pass on as written, and why.
NOT_PASSED = {
    "NOEFFORTS_ENV": "Compose runs the default environment; the test overlay sets its own",
    "NOEFFORTS_DATABASE_URL": "set by Compose to the postgres service",
    "NOEFFORTS_REDIS_URL": "set by Compose to the redis service",
    "NOEFFORTS_STORAGE_DIR": "the storage volume (/data/storage, the Dockerfile's)",
    "NOEFFORTS_AUDIT_REF_KEY": "Compose takes AUDIT_REF_KEY",
    "NOEFFORTS_CORS_ORIGINS": "set by Compose to the web app's address",
    "NOEFFORTS_BROWSER_ISOLATION": "Compose uses the browser-runner container",
    "NOEFFORTS_FAKE_API_TOKEN": "fixture only",
    "NOEFFORTS_BACKEND_URL": "the web app's build argument",
}


def test_every_owner_setting_in_the_example_reaches_the_api_and_the_worker():
    """Compose reads .env only to fill in docker-compose.yml: a setting it does not name never
    reaches a container, so the documented switches (email, boards, drafting, discovery) would
    stay off whatever .env says (found while checking D94)."""
    example = {k for k in checker().parse((ROOT / ".env.example").read_text())
               if k.startswith("NOEFFORTS_")}  # fmt: skip
    services = compose()["services"]
    for name in ("backend", "worker"):
        env = services[name]["environment"]
        for key in sorted(example - set(NOT_PASSED)):
            assert key in env, (name, key)
            assert str(env[key]).startswith(f"${{{key}:-"), (name, key)  # from .env, or a default
    assert set(NOT_PASSED) <= example
    assert "env_file" not in services["backend"] and "env_file" not in services["worker"]


def test_every_published_port_is_bound_to_this_machine_only():
    published = {name: service.get("ports", []) for name, service in compose()["services"].items()}
    assert published["backend"] and published["frontend"]
    for name, ports in published.items():
        for port in ports:
            assert str(port).startswith("127.0.0.1:"), (name, port)
    overlay = yaml.safe_load((ROOT / "docker-compose.execution-test.yml").read_text())
    assert not any(s.get("ports") for s in overlay["services"].values())


def test_the_worker_and_web_app_start_only_once_the_api_is_healthy():
    services = compose()["services"]
    probe = " ".join(services["backend"]["healthcheck"]["test"])
    assert "/api/health" in probe and "ProxyHandler({})" in probe
    for name in ("worker", "frontend"):
        assert services[name]["depends_on"]["backend"] == {"condition": "service_healthy"}, name
    # Healthy implies migrated: the API starts only after `alembic upgrade head` succeeds.
    cmd = (ROOT / "backend" / "Dockerfile").read_text().splitlines()[-1]
    assert "alembic upgrade head && uvicorn" in cmd


def test_the_example_file_is_refused_until_its_secrets_are_set():
    result = run_checker(ROOT / ".env.example")
    assert result.returncode == 1
    for key in ("AUDIT_REF_KEY: empty", "BROWSER_RUNNER_TOKEN: still the example placeholder",
                "EGRESS_CONTROL_TOKEN: still the example placeholder"):  # fmt: skip
        assert key in result.stdout, key


def test_a_good_file_passes_and_no_value_is_printed(tmp_path):
    values = good_values()
    result = run_checker(write_env(tmp_path, values))
    assert result.returncode == 0, result.stdout
    assert "OK (0 warning(s))" in result.stdout
    for value in values.values():
        assert value not in result.stdout + result.stderr


def test_a_bad_file_fails_without_printing_its_values(tmp_path):
    values = good_values() | {"BROWSER_RUNNER_TOKEN": "tooshort1", "POSTGRES_PASSWORD": "postgres"}
    result = run_checker(write_env(tmp_path, values))
    assert result.returncode == 1
    assert "BROWSER_RUNNER_TOKEN: shorter than 24 characters" in result.stdout
    assert "POSTGRES_PASSWORD: the default" in result.stdout
    for value in values.values():
        assert value not in result.stdout + result.stderr
    assert run_checker(tmp_path / "missing.env").returncode == 1


def test_reused_secrets_missing_keys_and_outbound_switches():
    check = checker().check
    same = secrets.token_hex(32)
    errors, _ = check(good_values() | {"AUDIT_REF_KEY": same, "BROWSER_RUNNER_TOKEN": same})
    assert any("the same value" in e for e in errors)
    errors, _ = check(good_values() | {"EGRESS_CONTROL_TOKEN": "x" * 40})
    assert errors == ["EGRESS_CONTROL_TOKEN: still the example placeholder; set your own secret"]
    errors, _ = check({k: v for k, v in good_values().items() if k != "AUDIT_REF_KEY"})
    assert errors == ["AUDIT_REF_KEY: missing (docker-compose.yml requires it)"]
    errors, warnings = check(good_values() | {"NOEFFORTS_DISCOVERY_PROVIDERS": '["freehire"]'})
    assert errors == [] and any("NOEFFORTS_DISCOVERY_PROVIDERS" in w for w in warnings)
    _, warnings = check(good_values() | {"NOEFFORTS_DISCOVERY_PROVIDERS": "[]"})
    assert warnings == []
    for key in ("NOEFFORTS_EMAIL_ENABLED", "NOEFFORTS_BOARD_SOURCES_ENABLED"):
        _, warnings = check(good_values() | {key: "true"})
        assert any(key in w for w in warnings), key
        _, warnings = check(good_values() | {key: "false"})
        assert warnings == [], key
    # Quoted values and `export` lines are read the way Compose reads them.
    parsed = checker().parse("export AUDIT_REF_KEY='abc'\n# AUDIT_REF_KEY=no\nX = \"y\"\n")
    assert parsed == {"AUDIT_REF_KEY": "abc", "X": "y"}


def test_backups_are_never_committed():
    for path in ("backups/noefforts-20261029.dump", "backups/storage-20261029.tgz"):
        ignored = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
        assert ignored.returncode == 0, path


def _verify_copy(tmp_path: Path) -> Path:
    """The verify script and what it reads, in a scratch directory (the repository's own .env
    is never created or read)."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for name in ("verify-local.sh", "check_env.py", "docker-smoke.sh", "smoke_lib.sh"):
        (root / "scripts" / name).write_text((ROOT / "scripts" / name).read_text())
    (root / "docker-compose.yml").write_text((ROOT / "docker-compose.yml").read_text())
    return root


def _run_verify(root: Path, path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(root / "scripts" / "verify-local.sh")],
        env={"PATH": path, "HOME": str(root)},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_verify_local_ends_with_a_safe_summary_when_docker_is_missing(tmp_path):
    root = _verify_copy(tmp_path)
    result = _run_verify(root, "/usr/bin:/bin")
    if Path("/usr/bin/docker").exists() or Path("/bin/docker").exists():
        return  # this machine has Docker on that path; the next test covers the summary
    assert result.returncode == 1
    out = result.stdout
    assert "===== NoEfforts verification summary (safe to share) =====" in out
    assert "result: FAILED at step: prerequisites" in out and "docker: unavailable" in out


def test_verify_local_reports_each_step_and_never_a_value(tmp_path):
    import socket

    root = _verify_copy(tmp_path)
    values = good_values()
    write_env(root, values)
    fake = tmp_path / "bin"
    fake.mkdir()
    # A stand-in for the Docker CLI: answers the version and config calls, nothing else.
    (fake / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n  "compose version --short") echo 2.40.0;;\n'
        '  "compose version") echo "Docker Compose version v2.40.0";;\n'
        '  "compose config --quiet") exit 0;;\n  "version --format"*) echo 28.0.0;;\n'
        "  *) exit 3;;\nesac\n"
    )
    (fake / "docker").chmod(0o755)
    held = socket.socket()
    try:
        held.bind(("127.0.0.1", 8000))  # one of the stack's ports, in use for this run
        held.listen()
    except OSError:
        pass  # already in use: the script stops there either way
    try:
        result = _run_verify(root, f"{fake}:/usr/bin:/bin")
    finally:
        held.close()
    out = result.stdout + result.stderr
    assert result.returncode == 1
    for step in ("prerequisites", "env check", "compose config"):
        assert f"passed: {step}" in out, step
    assert "result: FAILED at step: ports free" in out
    assert "docker: 28.0.0" in out and "compose: 2.40.0" in out
    for value in values.values():
        assert value not in out


def test_the_greenhouse_pilot_override_changes_only_what_it_says():
    """D102: docker-compose.pilot.yml puts the API and worker in production mode and gives the
    egress proxy, alone, an outbound network. The browser stays on its internal networks, the
    pilot's switch and owner come from .env through the base file, and nothing else changes."""
    base = compose()
    pilot = yaml.safe_load((ROOT / "docker-compose.pilot.yml").read_text())
    assert set(pilot["services"]) == {"backend", "worker", "egress-proxy"}
    for name in ("backend", "worker"):
        env = pilot["services"][name]["environment"]
        assert env == {"NOEFFORTS_ENV": "production",
                       "NOEFFORTS_LIVE_OWNER_EMAILS": "${NOEFFORTS_LIVE_OWNER_EMAILS:?name your "
                       "NoEfforts account in .env}"}  # fmt: skip
        assert set(pilot["services"][name]) == {"environment"}
        base_env = base["services"][name]["environment"]
        assert base_env["NOEFFORTS_LIVE_GREENHOUSE_ENABLED"] == (
            "${NOEFFORTS_LIVE_GREENHOUSE_ENABLED:-false}"
        )
        assert base_env["NOEFFORTS_BROWSER_ISOLATION"] == "container"
    assert pilot["services"]["egress-proxy"] == {"networks": ["exec_egress", "egress_out"]}
    assert pilot["networks"] == {"egress_out": {}}
    assert "egress_out" not in base["services"]["browser-runner"]["networks"]
    assert base["networks"]["exec_egress"] == {"internal": True}
