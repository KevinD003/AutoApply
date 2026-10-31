"""The production image installs the project's dependencies only (`uv sync --no-dev`): application
code that imports a development-only package starts in every test run and fails in the image.
That happened once (D101's Gmail reader imported httpx, a test dependency; CI #140's Docker
jobs). Read from the source: no module under app/ imports a package that only the `dev` group
provides."""

import ast
import importlib.metadata
import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _names(requirements: list[str]) -> set[str]:
    return {re.split(r"[\[<>=!~ ;]", r, maxsplit=1)[0].strip().lower() for r in requirements}


def _runtime_closure(roots: set[str]) -> set[str]:
    """The runtime dependencies and everything they require (extras named in the roots too)."""
    seen, todo = set(), list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            requires = importlib.metadata.requires(name) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for r in requires:
            if "extra ==" in r:
                continue  # an optional extra; the roots name any they use
            todo.append(_names([r]).pop())
    return {n.replace("_", "-") for n in seen}


def _imported_top_levels() -> set[str]:
    out = set()
    for path in (BACKEND / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                out |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                out.add(node.module.split(".")[0])
    return out


def test_application_code_imports_no_development_only_package():
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    runtime = _runtime_closure(_names(project["project"]["dependencies"]))
    dev_only = {n.replace("_", "-") for n in _names(project["dependency-groups"]["dev"])} - runtime
    assert dev_only >= {"httpx", "pytest"}, dev_only  # the rule has something to check
    providers = importlib.metadata.packages_distributions()
    offending = {
        module: dists
        for module in _imported_top_levels()
        if (dists := {d.lower() for d in providers.get(module, [])}) and dists <= dev_only
    }
    assert offending == {}
