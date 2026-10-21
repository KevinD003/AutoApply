"""docs/audit-events.md lists every audit event the code writes, with exactly its metadata keys.

The call sites are read from the source (every `record(...)` call under app/), so adding,
removing or changing an event without updating the inventory fails here."""

import ast
import pathlib
import re

from app.modules.audit.service import sanitize

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
DOC = ROOT / "docs" / "audit-events.md"


def _pattern(node: ast.expr) -> list[str]:
    """The action or entity strings a call can produce; f-string parts become `{}`."""
    if isinstance(node, ast.Constant):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _pattern(node.body) + _pattern(node.orelse)
    if isinstance(node, ast.JoinedStr):
        return ["".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)]
    if isinstance(node, ast.Name):
        return ["{}"]
    raise AssertionError(f"unrecognised audit argument: {ast.unparse(node)}")


def code_events() -> set[tuple[str, str, tuple[str, ...]]]:
    out = set()
    for path in APP.rglob("*.py"):
        for n in ast.walk(ast.parse(path.read_text())):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "record":
                keys = tuple(sorted(k.arg for k in n.keywords))
                (entity,) = _pattern(n.args[3])
                out |= {(action, entity, keys) for action in _pattern(n.args[2])}
    return out


def doc_events() -> set[tuple[str, str, tuple[str, ...]]]:
    text = DOC.read_text().split("## Event inventory", 1)[1].split("\n## ", 1)[0]
    out = set()
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].startswith("`"):
            continue
        actions = re.findall(r"`([^`]+)`", cells[0])
        (entity,) = re.findall(r"`([^`]+)`", cells[1])
        keys = tuple(sorted(re.findall(r"`([^`]+)`", cells[2])))
        norm = lambda s: re.sub(r"\{[^}]*\}", "{}", s)  # noqa: E731
        out |= {(norm(a), norm(entity), keys) for a in actions}
    return out


def test_the_inventory_lists_exactly_the_events_the_code_writes():
    code, doc = code_events(), doc_events()
    assert len(code) >= 30  # the scan found the call sites at all
    assert code - doc == set(), "written by the code but not documented"
    assert doc - code == set(), "documented but not written by the code"


def test_every_documented_metadata_key_survives_the_sanitizer():
    keys = {k for _, _, ks in doc_events() for k in ks}
    assert keys and all(sanitize({k: 1}) == {k: 1} for k in keys), keys
