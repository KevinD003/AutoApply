"""D118: two things the legacy adapters knew about real pages, ported into the generic
extractor (forms.extract_form_schema):

* the application form is the one filled and submitted, not a job-alert or newsletter form that
  shares the page (Recruitee, Breezy, Workable);
* a question's text can be linked by aria-labelledby with no <label> (Recruitee,
  SmartRecruiters); a missing label still stops the capture.

No real markup; the snippets are synthetic approximations labelled as such."""

import pytest

from app.modules.preparation.forms import ExtractionError, FieldType, extract_form_schema

# A job-alert sign-up form sharing the page with the application form (its own email + button).
JOB_ALERT = """
<form id="alerts" action="/alerts">
  <label for="alert_email">Get job alerts</label>
  <input type="email" id="alert_email" name="alert_email">
  <button type="submit">Subscribe</button>
</form>
"""

APPLICATION = """
<form id="app" action="/o/widget-co/c/new">
  <label for="full_name">Full name</label>
  <input type="text" id="full_name" name="candidate[name]">
  <label for="cv">Resume</label>
  <input type="file" id="cv" name="candidate[cv]">
  <button type="submit" data-testid="submit-application-form-button">Apply</button>
</form>
"""


def keys(schema) -> set[str]:
    return {f.key for f in schema.fields}


def test_only_the_application_form_is_read_not_a_job_alert_signup():
    schema = extract_form_schema(f"<main>{JOB_ALERT}{APPLICATION}</main>")
    assert keys(schema) == {"candidate[name]", "candidate[cv]"}  # never the alert's email
    assert schema.action == "/o/widget-co/c/new"  # the application form's action, not /alerts


def test_order_does_not_matter_the_form_with_the_upload_wins():
    schema = extract_form_schema(f"<main>{APPLICATION}{JOB_ALERT}</main>")
    assert keys(schema) == {"candidate[name]", "candidate[cv]"}


def test_a_single_form_is_still_read_whole():
    schema = extract_form_schema(f"<main>{APPLICATION}</main>")
    assert keys(schema) == {"candidate[name]", "candidate[cv]"}


def test_two_forms_each_with_an_upload_are_not_guessed_between():
    # Ambiguous: fall back to the whole page (both forms' fields are read; the real pages this
    # models don't occur, and nothing is silently dropped).
    second = APPLICATION.replace('id="app"', 'id="app2"').replace("candidate[", "other[")
    schema = extract_form_schema(f"<main>{APPLICATION}{second}</main>")
    assert "candidate[name]" in keys(schema) and "other[name]" in keys(schema)


def test_a_question_labelled_only_by_aria_labelledby_is_read():
    html = """
    <form action="/apply">
      <div id="q1-label">What is your preferred name?</div>
      <input type="text" id="q1" name="preferred" aria-labelledby="q1-label">
      <input type="file" id="cv" name="cv" aria-label="Resume">
    </form>
    """
    schema = extract_form_schema(html)
    name = next(f for f in schema.fields if f.key == "preferred")
    assert name.label == "What is your preferred name?" and name.type == FieldType.text


def test_several_labelledby_ids_join_in_order():
    html = """
    <form action="/apply">
      <span id="a">Do you now</span><span id="b">or in the future need sponsorship?</span>
      <input type="text" id="q" name="sponsorship" aria-labelledby="a b">
      <input type="file" id="cv" name="cv" aria-label="Resume">
    </form>
    """
    schema = extract_form_schema(html)
    q = next(f for f in schema.fields if f.key == "sponsorship")
    assert q.label == "Do you now or in the future need sponsorship?"


def test_a_field_with_no_label_of_any_kind_still_stops_the_capture():
    html = '<form action="/apply"><input type="text" id="q" name="mystery"></form>'
    with pytest.raises(ExtractionError):
        extract_form_schema(html)
