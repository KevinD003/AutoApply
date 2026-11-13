"""Greenhouse job posts: posting identity and form schema.

Two independent views of one application form are combined and cross-checked:
  * the job post JSON of the public Job Board API (`questions=true`): exact question wording,
    description, required flag and typed fields;
  * the rendered hosted form: the submit target and which questions only show conditionally.
If they disagree the form is not captured; nothing is guessed.

Access basis, kept distinct (see docs/first-adapter-proposal.md): reading a public job post is
not permission to submit. Only fixture origins are read here; reading real Greenhouse posts is
not enabled. Field mapping covers the documented types; anything else becomes an explicit
`unsupported` field (a checkpoint when required), never a guess.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from app.modules.preparation.forms import (
    SENT_OTHERWISE,
    Condition,
    FieldType,
    FormField,
    FormSchema,
    Option,
    extract_form_schema,
    field_fingerprint,
)

EXTRACTION_VERSION = "greenhouse-v1"
REAL_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io",
              "job-boards.eu.greenhouse.io")  # fmt: skip


@dataclass(frozen=True)
class Posting:
    board: str
    job_id: str
    fixture: bool
    fixture_prefix: str = "gh"  # local fixtures: "gh" (v1 structure) or "gh2" (v2 structure)

    @property
    def ref(self) -> str:
        return f"{self.board}/{self.job_id}"


def parse_posting(url: str, *, fixture_origin: bool) -> Posting | None:
    """Board token and job id from a hosted-board URL (real hosts or the local fixture)."""
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if fixture_origin:
        m = re.fullmatch(r"/(gh2?)/([A-Za-z0-9_-]{1,100})/jobs/(\d{1,20})/?", p.path)
        return Posting(m.group(2), m.group(3), True, m.group(1)) if m else None
    if host in REAL_HOSTS:
        m = re.fullmatch(r"/([A-Za-z0-9_-]{1,100})/jobs/(\d{1,20})/?", p.path)
        if m:
            return Posting(m.group(1), m.group(2), False)
        q = parse_qs(p.query)
        if p.path.rstrip("/") == "/embed/job_app" and q.get("for") and q.get("token"):
            return Posting(q["for"][0], q["token"][0], False)
    return None


def api_url(posting: Posting, origin: str) -> str:
    if posting.fixture:
        pre = f"{origin}/{posting.fixture_prefix}-api"
        return f"{pre}/v1/boards/{posting.board}/jobs/{posting.job_id}?questions=true"
    return f"https://boards-api.greenhouse.io/v1/boards/{posting.board}/jobs/{posting.job_id}?questions=true"


class SchemaMismatch(ValueError):
    """The form's structure is unsupported or incomplete. `code` is a fixed reason code; the
    message gives counts only, never the posting's field keys, labels or addresses."""

    def __init__(self, message: str, code: str = "form_structure_mismatch"):
        super().__init__(message)
        self.code = code


# -- JSON → schema -----------------------------------------------------------------------------
_TEXT_BY_NAME = {"email": FieldType.email, "phone": FieldType.tel}
_FILE_ACCEPT = ".pdf,.doc,.docx,.txt,.rtf"
CONSENT_KEY = "gdpr_processing_consent_given"
CONSENT_LABEL = "Data processing consent (wording taken from the application page)"


def _options(values: list[dict]) -> list[Option]:
    return [Option(value=str(v["value"]), label=str(v["label"])) for v in values]


