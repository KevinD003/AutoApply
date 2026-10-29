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
    # Quoted values and `export` lines are read the way Compose reads them.
    parsed = checker().parse("export AUDIT_REF_KEY='abc'\n# AUDIT_REF_KEY=no\nX = \"y\"\n")
    assert parsed == {"AUDIT_REF_KEY": "abc", "X": "y"}


def test_backups_are_never_committed():
    for path in ("backups/noefforts-20261029.dump", "backups/storage-20261029.tgz"):
        ignored = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
        assert ignored.returncode == 0, path
