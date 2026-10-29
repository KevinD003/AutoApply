"""Local ATS-like fixture forms for development and tests. All employers are fictional."""

from pathlib import Path

_DIR = Path(__file__).parent / "fixtures"

FIXTURES = {
    "basic": "Clinic Assistant — Example Health Clinic (fictional, standard questions)",
    "tricky": "Dispatcher — Northwind Logistics (fictional, negation/tense/option traps)",
    # D80: shapes from docs/research/lever.md (search-reported); checkpoint-first.
    "lever": "Registered Nurse — Example Health (fictional, Lever-shaped, search-reported fields)",
    # D81: shapes from docs/research/workday.md and ashby.md (search-reported); checkpoint-first.
    "workday": "Registered Nurse — Example Health (fictional, Workday-shaped, account required)",
    "ashby": "Clinical Data Analyst — Example Health (fictional, Ashby-shaped, search-reported)",
}


def fixture_html(name: str) -> str:
    if name not in FIXTURES:
        raise KeyError(name)
    return (_DIR / f"{name}.html").read_text(encoding="utf-8")