def _field(q: dict) -> FormField:
    label, required, desc = q["label"], bool(q.get("required")), q.get("description") or None
    fields = q.get("fields") or []
    # "Attach or paste" questions: the attachment is used; the paste box is an alternative.
    files = [f for f in fields if f["type"] == "input_file"]
    f = files[0] if files else (fields[0] if len(fields) == 1 else None)
    if f is None:
        return FormField(
            key=_safe_key(fields[0]["name"] if fields else label),
            label=label,
            help_text=desc,
            type=FieldType.unsupported,
            required=required,
            unsupported_reason="question with several inputs",
        )
    name, t = f["name"], f["type"]
    common = {"label": label, "help_text": desc, "required": required}
    if t == "input_text":
        return FormField(key=name, type=_TEXT_BY_NAME.get(name, FieldType.text), **common)
    if t == "textarea":
        return FormField(key=name, type=FieldType.textarea, **common)
    if t == "input_file":
        return FormField(key=name, type=FieldType.file, accept=_FILE_ACCEPT, **common)
    if t == "multi_value_single_select":
        return FormField(key=name, type=FieldType.select, options=_options(f["values"]), **common)
    if t == "multi_value_multi_select":
        return FormField(
            key=f"{name}[]", type=FieldType.checkbox_group, options=_options(f["values"]), **common
        )
    reason = (
        "hidden value normally set by the page (for example map coordinates)"
        if t == "input_hidden"
        else f"control type '{t}' is not supported"
    )
    return FormField(key=name, type=FieldType.unsupported, unsupported_reason=reason, **common)


def _safe_key(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:\[\]-]+", "_", s)[:200] or "field"


DEMOGRAPHIC_PREFIX = "demographic_question_"


def _demographic_field(q: dict) -> FormField:
    """D120: one Greenhouse-Inclusion demographic question
    (demographic_questions.questions[]). Keyed with DEMOGRAPHIC_PREFIX so classify treats it as
    sensitive even when its wording is neutral (e.g. "Favorite Color"): the applicant's own
    explicit choice, never inferred, never saved. A question that offers a free-form ("type your
    own") option is shown but left for the applicant to answer, so a changed option set and
    free-text entry are never guessed."""
    opts = q.get("answer_options") or []
    label = str(q.get("label") or "Demographic question")[:2000]
    required = bool(q.get("required"))
    key = f"{DEMOGRAPHIC_PREFIX}{_safe_key(str(q.get('id')))}"
    common = {"key": key, "label": label, "required": required}
    if any(o.get("free_form") for o in opts) or not opts:
        return FormField(
            type=FieldType.unsupported,
            unsupported_reason="a demographic question with a free-form answer: you answer it",
            **common,
        )
    options = [Option(value=str(o["id"]), label=str(o["label"])) for o in opts]
    t = q.get("type")
    if t == "multi_value_multi_select":
        return FormField(type=FieldType.checkbox_group, options=options, **common)
    return FormField(type=FieldType.select, options=options, **common)


def schema_from_api(data: dict) -> FormSchema:
    fields = [_field(q) for q in (data.get("questions") or [])]
    fields += [_field(q) for q in (data.get("location_questions") or [])]
    # D120: EEOC (compliance[]) has the same shape as questions; its labels (Gender, Race,
    # Veteran Status, Disability Status) classify as sensitive on their own. Greenhouse-Inclusion
    # demographic questions (demographic_questions{}) are keyed so they are sensitive too. Both
    # are the applicant's own explicit choice: never inferred, never saved for reuse. A parse
    # failure leaves the section out, so it stays a checkpoint on the page (fail-closed).
    for q in data.get("compliance") or []:
        try:
            fields.append(_field(q))
        except (KeyError, TypeError, ValueError):
            continue
    demo = data.get("demographic_questions") or {}
    for q in demo.get("questions") or []:
        try:
            fields.append(_demographic_field(q))
        except (KeyError, TypeError, ValueError):
            continue
    if any(d.get("requires_consent") for d in data.get("data_compliance") or []):
        fields.append(
            FormField(key=CONSENT_KEY, label=CONSENT_LABEL, type=FieldType.checkbox, required=True)
        )
    return FormSchema(title=str(data.get("title") or "")[:300] or None, fields=fields)


