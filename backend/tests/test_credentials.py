"""C16 (D69): licences, certifications and credentials are grounded facts. A draft may name one
only by citing a credential from the profile that is approved and not expired; one is never
read into a job title, an employment description or the job text. An answer about a licence or
certification is never saved for reuse: the profile's credentials record when they expire."""

import uuid
from datetime import timedelta

from app.core.db import SessionLocal, utcnow
from app.modules.preparation import bankscope, drafting
from app.modules.preparation.classify import classify
from app.modules.preparation.drafting import DraftResult, GroundingFact, InvalidDraft
from app.modules.preparation.forms import FieldType, FormField, Option
from app.modules.preparation.resolver import Context, resolve_field
from app.modules.profiles.models import Approval, Credential
from tests.test_drafting import Canned, draft_for, request, use
from tests.test_input_binding import start
from tests.test_preparation import setup_candidate

YES_NO = [{"value": "1", "label": "Yes"}, {"value": "0", "label": "No"}]
LICENCE = {"key": "licence", "label": "Do you hold a phlebotomy certification?", "type": "radio",
           "required": True, "options": YES_NO}  # fmt: skip
WHY = {"key": "why_us", "label": "Why do you want to work here?", "type": "textarea",
       "required": False}  # fmt: skip


def user_id(api) -> uuid.UUID:
    return uuid.UUID(api.get("/auth/me").json()["user_id"])


def add_credential(uid, name, *, expires_in_days=None, status=Approval.approved, issuer=None):
    with SessionLocal() as db:
        c = Credential(
            user_id=uid,
            name=name,
            issuer=issuer,
            expires_on=None
            if expires_in_days is None
            else utcnow().date() + timedelta(days=expires_in_days),
            approval_status=status,
        )
        db.add(c)
        db.commit()
        return c.id


def facts(uid) -> dict[str, GroundingFact]:
    with SessionLocal() as db:
        return {f.id: f for f in drafting.grounding_facts(db, uid)}


def test_only_approved_unexpired_credentials_of_this_user_ground_a_draft(api, other_api):
    setup_candidate(api)
    me = user_id(api)
    ok = add_credential(me, "Phlebotomy certification", issuer="Synthetic Board",
                        expires_in_days=30)  # fmt: skip
    today = add_credential(me, "CPR certification", expires_in_days=0)
    never = add_credential(me, "Forklift operator certificate")
    expired = add_credential(me, "Food handler certificate", expires_in_days=-1)
    proposed = add_credential(me, "CNA certification", status=Approval.proposed)
    rejected = add_credential(me, "Nursing license", status=Approval.rejected)
    theirs = add_credential(user_id(other_api), "Security guard license")
    got = facts(me)
    for kept in (ok, today, never):
        assert got[f"credential:{kept}"].kind == "credential"
    for gone in (expired, proposed, rejected, theirs):
        assert f"credential:{gone}" not in got
    until = (utcnow().date() + timedelta(days=30)).isoformat()
    assert got[f"credential:{ok}"].text == (
        f"Phlebotomy certification, issued by Synthetic Board, valid until {until}"
    )


def test_a_credential_named_in_a_draft_must_be_a_cited_credential():
    """Never inferred from a job title, an employment description or the job text."""
    lpn = GroundingFact("employment:1", "employment", "Licensed Practical Nurse at Synthetic Care")
    cred = GroundingFact("credential:1", "credential", "Phlebotomy certification")
    req = request(job_text="A phlebotomy certification is required.", facts=(lpn, cred))

    def code(text, evidence):
        try:
            drafting.validate_draft(req, DraftResult(text=text, evidence=evidence, provider="t"))
        except InvalidDraft as e:
            return e.code
        return None

    assert code("I am a licensed practical nurse.", ["employment:1"]) == "uncited_credential"
    assert code("I hold a phlebotomy certification.", ["employment:1"]) == "uncited_credential"
    assert code("I hold a phlebotomy certification.", ["credential:1"]) is None
    assert code("I worked as a nurse at Synthetic Care.", ["employment:1"]) is None


def test_a_draft_cannot_claim_an_expired_credential(api, monkeypatch):
    setup_candidate(api)
    add_credential(user_id(api), "Phlebotomy certification", expires_in_days=-1)
    _, app_id = start(api, WHY)
    use(monkeypatch, Canned("I hold a phlebotomy certification."))
    r = api.post(f"/applications/{app_id}/drafts", json={"key": "why_us"})
    assert r.status_code == 422 and "without citing one of your credentials" in r.json()["detail"]
    add_credential(user_id(api), "Phlebotomy certification", expires_in_days=365)
    assert draft_for(api, app_id)["text"] == "I hold a phlebotomy certification."


def test_a_licence_answer_is_never_saved_for_reuse(api):
    setup_candidate(api)
    _, app_id = start(api, LICENCE)
    body = {"key": "licence", "value": {"label": "Yes"}, "save_to_bank": True}
    r = api.put(f"/applications/{app_id}/answers", json=body)
    assert r.status_code == 400 and "licence, certification or credential" in r.json()["detail"]
    assert api.get("/answer-bank").json() == []
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "licence", "value": {"label": "Yes"}})  # fmt: skip
    assert r.status_code == 200  # answered for this application


def test_a_licence_question_is_never_answered_from_the_profile_or_the_bank():
    """Even with an approved saved answer under its own key: the user answers it each time."""
    f = FormField(key="q", label="Do you have a nursing license?", type=FieldType.radio,
                  options=[Option(value="1", label="Yes"), Option(value="0", label="No")],
                  required=True)  # fmt: skip
    assert bankscope.refusal_code(f, classify(f)) == "credential"
    r = resolve_field(f, Context())
    assert not r.bankable and r.status == "needs_user" and r.value is None
    assert "credentials record with their expiry" in r.explanation


def test_the_credential_family_only_narrows():
    """Checked after every other family: a wording another family already refuses keeps its
    category, and the credential words alone never make anything reusable."""
    cpr = FormField(key="q", label="Are you CPR certified?", type=FieldType.radio,
                    options=[Option(value="1", label="Yes"), Option(value="0", label="No")],
                    help_text="Your certification must be valid on your first day.",
                    required=True)  # fmt: skip
    assert bankscope.refusal_code(cpr, classify(cpr)) == "time"
    yes_no = [Option(value="1", label="Yes"), Option(value="0", label="No")]
    plain = FormField(key="q", label="Do you have experience with phlebotomy?",
                      type=FieldType.radio, required=True, options=yes_no)  # fmt: skip
    assert bankscope.refusal_code(plain, classify(plain)) is None
