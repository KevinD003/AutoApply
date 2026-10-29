"""C6 (D51) through the API (synthetic candidate, fictional manual forms): answers that depend on
the employer, the job or the date are never saved for reuse (400, nothing stored, not even the
typed answer), a saved answer is bound to its help text, saved answers from before C6 are kept
and answer only a question without help text, a package built before C6 cannot save what C6
never reuses, and saved answers stay per user."""

import copy
import hashlib
import uuid
from types import SimpleNamespace as NS

from app.core.db import SessionLocal
from app.modules.preparation import router as prep
from app.modules.preparation.models import AnswerBankEntry
from app.modules.profiles.models import Approval
from tests.test_preparation import setup_candidate
from tests.test_question_safety_api import application, bank_count, package, radio, rows

EDU = "Highest level of education completed"
EDU_HELP = "Choose the highest level you have finished."
EDU_OPTIONS = [
    {"value": "hs", "label": "High school diploma"},
    {"value": "ba", "label": "Bachelor's degree"},
    {"value": "ma", "label": "Master's degree or higher"},
]
HEAR = {
    "key": "hear",
    "label": "How did you hear about this job?",
    "type": "select",
    "required": True,
    "options": [{"value": "r", "label": "Referral"}, {"value": "j", "label": "Job board"}],
}


def edu(key="edu", help_text=None, **kw) -> dict:
    f = {"key": key, "label": EDU, "type": "select", "required": True, "options": EDU_OPTIONS}
    return f | ({"help_text": help_text} if help_text else {}) | kw


def text(key, label, typ="text") -> dict:
    return {"key": key, "label": label, "type": typ, "required": True}


# (field, a valid answer, a phrase of the 400 detail): the critic's list, and one per category.
NEVER = [
    (radio("this_company", "Have you previously worked for this company?"), {"label": "No"},
     "about the employer or the job"),
    (radio("prev_named", "Have you previously worked for Northwind Example?"), {"label": "No"},
     "about the employer or the job"),
    (HEAR, {"label": "Referral"}, "about the employer or the job"),
    (radio("relevant", "Do you have relevant experience?"), {"label": "Yes"},
     "about the employer or the job"),
    (text("jobref", "Job reference number"), {"text": "R-1"}, "about the employer or the job"),
    (text("start", "Earliest start date", "date"), {"date": "2026-11-02"},
     "depends on when you apply"),
    (text("when", "When can you start?"), {"text": "In two weeks"}, "depends on when you apply"),
    (text("avail", "What is your availability?"), {"text": "Weekdays"},
     "depends on when you apply"),
    (text("notice", "Notice period"), {"text": "Two weeks"}, "depends on when you apply"),
    (text("years", "Years of experience", "number"), {"number": 3}, "depends on when you apply"),
    (radio("dl", "Do you have a valid driver's license?"), {"label": "Yes"},
     "depends on when you apply"),
    (radio("relocate", "Are you willing to relocate?"), {"label": "No"}, "Relocation, commuting"),
    (text("street", "Street address"), {"text": "1 Synthetic Way"}, "Relocation, commuting"),
    (text("salary", "Desired annual salary (USD)", "number"), {"number": 50000},
     "Pay is never saved"),
    (text("ctc", "Expected CTC"), {"text": "10 LPA"}, "Pay is never saved"),
    (radio("based", "I am based in the U.S."), {"label": "Yes"},
     "is about work authorization"),
]  # fmt: skip


def _me(api) -> str:
    return api.get("/auth/me").json()["user_id"]


def _put(api, app_id, key, value, bank):
    body = {"key": key, "value": value, "save_to_bank": bank}
    return api.put(f"/applications/{app_id}/answers", json=body)


def test_answers_that_depend_on_the_employer_the_job_or_the_date_are_never_saved(api):
    setup_candidate(api)
    # Without a relocation or salary preference, those two are the user's to answer here.
    api.put("/profile/preferences", json={"willing_to_relocate": "unknown"})
    app_id = application(api, [f for f, _, _ in NEVER] + [edu()])
    v = package(api, app_id)
    me = _me(api)
    for f, value, phrase in NEVER:
        key = f["key"]
        row = rows(v)[key]
        assert not row["bankable"] and row["source"] == "unresolved", (key, row)
        r = _put(api, app_id, key, value, True)
        assert r.status_code == 400 and phrase in r.json()["detail"], (key, r.text)
        assert "Nothing was saved" in r.json()["detail"], key
        assert bank_count(me) == 0, key
        # The refused request wrote nothing, not even the typed answer.
        assert rows(package(api, app_id))[key]["source"] == "unresolved", key
        r = _put(api, app_id, key, value, False)
        assert r.status_code == 200 and rows(r.json())[key]["source"] == "user_entered", key
    # Control on the same form: a stable question is saved.
    r = _put(api, app_id, "edu", {"label": "Bachelor's degree"}, True)
    assert r.status_code == 200 and bank_count(me) == 1


