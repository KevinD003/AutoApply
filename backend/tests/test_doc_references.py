"""Every test the documentation cites as evidence exists (as a test function or a test module),
so a renamed or deleted test cannot leave a guarantee pointing at nothing."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
CITED = re.compile(r"`(test_[a-z0-9_]+)`")
DEFINED = re.compile(r"^\s*(?:async\s+)?def (test_[a-z0-9_]+)", re.M)


def test_every_cited_test_exists():
    docs = [*sorted((ROOT / "docs").glob("*.md")), ROOT / "README.md"]
    cited = {name for d in docs for name in CITED.findall(d.read_text())}
    sources = [*(ROOT / "backend" / "tests").glob("*.py"), *(ROOT / "compose_tests").glob("*.py")]
    defined = {name for p in sources for name in DEFINED.findall(p.read_text())}
    defined |= {p.stem for p in sources}  # a cited test module
    assert len(cited) > 100  # the scan read the documents at all
    assert sorted(cited - defined) == []
