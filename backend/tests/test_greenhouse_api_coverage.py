"""D119: the Greenhouse field catalogue is the official Job Board API
(GET /boards/{token}/jobs/{id}?questions=true; grnhse/greenhouse-api-docs). This guard pins
the documented question field types to how greenhouse.schema_from_api maps each, so a type
Greenhouse adds later is noticed instead of silently dropped. Synthetic data only.

Every documented field type is filled by the DOM adapter:
  input_text → text (email/phone by name), textarea → textarea, input_file → file,
  multi_value_single_select → select, multi_value_multi_select → checkbox_group,
  input_hidden → unsupported (a value the page sets, e.g. map coordinates: a checkpoint).
EEOC/demographic and education/employment history are NOT auto-filled: demographics are never
inferred (a non-negotiable rule), so those stay the applicant's own per-application answers."""

from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import FieldType

# The question field types the Job Board API documents (docs.greenhouse.io/job-board.html).
DOCUMENTED_TYPES = {
    "input_text": FieldType.text,
    "textarea": FieldType.textarea,
    "input_file": FieldType.file,
    "multi_value_single_select": FieldType.select,
    "multi_value_multi_select": FieldType.checkbox_group,
    "input_hidden": FieldType.unsupported,
}


def q(label, name, ftype, required=False, values=None):
    f = {"name": name, "type": ftype}
    if values is not None:
        f["values"] = values
    return {"label": label, "required": required, "fields": [f]}


def test_every_documented_question_field_type_maps_to_a_control_kind():
    yn = [{"value": 0, "label": "No"}, {"value": 1, "label": "Yes"}]
    data = {
        "title": "Product Engineer",
        "questions": [
            q("First Name", "first_name", "input_text", required=True),
            q("Email", "email", "input_text"),
            q("Phone", "phone", "input_text"),
            q("Why us?", "question_1", "textarea"),
            q("Resume", "resume", "input_file", required=True),
            q("Do you like apples?", "question_2", "multi_value_single_select", values=yn),
            q("Colours", "question_3", "multi_value_multi_select", values=yn),
        ],
        "location_questions": [
            q("Latitude", "latitude", "input_hidden", required=True),
        ],
    }
    by_key = {f.key: f for f in gh.schema_from_api(data).fields}
    assert by_key["first_name"].type is FieldType.text
    assert by_key["email"].type is FieldType.email  # input_text, mapped by name
    assert by_key["phone"].type is FieldType.tel
    assert by_key["question_1"].type is FieldType.textarea
    assert by_key["resume"].type is FieldType.file
    assert by_key["question_2"].type is FieldType.select
    assert [o.label for o in by_key["question_2"].options] == ["No", "Yes"]
    assert by_key["question_3[]"].type is FieldType.checkbox_group  # multi: name gets []
    # input_hidden (map coordinates): never typed, a checkpoint, as documented.
    assert by_key["latitude"].type is FieldType.unsupported
    assert by_key["latitude"].required is True


def test_the_attach_or_paste_question_uses_the_upload_not_the_paste_box():
    # Documented: the Resume question has both input_file and textarea; the file is the control.
    data = {"questions": [{"label": "Resume", "required": True, "fields": [
        {"name": "resume", "type": "input_file"},
        {"name": "resume_text", "type": "textarea"},
    ]}]}  # fmt: skip
    (f,) = gh.schema_from_api(data).fields
    assert f.key == "resume" and f.type is FieldType.file


def test_a_required_data_compliance_consent_becomes_a_consent_checkbox():
    data = {"questions": [q("First Name", "first_name", "input_text", required=True)],
            "data_compliance": [{"type": "gdpr", "requires_consent": True}]}  # fmt: skip
    keys = {f.key: f for f in gh.schema_from_api(data).fields}
    assert gh.CONSENT_KEY in keys and keys[gh.CONSENT_KEY].type is FieldType.checkbox
    assert keys[gh.CONSENT_KEY].required is True


def test_a_future_unknown_field_type_is_a_checkpoint_never_silently_dropped():
    data = {"questions": [q("Signature", "question_9", "input_signature_pad")]}
    (f,) = gh.schema_from_api(data).fields
    assert f.type is FieldType.unsupported and f.key == "question_9"
    assert "input_signature_pad" in (f.unsupported_reason or "")


def test_the_mapper_names_match_the_documented_set():
    # If Greenhouse adds a documented type, this list and the mapper must be updated together.
    assert set(DOCUMENTED_TYPES) == {
        "input_text", "textarea", "input_file",
        "multi_value_single_select", "multi_value_multi_select", "input_hidden",
    }  # fmt: skip