def test_relocation_and_salary_from_preferences_keep_the_profile_refusal(api):
    setup_candidate(api)
    prefs = {"willing_to_relocate": "no", "salary_min": 50000, "salary_currency": "USD",
             "salary_period": "year"}  # fmt: skip
    api.put("/profile/preferences", json=prefs)
    fields = [radio("relocate", "Are you willing to relocate?"),
              text("salary", "Desired annual salary (USD)", "number")]  # fmt: skip
    app_id = application(api, fields)
    v = package(api, app_id)
    for key, value in (("relocate", {"label": "No"}), ("salary", {"number": 50000})):
        row = rows(v)[key]
        assert (row["status"], row["source"], row["bankable"]) == (
            "resolved",
            "deterministic_mapping",
            False,
        ), key
        r = _put(api, app_id, key, value, True)
        assert r.status_code == 400, key
        assert "verified profile or your preferences" in r.json()["detail"], key
    assert bank_count(_me(api)) == 0


def test_a_follow_up_or_a_repeated_question_is_never_saved(api):
    setup_candidate(api)
    langs = [{"value": "en", "label": "English"}, {"value": "es", "label": "Spanish"}]
    fields = [
        radio("before", "Have you worked for us before?", required=True),
        text("certs", "Which certifications do you hold?")
        | {"condition": {"key": "before", "any_of": ["1"]}},
        {"key": "l1", "label": "Languages", "type": "multiselect", "options": langs},
        {"key": "l2", "label": "Languages", "type": "multiselect", "options": langs},
    ]
    app_id = application(api, fields)
    v = package(api, app_id)
    for key, value, phrase in (
        ("certs", {"text": "CPR"}, "follow-up depends on a question"),
        ("l1", {"labels": ["English"]}, "appears more than once"),
        ("l2", {"labels": ["Spanish"]}, "appears more than once"),
    ):
        assert not rows(v)[key]["bankable"], key
        r = _put(api, app_id, key, value, True)
        assert r.status_code == 400 and phrase in r.json()["detail"], (key, r.text)
    assert bank_count(_me(api)) == 0


def test_a_saved_answer_is_reused_only_for_the_same_help_text(api):
    setup_candidate(api)
    j1 = application(api, [edu(help_text=EDU_HELP)], title="Role 1")
    assert _put(api, j1, "edu", {"label": "Bachelor's degree"}, True).status_code == 200
    (entry,) = api.get("/answer-bank").json()
    assert (entry["question_text"], entry["help_text"], entry["not_reused"]) == (
        EDU,
        EDU_HELP,
        None,
    )
    same = application(api, [edu(help_text=EDU_HELP)], title="Role 2")
    cosmetic = application(
        api, [edu(help_text="  choose the highest level you have FINISHED ")], title="Role 3"
    )
    other_help = "Choose the highest level you have started."
    other = application(api, [edu(help_text=other_help)], title="Role 4")
    plain = application(api, [edu()], title="Role 5")
    for app_id, reused in ((same, True), (cosmetic, True), (other, False), (plain, False)):
        row = rows(package(api, app_id))["edu"]
        if reused:
            assert (row["source"], row["display"]) == ("answer_bank", "Bachelor's degree"), app_id
        else:
            assert (row["status"], row["source"]) == ("needs_user", "unresolved"), app_id
    # Saving under other help text adds its own entry; the first one is untouched.
    assert _put(api, other, "edu", {"label": "High school diploma"}, True).status_code == 200
    bank = {e["help_text"]: e for e in api.get("/answer-bank").json()}
    assert set(bank) == {EDU_HELP, other_help}
    assert bank[EDU_HELP]["version"] == 1
    assert bank[EDU_HELP]["value"] == {"labels": ["Bachelor's degree"]}


