"""D158: an ordinary question's length limit (`maxlength`, on every provider) is read as the
browser reads it, and your answer held to it as its form sends it (`forms.sent_len`: UTF-16 code
units, a line break counting two), never less than the browser's own count. Before D158 an answer
was counted by its characters (code points): one the browser would cut (an emoji counts two
there) passed and was stopped only by the readback; one whose line breaks the form sends as
CRLF passed and could be refused by the employer's own check after the final click.

The receiver's own ledger is the oracle (its acceptances, and its own check of the page's limit
on what it receives, `receiver.too_long`). Passing here shows fixture compatibility only, never
how a real employer's server counts. Synthetic candidate data only."""

import sys
import uuid

import pytest

from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.preparation import resolver
from app.modules.preparation.forms import FieldType, FormField, extract_form_schema, sent_len
from app.modules.preparation.models import AnswerDraft
from app.modules.preparation.resolver import normalize_input, validate_value
from tests.execution_harness import ROOT as REPO
from tests.execution_harness import Receiver, prepared_application, queue
from tests.test_drafting import Canned, draft_for, use
from tests.test_preparation import answers, new_application, setup_candidate

sys.path.insert(0, str(REPO / "fixtures" / "ats_receiver"))
import receiver as receiver_module  # noqa: E402

LIMIT = receiver_module.LIMITS["why_us"]
assert LIMIT == 1000


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


# ---------------------------------------------------------------------------- reading


@pytest.mark.parametrize("written, read_as", [
    ("40", 40),
    (" 40 ", 40),  # D158: as the browser reads it (before: not recorded)
    ("\t40\n", 40),
    ("040", 40),
    ("+40", None),  # the browser reads 40; never guessed at, the readback stops a cut
    ("40abc", None),
    (" 40", None),  # the browser reads no limit
    ("٤٠", None),
    ("0", None),
    ("100001", None),  # above FormField's own bound: not recorded
    ('10" maxlength="1000', 10),  # written twice: the browser keeps the first
    ('1000" maxlength="10', 1000),
], ids=["digits", "spaces", "ascii-whitespace", "leading-zero", "plus", "trailing-text",
        "no-break-space", "other-digits", "zero", "too-large", "twice-smaller-first",
        "twice-larger-first"])  # fmt: skip
def test_a_question_s_limit_is_read_as_the_browser_reads_it(written, read_as):
    html = (f'<form><label for="n">Why us?</label><textarea id="n" name="why" '
            f'maxlength="{written}"></textarea></form>')  # fmt: skip
    (field,) = extract_form_schema(html).fields
    assert field.max_length == read_as


# ---------------------------------------------------------------------------- the count


def text_field(limit: int | None, kind: FieldType = FieldType.textarea) -> FormField:
    return FormField(key="why", label="Why us?", type=kind, max_length=limit)


@pytest.mark.parametrize("text, ok", [
    ("abcde", True),
    ("ab\ncd", False),  # 5 for the browser, 6 as its form sends it
    ("abc\nd", False),
    ("ab\nc", True),
    ("a\U0001f600cd", True),  # outside the Basic Multilingual Plane: 2
    ("a\U0001f600cde", False),  # 5 characters, 6 units: the browser would cut it
    ("ab\rc", True),  # a lone CR is a line break too: sent as CRLF, 5
    ("abc\rd", False),
    ("ab\r\nc", True),  # CRLF is one line break: 5, never 6
], ids=["plain", "line-break-over", "line-break-over-2", "line-break-fits", "emoji-fits",
        "emoji-over", "cr-fits", "cr-over", "crlf-is-one"])  # fmt: skip
def test_an_answer_is_held_to_its_limit_as_its_form_sends_it(text, ok):
    err = validate_value(text_field(5), {"text": text})
    assert (err is None) is ok
    if not ok:
        assert f"({sent_len(text)}/5 characters as the form sends them" in err
        assert "a line break or an emoji counts as two" in err


# ---------------------------------------------------------------------------- the API


def test_an_answer_the_form_would_send_too_long_is_refused_when_saved(api, receiver):
    """999 for the browser (a line break counting one), 1001 as its form sends it."""
    app_id = prepared_application(api, receiver, approve=False)
    over = "x" * 998 + "\n" + "y"
    r = api.put(f"/applications/{app_id}/answers", json={"key": "why_us", "value": {"text": over}})
    assert r.status_code == 400 and "1001/1000 characters as the form sends them" in r.text
    fits = "x" * 997 + "\n" + "y"
    r = api.put(f"/applications/{app_id}/answers", json={"key": "why_us", "value": {"text": fits}})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------- through the runner


def test_an_answer_at_its_limit_as_the_form_sends_it_is_sent_whole(api, receiver):
    """1000 as its form sends it (999 for the browser): typed whole, and the page's own check on
    what it receives accepts it."""
    answer = "x" * 997 + "\n" + "y"
    assert sent_len(answer) == LIMIT
    app_id = prepared_application(api, receiver, why_text=answer)
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    (row,) = receiver.ledger()["acceptances"]
    assert row["fields"]["why_us"].replace("\r\n", "\n") == answer
    assert receiver_module.too_long(row["fields"]) == []


def test_the_stand_in_refuses_what_it_receives_longer_than_its_limit():
    """The oracle's own check: what it receives, a line break (CRLF) counting two."""
    assert receiver_module.too_long({"why_us": "x" * 998 + "\r\n"}) == []
    assert receiver_module.too_long({"why_us": "x" * 999 + "\r\n"}) == ["why_us"]
    assert receiver_module.too_long({"why_us": "x" * 999 + "\U0001f600"}) == ["why_us"]
    assert receiver_module.too_long({}) == []


