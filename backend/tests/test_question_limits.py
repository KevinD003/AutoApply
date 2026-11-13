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

import pytest

from app.modules.execution import runner
from app.modules.preparation.forms import FieldType, FormField, extract_form_schema, sent_len
from app.modules.preparation.resolver import validate_value
from tests.execution_harness import ROOT as REPO
from tests.execution_harness import Receiver, prepared_application, queue

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
], ids=["digits", "spaces", "ascii-whitespace", "leading-zero", "plus", "trailing-text",
        "no-break-space", "other-digits", "zero", "too-large"])  # fmt: skip
def test_a_question_s_limit_is_read_as_the_browser_reads_it(written, read_as):
    html = (f'<form><label for="n">Why us?</label><textarea id="n" name="why" '
            f'maxlength="{written}"></textarea></form>')  # fmt: skip
    (field,) = extract_form_schema(html).fields
    assert field.max_length == read_as


# ---------------------------------------------------------------------------- the count


def text_field(limit: int) -> FormField:
    return FormField(key="why", label="Why us?", type=FieldType.textarea, max_length=limit)


@pytest.mark.parametrize("text, ok", [
    ("abcde", True),
    ("ab\ncd", False),  # 5 for the browser, 6 as its form sends it
    ("abc\nd", False),
    ("ab\nc", True),
    ("a\U0001f600cd", True),  # outside the Basic Multilingual Plane: 2
    ("a\U0001f600cde", False),  # 5 characters, 6 units: the browser would cut it
], ids=["plain", "line-break-over", "line-break-over-2", "line-break-fits", "emoji-fits",
        "emoji-over"])  # fmt: skip
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