def test_saved_answers_from_before_c6_are_kept_and_answer_only_a_question_without_help_text(
    api, other_api
):
    """Rows written before C6: the key of the wording and shape only (the literal formula), no
    help text recorded. Nothing is deleted or re-keyed; such a row answers only a question that
    has no help text, and one whose wording C6 never reuses answers nothing."""
    setup_candidate(api)
    me = uuid.UUID(_me(api))
    legacy = {
        "edu": (b"highest level of education completed|choice", EDU,
                ["bachelor's degree", "high school diploma", "master's degree or higher"],
                {"labels": ["Bachelor's degree"]}),
        "hear": (b"how did you hear about this job|choice", HEAR["label"],
                 ["job board", "referral"], {"labels": ["Referral"]}),
    }  # fmt: skip
    ids = {}
    with SessionLocal() as db:
        for name, (raw, label, options, value) in legacy.items():
            e = AnswerBankEntry(
                user_id=me,
                question_key=hashlib.sha256(raw).hexdigest(),
                question_text=label,
                help_text=None,
                answer_shape="choice",
                value=value,
                options_snapshot=options,
                sensitive=False,
                version=1,
                provenance="user_entered",
                approval_status=Approval.approved,
            )
            db.add(e)
            db.flush()
            ids[name] = e.id
        db.commit()
    plain = application(api, [edu(), HEAR], title="Plain")
    helped = application(api, [edu(help_text=EDU_HELP)], title="Helped")
    v = rows(package(api, plain))
    assert (v["edu"]["source"], v["edu"]["display"]) == ("answer_bank", "Bachelor's degree")
    assert (v["hear"]["source"], v["hear"]["bankable"]) == ("unresolved", False)
    assert rows(package(api, helped))["edu"]["source"] == "unresolved"
    listed = {e["question_text"]: e for e in api.get("/answer-bank").json()}
    assert listed[EDU]["help_text"] is None and listed[EDU]["not_reused"] is None
    assert listed[HEAR["label"]]["not_reused"] == "It is about one employer or job."
    # A save from the form with help text adds a C6 entry; the legacy row is unchanged.
    assert _put(api, helped, "edu", {"label": "Master's degree or higher"}, True).status_code == 200
    with SessionLocal() as db:
        old = db.get(AnswerBankEntry, ids["edu"])
        assert (old.question_key, old.value, old.version, old.help_text) == (
            hashlib.sha256(legacy["edu"][0]).hexdigest(),
            {"labels": ["Bachelor's degree"]},
            1,
            None,
        )
    assert len(api.get("/answer-bank").json()) == 3
    # The owner's explicit save on the plain form updates the legacy row in place: same key,
    # same value (no new version), help text now recorded as none.
    assert _put(api, plain, "edu", {"label": "Bachelor's degree"}, True).status_code == 200
    with SessionLocal() as db:
        old = db.get(AnswerBankEntry, ids["edu"])
        assert (old.version, old.help_text) == (1, "")
    # Another user never resolves from these rows and cannot read or delete them.
    setup_candidate(other_api)
    theirs = rows(package(other_api, application(other_api, [edu(), HEAR], title="Theirs")))
    assert theirs["edu"]["source"] == "unresolved" and theirs["hear"]["source"] == "unresolved"
    assert other_api.get("/answer-bank").json() == []
    assert other_api.get(f"/applications/{plain}/package").status_code == 404
    for e in api.get("/answer-bank").json():
        assert other_api.delete(f"/answer-bank/{e['id']}").status_code == 404
    assert len(api.get("/answer-bank").json()) == 3
    # The owner can delete an entry that is no longer reused, once.
    hid = listed[HEAR["label"]]["id"]
    assert api.delete(f"/answer-bank/{hid}").status_code == 204
    assert api.delete(f"/answer-bank/{hid}").status_code == 404


def test_a_package_built_before_c6_cannot_save_what_c6_never_reuses(api, monkeypatch):
    """A package that is not rebuilt (its application is past preparation) keeps the rows it was
    built with, and a row built before C6 still says bankable. The router checks the wording too."""
    setup_candidate(api)
    app_id = application(api, [HEAR, edu()])
    real = prep.pk.ensure_current

    def as_built_before_c6(db, app):
        content = copy.deepcopy(real(db, app).content)
        for a in content["answers"]:
            a["bankable"] = True
        return NS(content=content)

    monkeypatch.setattr(prep.pk, "ensure_current", as_built_before_c6)
    r = _put(api, app_id, "hear", {"label": "Referral"}, True)
    assert r.status_code == 400 and "about the employer or the job" in r.json()["detail"]
    assert bank_count(_me(api)) == 0