# -- rendered form ---------------------------------------------------------------------------
class _Conditions(HTMLParser):
    """Maps each control name to the `data-show-if` of its enclosing wrapper, if any."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []
        self.found: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("input", "select", "textarea"):
            cond = next((c for _, c in reversed(self.stack) if c), None)
            if cond and a.get("name"):
                self.found.setdefault(a["name"], cond)
            return
        self.stack.append((tag, a.get("data-show-if")))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def rendered_schema(html: str, *, sent_rule: bool = True) -> FormSchema:
    """The hosted form as rendered: generic extraction plus show-if conditions. `sent_rule`
    (D159): as `extract_form_schema`'s; off only for the cross-check with the job data."""
    schema = extract_form_schema(html, sent_rule=sent_rule)
    p = _Conditions()
    p.feed(html)
    out = []
    for f in schema.fields:
        cond = p.found.get(f.key)
        if cond:
            key, _, value = cond.partition("=")
            f = f.model_copy(update={"condition": Condition(key=key, any_of=[value])})
        out.append(f)
    return schema.model_copy(update={"fields": out})


def comparable(fields: list[FormField]) -> dict[str, str]:
    """Per-key fingerprints of what both views can see (hidden page-set values are API-only)."""
    return {
        f.key: field_fingerprint(f)
        for f in fields
        if not (
            f.type == FieldType.unsupported and (f.unsupported_reason or "").startswith("hidden")
        )
    }


def _as_on_page(f: FormField, on_page: dict[str, FormField]) -> FormField:
    """D159: a question as the page has it where the job data says nothing about it:
    * refused, where its control on the page would not send exactly what is typed into it
      (`forms.sent_otherwise`), whatever type the job data gives it: never filled, a required
      one a checkpoint;
    * held to the page's own length limit (`maxlength`, read as the browser reads it): the job
      data states none, so a limit the page lowers is recorded when the form is read again,
      rather than found only by the attempt. (Before D159 the page's limit was never read.)"""
    page = on_page.get(f.key)
    if page is None:
        return f
    if page.unsupported_reason == SENT_OTHERWISE:
        return f.model_copy(update={"type": FieldType.unsupported, "options": [],
                                    "unsupported_reason": SENT_OTHERWISE, "max_length": None,
                                    "accept": None})  # fmt: skip
    if f.max_length is None and page.max_length is not None:
        return f.model_copy(update={"max_length": page.max_length})
    return f


def build_schema(api: dict, hosted_html: str) -> FormSchema:
    """Combine and cross-check the two views; raises SchemaMismatch on any difference. D159: the
    views are compared as the page's controls read without D159's rule (`sent_rule`), so a type
    the page's control disagrees on is still a difference; what the page refuses, and its
    limits, are taken from it after (`_as_on_page`)."""
    from_api = schema_from_api(api)
    compared = rendered_schema(hosted_html, sent_rule=False)
    dom = rendered_schema(hosted_html)
    conds = {f.key: f.condition for f in dom.fields if f.condition}
    on_page = {f.key: f for f in dom.fields}
    # The job data only says consent is required; its wording is what the page shows.
    fields = [
        on_page[f.key] if f.key == CONSENT_KEY and f.key in on_page else f
        for f in (f.model_copy(update={"condition": conds.get(f.key)}) for f in from_api.fields)
    ]
    a, d = comparable(fields), comparable(compared.fields)
    if a != d:
        only_api, only_page = sorted(set(a) - set(d)), sorted(set(d) - set(a))
        changed = sorted(k for k in set(a) & set(d) if a[k] != d[k])
        raise SchemaMismatch(
            "the job post data and the application page disagree"
            + (f"; {len(only_api)} only in job data" if only_api else "")
            + (f"; {len(only_page)} only on the page" if only_page else "")
            + (f"; {len(changed)} different" if changed else ""),
            "form_sources_disagree",
        )
    if not dom.action or (dom.method or "").lower() != "post":
        raise SchemaMismatch("the application page has no form to submit", "no_submittable_form")
    fields = [f if f.key == CONSENT_KEY else _as_on_page(f, on_page) for f in fields]
    return FormSchema(title=from_api.title, action=dom.action, method="post", fields=fields)
