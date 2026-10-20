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
    pass


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


def schema_from_api(data: dict) -> FormSchema:
    fields = [_field(q) for q in (data.get("questions") or [])]
    fields += [_field(q) for q in (data.get("location_questions") or [])]
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


def rendered_schema(html: str) -> FormSchema:
    """The hosted form as rendered: generic extraction plus show-if conditions."""
    schema = extract_form_schema(html)
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


def build_schema(api: dict, hosted_html: str) -> FormSchema:
    """Combine and cross-check the two views; raises SchemaMismatch on any difference."""
    from_api = schema_from_api(api)
    dom = rendered_schema(hosted_html)
    conds = {f.key: f.condition for f in dom.fields if f.condition}
    on_page = {f.key: f for f in dom.fields}
    # The job data only says consent is required; its wording is what the page shows.
    fields = [
        on_page[f.key] if f.key == CONSENT_KEY and f.key in on_page else f
        for f in (f.model_copy(update={"condition": conds.get(f.key)}) for f in from_api.fields)
    ]
    a, d = comparable(fields), comparable(dom.fields)
    if a != d:
        only_api, only_page = sorted(set(a) - set(d)), sorted(set(d) - set(a))
        changed = sorted(k for k in set(a) & set(d) if a[k] != d[k])
        raise SchemaMismatch(
            "the job post data and the application page disagree"
            + (f"; only in job data: {', '.join(only_api)}" if only_api else "")
            + (f"; only on the page: {', '.join(only_page)}" if only_page else "")
            + (f"; different: {', '.join(changed)}" if changed else "")
        )
    if not dom.action or (dom.method or "").lower() != "post":
        raise SchemaMismatch("the application page has no form to submit")
    return FormSchema(title=from_api.title, action=dom.action, method="post", fields=fields)