def test_a_follow_up_in_a_package_built_before_c6_checks_its_parent_again(api, monkeypatch):
    """Found by the review: the follow-up check read its parent's flag from the stored package,
    which in a package built before C6 says bankable."""
    setup_candidate(api)
    site = text("site", "Which website?") | {"condition": {"key": "hear", "any_of": ["j"]}}
    app_id = application(api, [HEAR, site, edu()])
    assert _put(api, app_id, "hear", {"label": "Job board"}, False).status_code == 200
    real_current, real_latest = prep.pk.ensure_current, prep.pk.latest_package

    class Stale:  # the stored package, as built before C6: every row says bankable
        def __init__(self, pkg):
            self._pkg, self.content = pkg, copy.deepcopy(pkg.content)
            for a in self.content["answers"]:
                a["bankable"] = True

        def __getattr__(self, name):
            return getattr(self._pkg, name)

    def stale(pkg):
        return Stale(pkg)

    monkeypatch.setattr(prep.pk, "ensure_current", lambda db, app: stale(real_current(db, app)))
    monkeypatch.setattr(prep.pk, "latest_package", lambda db, aid: stale(real_latest(db, aid)))
    r = _put(api, app_id, "site", {"text": "A job board"}, True)
    assert r.status_code == 400 and "follow-up depends on a question" in r.json()["detail"], r.text
    assert bank_count(_me(api)) == 0


def test_saving_and_listing_never_fail_on_unusual_text(api):
    """Found by the review: a NUL in page text or in an answer, a stored option label longer
    than an option may be, NaN or infinity as a number, and a repeated sensitive question's
    message. Each was a 500 or a wrong reason."""
    setup_candidate(api)
    gender = [{"value": "w", "label": "Woman"}, {"value": "m", "label": "Man"}]
    fields = [
        # Not a certification question: those are never saved (C16).
        text("langs", "Which programming languages do you know?")
        | {"help_text": "List them.\u0000"},
        text("count", "How many languages do you speak?", "number"),
        {"key": "g1", "label": "Gender", "type": "select", "required": False, "options": gender},
        {"key": "g2", "label": "Gender", "type": "select", "required": False, "options": gender},
    ]
    app_id = application(api, fields)
    for value in ({"text": "Python\u0000"}, {"text": "Python\u0000"}, {"text": "Go"}):
        assert _put(api, app_id, "langs", value, True).status_code == 200
    (saved,) = api.get("/answer-bank").json()
    assert saved["help_text"] == "List them." and saved["version"] == 2  # changed once
    for bad in ("nan", "inf", "-inf"):
        r = _put(api, app_id, "count", {"number": bad}, False)
        assert r.status_code == 400 and "expected a number" in r.json()["detail"], bad
    r = _put(api, app_id, "g1", {"label": "Woman"}, True)
    assert r.status_code == 400 and "appears more than once" in r.json()["detail"], r.text
    me = uuid.UUID(_me(api))
    with SessionLocal() as db:
        db.add(
            AnswerBankEntry(
                user_id=me,
                question_key=hashlib.sha256(b"pick one|choice").hexdigest(),
                question_text="Pick one",
                answer_shape="choice",
                value={"labels": ["b"]},
                options_snapshot=["a" * 503, "b"],
                sensitive=False,
                version=1,
                provenance="user_entered",
                approval_status=Approval.approved,
            )
        )
        db.commit()
    listed = api.get("/answer-bank")
    assert listed.status_code == 200, listed.text
    assert {e["question_text"]: e["not_reused"] for e in listed.json()}["Pick one"] is None


def test_saved_answers_stay_per_user(api, other_api):
    setup_candidate(api)
    setup_candidate(other_api)
    mine = application(api, [edu()], title="Mine")
    theirs = application(other_api, [edu()], title="Theirs")
    assert _put(api, mine, "edu", {"label": "Bachelor's degree"}, True).status_code == 200
    assert _put(other_api, theirs, "edu", {"label": "High school diploma"}, True).status_code == 200
    (m,) = api.get("/answer-bank").json()
    (t,) = other_api.get("/answer-bank").json()
    assert m["id"] != t["id"] and m["version"] == t["version"] == 1
    assert m["value"] == {"labels": ["Bachelor's degree"]}
    assert t["value"] == {"labels": ["High school diploma"]}
    assert api.delete(f"/answer-bank/{m['id']}").status_code == 204
    assert api.delete(f"/answer-bank/{m['id']}").status_code == 404
    assert other_api.get("/answer-bank").json() == [t]
