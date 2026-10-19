"""Local ATS-like fixture forms for development and tests. All employers are fictional."""

from pathlib import Path

_DIR = Path(__file__).parent / "fixtures"

FIXTURES = {
    "basic": "Clinic Assistant — Example Health Clinic (fictional, standard questions)",
    "tricky": "Dispatcher — Northwind Logistics (fictional, negation/tense/option traps)",
}


def fixture_html(name: str) -> str:
    if name not in FIXTURES:
        raise KeyError(name)
    return (_DIR / f"{name}.html").read_text(encoding="utf-8")