@pytest.mark.parametrize("text", ["a\nb", "a\rb", "a\r\nb"], ids=["lf", "cr", "crlf"])
@pytest.mark.parametrize("kind", [FieldType.text, FieldType.email, FieldType.tel, FieldType.url])
def test_a_one_line_box_holds_no_line_break(text, kind):
    """D158, found by its review: the browser makes each line break in a one-line box a space,
    so the readback could never match and the attempt stopped after the pages it had sent."""
    assert validate_value(text_field(None, kind), {"text": text}) == (
        "a line break, which this one-line box cannot hold"
    )
    with pytest.raises(ValueError, match="one-line box"):
        normalize_input(text_field(None, kind), {"text": text})


@pytest.mark.parametrize("limit", [None, 10])
def test_a_broken_character_is_refused_plainly(limit):
    """D158, found by its review: half of a surrogate pair failed the count with the codec's own
    words (and, without a limit, a server error)."""
    with pytest.raises(ValueError, match="broken character"):
        normalize_input(text_field(limit), {"text": "ab\ud800c"})
    assert sent_len("ab\ud800c") == 4


def test_a_text_area_s_line_breaks_are_kept_as_one_lf_each():
    value = normalize_input(text_field(None), {"text": "a\r\nb\rc\nd"})
    assert value == {"text": "a\nb\nc\nd"}
    assert sent_len("a\r\nb") == sent_len("a\rb") == sent_len("a\nb") == 4


# ---------------------------------------------------------------------------- answers you gave


def code_points(text: str) -> int:
    """The count before D158."""
    return len(text)


def test_an_answer_saved_before_that_no_longer_fits_is_a_checkpoint_even_when_optional(
    api, receiver, monkeypatch
):
    """D158, found by its review: saved under the old count (code points), the optional answer
    was left out of the package without a word (`blank_optional`) and approval allowed, so the
    attempt sent the question empty. It is yours to fix now, and approval waits for it (D78)."""
    monkeypatch.setattr(resolver, "sent_len", code_points)
    app_id = prepared_application(api, receiver, why_text="x" * 998 + "\n" + "y", approve=False)
    assert answers(api.get(f"/applications/{app_id}/package").json())["why_us"]["status"] == (
        "resolved"
    )
    monkeypatch.undo()
    view = api.get(f"/applications/{app_id}/package").json()
    why = answers(view)["why_us"]
    assert why["status"] == "needs_user" and why["value"] is None
    assert "no longer fits" in why["explanation"] and "1001/1000" in why["explanation"]
    assert "why_us" in view["package"]["content"]["unresolved"]


def test_what_the_page_s_own_check_refuses_never_reaches_it_now(api, receiver, monkeypatch):
    """Before D158 (the old count, code points), an answer the browser keeps whole but its form
    sends longer than the page's limit was typed and the final click made; the page's own check
    on what it receives refused it. Its oracle, here: no acceptance, and the page's refusal."""
    monkeypatch.setattr(resolver, "sent_len", code_points)
    app_id = prepared_application(api, receiver, why_text="x" * 998 + "\n" + "y")
    assert runner.run_attempt(queue(api, app_id), "w1") != "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 0 and led["acceptances"] == []


# ---------------------------------------------------------------------------- drafts


def test_a_draft_its_form_would_send_too_long_is_never_offered(api, monkeypatch):
    """D158, found by its review: the draft check counted characters, so a draft accepting would
    refuse was offered, and offered again from the cache."""
    setup_candidate(api)
    app_id = new_application(api)[1]["id"]  # the basic fixture: why_us limited to 1000
    p = use(monkeypatch, Canned("I supported 3 doctors." + "\nAnd more." * 97))
    assert len(p.text) <= 1000 < sent_len(p.text)
    r = api.post(f"/applications/{app_id}/drafts", json={"key": "why_us"})
    assert r.status_code == 422 and "as the form sends them" in r.text
    with SessionLocal() as db:
        assert db.query(AnswerDraft).count() == 0


def test_a_cached_draft_that_no_longer_fits_is_replaced_not_offered_again(api, monkeypatch):
    setup_candidate(api)
    app_id = new_application(api)[1]["id"]
    p = use(monkeypatch, Canned("I supported 3 doctors at the front desk."))
    d = draft_for(api, app_id)
    with SessionLocal() as db:  # as a draft made before D158 may be
        db.get(AnswerDraft, uuid.UUID(d["id"])).text = "x" * 999 + "\n"
        db.commit()
    fresh = draft_for(api, app_id)
    assert fresh["id"] != d["id"] and len(p.requests) == 2


def test_a_draft_for_a_one_line_box_is_offered_on_one_line(api, monkeypatch):
    setup_candidate(api)
    job = api.post("/jobs", json={"title": "Manual", "employer": "Example Health"}).json()["job"]
    form = {"title": "Manual (fictional)", "fields": [
        {"key": "why_short", "label": "Why do you want to work here?", "type": "text",
         "max_length": 300}]}  # fmt: skip
    assert api.post(f"/jobs/{job['id']}/form", json={"form": form}).status_code == 201
    app_id = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    use(monkeypatch, Canned("I supported 3 doctors.\nAt the front desk."))
    d = draft_for(api, app_id, key="why_short")
    assert d["text"] == "I supported 3 doctors. At the front desk."
    r = api.post(f"/applications/{app_id}/drafts/{d['id']}/accept")
    assert r.status_code == 200, r.text
