"""D99: saved answers imported from a file are proposals that answer nothing until you approve
each one; every row is judged by the rules for saved answers first. Synthetic rows only."""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.preparation.models import AnswerBankEntry

EXCEL = "Do you have advanced spreadsheet skills?"
TOOLS = "Which data visualization tools have you used?"
ROWS = [
    {"question": EXCEL, "answer": "Yes"},
    {"question": TOOLS, "answer": "Tableau and Looker"},
    {"question": "Are you authorized to work in the United States?", "answer": "Yes"},
    {"question": "Do you require visa sponsorship?", "answer": "No"},
    {"question": "What is your gender?", "answer": "Woman"},
    {"question": "Do you attend church regularly?", "answer": "No"},
    {"question": "Have you worked for {company} before?", "answer": "No"},
    {"question": "How did you hear about this job?", "answer": "A friend"},
    {"question": "What is your earliest start date?", "answer": "In two weeks"},
    {"question": "Do you hold a CPA?", "answer": "No"},
    {"question": "Apt / Suite", "answer": "Unit 9"},
    {
        "question": "Please describe a project you are proud of.",
        "answer": "I rebuilt a monthly reporting pack for a fictional clinic. " * 6,
    },
    {"question": "Do you speak Spanish?", "answer": "N/A"},
    {"question": "Do you enjoy public speaking?", "answer": "Yes"},
    {"question": "Do you enjoy public speaking?", "answer": "No"},
    {"question": "Do you have SQL experience?", "answer": "Yes"},
    {"question": "Do you have SQL experience?", "answer": "yes"},
    {"question": "", "answer": "Yes"},
]
EXPECTED = [
    ("import", None),
    ("import", None),
    ("refused", "protected"),
    ("refused", "protected"),
    ("refused", "sensitive"),
    ("refused", "sensitive"),
    ("refused", "template"),
    ("refused", "employer"),
    ("refused", "time"),
    ("refused", "credential"),
    ("refused", "place"),
    ("refused", "not_saved"),  # long free text: written per application or drafted
    ("refused", "placeholder"),
    ("refused", "conflict"),  # the same question, two answers: never chosen silently
    ("refused", "conflict"),
    ("import", None),
    ("refused", "duplicate"),
    ("refused", "blank"),
]


def bank() -> list[AnswerBankEntry]:
    with SessionLocal() as db:
        rows = db.scalars(select(AnswerBankEntry).order_by(AnswerBankEntry.question_text)).all()
        for r in rows:
            db.expunge(r)
        return rows


def outcomes(r) -> list[tuple]:
    return [(o["outcome"], o["reason"]) for o in r["outcomes"]]


def test_each_row_is_judged_by_the_rules_for_saved_answers(api):
    r = api.post("/answer-bank/import", json={"rows": ROWS})  # a dry run by default
    assert r.status_code == 200, r.text
    body = r.json()
    assert outcomes(body) == EXPECTED
    assert (body["dry_run"], body["rows"], body["importable"], body["added"]) == (True, 18, 3, 0)
    assert body["refused"]["conflict"] == 2 and "different answers" in body["reasons"]["conflict"]
    assert bank() == []  # a dry run writes nothing
    text = r.text.lower()
    assert "tableau" not in text and "spreadsheet" not in text  # rows by position, never text


def test_imported_answers_are_proposals_until_approved(api):
    r = api.post("/answer-bank/import", json={"rows": ROWS, "dry_run": False}).json()
    assert r["added"] == 3
    entries = bank()
    assert {e.question_text for e in entries} == {EXCEL, TOOLS, "Do you have SQL experience?"}
    assert {(e.provenance, e.approval_status) for e in entries} == {("import", "proposed")}
    excel = next(e for e in entries if e.question_text == EXCEL)
    assert (excel.answer_shape, excel.value, excel.options_snapshot) == (
        "choice", {"labels": ["Yes"]}, ["no", "yes"])  # fmt: skip
    listed = {e["question_text"]: e for e in api.get("/answer-bank").json()}
    assert listed[EXCEL]["approval_status"] == "proposed"
    hist = api.get(f"/answer-bank/{excel.id}/history").json()
    assert hist[0]["how"] == "imported from a file"
    with SessionLocal() as db:
        (a,) = db.scalars(select(AuditEvent).where(AuditEvent.action == "answer_bank.import"))
        assert (a.meta["rows"], a.meta["added"], a.meta["refused"]) == (18, 3, 15)
        assert "spreadsheet" not in str(a.meta).lower()


def _application(api) -> str:
    job = api.post("/jobs", json={"title": "Data Analyst", "employer": "Example Analytics"})
    job_id = job.json()["job"]["id"]
    form = {
        "title": "Data Analyst",
        "fields": [
            {"key": "excel", "label": EXCEL, "type": "select", "required": True,
             "options": [{"value": "1", "label": "Yes"}, {"value": "0", "label": "No"}]},
            {"key": "tools", "label": TOOLS, "type": "text", "required": True},
        ],
    }  # fmt: skip
    assert api.post(f"/jobs/{job_id}/form", json={"form": form}).status_code == 201
    return api.post("/applications", json={"job_id": job_id}).json()["id"]


def _answers(api, app_id) -> dict:
    p = api.get(f"/applications/{app_id}/package").json()["package"]["content"]
    return {a["key"]: a for a in p["answers"]}


def test_a_proposal_answers_nothing_until_you_approve_it(api):
    api.post("/answer-bank/import", json={"rows": ROWS[:2], "dry_run": False})
    app_id = _application(api)
    before = _answers(api, app_id)
    assert before["excel"]["source"] != "answer_bank" and before["tools"]["source"] != "answer_bank"
    excel = next(e for e in bank() if e.question_text == EXCEL)
    r = api.post(f"/answer-bank/{excel.id}/approve")
    assert r.status_code == 200 and r.json()["approval_status"] == "approved"
    app2 = _application(api)  # a new application resolves with the approved answer
    after = _answers(api, app2)
    assert after["excel"]["source"] == "answer_bank"
    assert after["excel"]["value"]["label"] == "Yes"
    assert after["tools"]["source"] != "answer_bank"  # still a proposal
    assert api.post(f"/answer-bank/{excel.id}/approve").status_code == 409  # already approved


def test_nothing_already_saved_is_replaced(api):
    api.post("/answer-bank/import", json={"rows": ROWS[:1], "dry_run": False})
    r = api.post("/answer-bank/import", json={"rows": [{"question": EXCEL, "answer": "No"}],
                                               "dry_run": False}).json()  # fmt: skip
    assert outcomes(r) == [("refused", "already_saved")] and r["added"] == 0
    (e,) = bank()
    assert e.value == {"labels": ["Yes"]}


def test_another_accounts_proposal_is_not_found(api, other_api):
    api.post("/answer-bank/import", json={"rows": ROWS[:1], "dry_run": False})
    (e,) = bank()
    assert other_api.post(f"/answer-bank/{e.id}/approve").status_code == 404
    assert other_api.post(f"/answer-bank/{uuid.uuid4()}/approve").status_code == 404
    assert bank()[0].approval_status == "proposed"
    # The other account's own import is judged against its own saved answers only.
    r = other_api.post("/answer-bank/import", json={"rows": ROWS[:1]}).json()
    assert outcomes(r) == [("import", None)]


def test_limits(api):
    assert api.post("/answer-bank/import", json={"rows": []}).status_code == 422
    big = [{"question": f"Q{i}?", "answer": "Yes"} for i in range(5001)]
    assert api.post("/answer-bank/import", json={"rows": big}).status_code == 422
    long_q = [{"question": "x" * 2001, "answer": "Yes"}]
    assert api.post("/answer-bank/import", json={"rows": long_q}).status_code == 422
