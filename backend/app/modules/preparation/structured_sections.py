"""D120: education and employment structured sections (Greenhouse), resolution layer.

These sections are NOT part of the Job Board API `questions` array. They are a separate,
documented submission contract, verified against the official Greenhouse Job Board API docs
(grnhse/greenhouse-api-docs, `source/includes/job-board/_educations.md` and `_applications.md`):

  educations[]:  school_name_id, degree_id, discipline_id,
                 start_date{month,year}, end_date{month,year}
  employments[]: company_name, title, start_date{month,year}, current ("true"/"false"),
                 end_date{month,year}  (required only when current is "false"; start before end)

  The `*_id` values come from the per-organization List Schools / List Degrees / List
  Disciplines endpoints (`GET /v1/boards/{token}/education/{schools|degrees|disciplines}`, each
  `{items:[{id,text}], meta:{per_page:100}}`). The ids differ per board, so they are never
  hardcoded here: a record is mapped to an option by its text.

This module is the deterministic RESOLUTION layer only. From the owner's approved education and
employment records and a section's own option lists it produces, per row, the exact values the
section would carry, with field-level provenance. It never infers, never fuzzy-guesses an option
beyond a defensible match grounded in the option's own text, and anything it cannot establish
becomes a checkpoint (`needs_user`).

Deliberately OUT OF SCOPE here (the isolated remaining gaps, not guessed):
  * the rendered hosted-form DOM — the control selectors and the repeating-row indexing of a
    real Greenhouse education/employment section are UNOBSERVED and are not invented. The option
    lists are supplied by the caller (at capture, from the education endpoints) or, in tests, by
    a clearly-labelled synthetic contract fixture.
  * real pages — `package.build_content` freezes a ready section into `content["sections"]`
    (D120 (cont.)), but only a captured local stand-in carries one: capture reads a section on
    stand-ins only, and a real destination refuses a section package before anything is entered.
    `SCHEMA_VERSION` is unchanged (an ordinary form has no `sections` key); D140 shows the frozen
    rows on the review page and in the version diff.
"""

import re
from dataclasses import dataclass, field

from app.modules.preparation.forms import (
    ENTRY_PARTS,
    LIMITED_FIELDS,
    MAX_LIMIT,
    normalize,
    sent_len,
)
from app.modules.profiles.models import Approval
from app.modules.profiles.resume_parse import DATES_NOTE

_BAD_DATE_ORDER = "This record's start date is after its end date; fix it in your profile."

# The ten canonical Greenhouse degree texts, for documentation and fixtures only (the live list
# and its ids come from the degrees endpoint; matching is by text, never by these ids).
CANONICAL_DEGREE_TEXTS = (
    "High School",
    "Associate's Degree",
    "Bachelor's Degree",
    "Master's Degree",
    "Master of Business Administration (M.B.A.)",
    "Juris Doctor (J.D.)",
    "Doctor of Medicine (M.D.)",
    "Doctor of Philosophy (Ph.D.)",
    "Engineer's Degree",
    "Other",
)


@dataclass(frozen=True)
class SectionOption:
    """One `{id, text}` entry from a List Schools/Degrees/Disciplines response."""

    id: str
    text: str


@dataclass(frozen=True)
class EducationOptions:
    """The option lists a captured education section offers (from the education endpoints)."""

    degrees: tuple[SectionOption, ...] = ()
    disciplines: tuple[SectionOption, ...] = ()
    schools: tuple[SectionOption, ...] = ()


@dataclass(frozen=True)
class Choice:
    """D164: the option you chose, for one application, for a record's field that no option
    matches, and what it was chosen against: the option's text, and the record's version and
    text. It applies only while all three are as they were (`_choice_field`)."""

    option_id: str
    option_text: str
    record_version: int | None
    record_text: str


# D164: the fields you may choose an option for, for one application: the record's attribute, the
# field's label, and the list it is chosen from. A field the record leaves empty is never chosen
# for: add it to your record instead.
CHOICE_FIELDS = {
    "school_name_id": ("institution", "school", "schools"),
    "degree_id": ("degree", "degree", "degrees"),
    "discipline_id": ("field_of_study", "field of study", "disciplines"),
}


@dataclass
class FieldResult:
    """One section field's resolution. `status`: resolved | needs_user | omitted. `omitted` is a
    field intentionally not sent (an end date for current employment), never a silent blank."""

    field: str
    status: str
    value: object | None = None
    display: str | None = None
    source: str | None = None
    explanation: str = ""
    fact_refs: list = field(default_factory=list)


@dataclass
class RowResult:
    record_id: str
    record_type: str  # "education" | "employment"
    fields: dict  # field name -> FieldResult


@dataclass
class SectionResult:
    kind: str  # "education" | "employment"
    rows: list  # list[RowResult]
    supported: bool = True
    reason: str = ""  # when not supported

    def ready(self) -> bool:
        """Every field across every row is resolved or intentionally omitted."""
        return self.supported and all(
            fr.status in ("resolved", "omitted") for row in self.rows for fr in row.fields.values()
        )

    def checkpoints(self) -> list[tuple[str, str, str]]:
        """(record_id, field, why) for each field that needs the owner."""
        return [
            (row.record_id, fr.field, fr.explanation)
            for row in self.rows
            for fr in row.fields.values()
            if fr.status == "needs_user"
        ]


def _approved(obj) -> bool:
    return obj is not None and getattr(obj, "approval_status", None) == Approval.approved


def _ref(record, record_type: str, attr: str, value) -> dict:
    """Field-level provenance: references the exact record field used, so changing that field
    (and only that field) would change the section — the same shape resolver._ref produces."""
    return {
        "type": record_type,
        "id": str(record.id),
        "version": getattr(record, "version", None),
        "field": attr,
        "value": value,
    }


# -- option matching -------------------------------------------------------------------------


# D163 review: a trailing parenthetical that is an abbreviation, as written ("M.B.A.", "Ph.D.",
# "MBA"); never a qualifier ("(Other)", "(No Degree)"), which would match a bare "Other".
_ABBREVIATION = re.compile(r"(?:[A-Za-z]{1,4}\.\s?){1,5}|[A-Z]{2,6}")


def _degree_keys(text: str) -> set[str]:
    """Match keys for a degree label, grounded only in the label's own text: the normalized
    text, the text with/without a trailing 'degree', and a trailing parenthetical abbreviation
    (so 'Master of Business Administration (M.B.A.)' also matches 'MBA' / 'M.B.A.'; D163 review:
    only one written as an abbreviation, `_ABBREVIATION`)."""
    n = normalize(text)
    if not n:
        return set()
    keys = {n}
    if n.endswith(" degree"):
        keys.add(n[: -len(" degree")].strip())
    else:
        keys.add(f"{n} degree")
    m = re.search(r"\(([^)]+)\)\s*$", text or "")
    if m and _ABBREVIATION.fullmatch(m.group(1).strip()):
        keys.add(re.sub(r"[.\s]", "", m.group(1)).lower())
    # A dots/spaces-stripped form, so a typed abbreviation ("M.B.A.") reduces to the same token
    # ("mba") as the option's own parenthetical abbreviation.
    stripped = re.sub(r"[.\s]", "", n)
    if stripped:
        keys.add(stripped)
    return {k for k in keys if k}


def match_degree(text: str | None, options: tuple[SectionOption, ...]) -> SectionOption | None:
    """The one degree option whose text matches, by exact text or a defensible variant grounded
    in the option's own text. None when nothing matches or more than one does (never guessed)."""
    want = _degree_keys(text or "")
    if not want:
        return None
    hits = [o for o in options if _degree_keys(o.text) & want]
    return hits[0] if len(hits) == 1 else None


def match_exact(text: str | None, options: tuple[SectionOption, ...]) -> SectionOption | None:
    """The one option whose text is exactly this text (normalized). Used for disciplines and
    schools: large, per-organization lists where only an exact match is safe. Two hits are none."""
    n = normalize(text or "")
    if not n:
        return None
    hits = [o for o in options if normalize(o.text) == n]
    return hits[0] if len(hits) == 1 else None


# -- dates -----------------------------------------------------------------------------------


def _date_hash(d) -> dict | None:
    return {"month": d.month, "year": d.year} if d is not None else None


# -- education -------------------------------------------------------------------------------


def _choice_field(
    name: str, record, record_type, attr, opt, kind_label, options=(), choice=None
) -> FieldResult:
    """A field resolved to one option id (school/degree/discipline), or a checkpoint. D164: a
    field no option matches is resolved by your choice for this application (`choice`), while
    the option is still offered with the same text and the record is as it was when you chose."""
    text = getattr(record, attr, None)
    if not text:
        return FieldResult(name, "needs_user", explanation=f"No {kind_label} on this record.")
    if opt is None:
        if choice is not None:
            chosen = next((o for o in options if o.id == choice.option_id), None)
            if (
                chosen is not None
                and chosen.text == choice.option_text
                and choice.record_version == getattr(record, "version", None)
                and choice.record_text == text
            ):
                return FieldResult(
                    name,
                    "resolved",
                    value={"id": chosen.id},
                    display=chosen.text,
                    source="user_choice",
                    explanation=(
                        f"You chose '{chosen.text}' for your {kind_label} ({text}) for this "
                        "application."
                    ),
                    fact_refs=[_ref(record, record_type, attr, text)],
                )
            return FieldResult(
                name,
                "needs_user",
                explanation=(
                    f"Your {kind_label} ({text}) does not match exactly one option the form "
                    "offers, and the option you chose for this application no longer applies "
                    "(your record or the form's options changed): choose it again."
                ),
                fact_refs=[_ref(record, record_type, attr, text)],
            )
        return FieldResult(
            name,
            "needs_user",
            explanation=(
                f"Your {kind_label} ({text}) does not match exactly one option the form offers; "
                "choose it for this application."
            ),
            fact_refs=[_ref(record, record_type, attr, text)],
        )
    return FieldResult(
        name,
        "resolved",
        value={"id": opt.id},
        display=opt.text,
        source="deterministic_mapping",
        explanation=f"Your {kind_label} ({text}) matched the option '{opt.text}'.",
        fact_refs=[_ref(record, record_type, attr, text)],
    )


def _date_field(name: str, record, record_type, attr, *, required: bool) -> FieldResult:
    d = getattr(record, attr, None)
    if d is None:
        if not required:
            return FieldResult(name, "omitted", explanation="Not applicable.")
        return FieldResult(
            name,
            "needs_user",
            explanation=f"No {attr.replace('_', ' ')} on this record (month and year are needed).",
        )
    return FieldResult(
        name,
        "resolved",
        value=_date_hash(d),
        display=f"{d.month:02d}/{d.year}",
        source="deterministic_mapping",
        explanation=f"From your record's {attr.replace('_', ' ')}.",
        fact_refs=[_ref(record, record_type, attr, d.isoformat())],
    )


def _bad_date_order(start, end) -> bool:
    return start is not None and end is not None and start > end


def matched_option(name: str, text: str | None, options: EducationOptions) -> SectionOption | None:
    """The option a choice field's text matches by itself (D120's rules), or None."""
    lst = CHOICE_FIELDS[name][2]
    match = match_degree if name == "degree_id" else match_exact
    return match(text, getattr(options, lst))


def resolve_education_row(record, options: EducationOptions, choices=None) -> RowResult:
    """D164: `choices` maps (record id, field) to your `Choice` for this application."""
    choices = choices or {}

    def choice_field(name: str) -> FieldResult:
        attr, label, lst = CHOICE_FIELDS[name]
        text = getattr(record, attr, None)
        chosen = choices.get((str(record.id), name))
        return _choice_field(name, record, "education", attr,
                             matched_option(name, text, options), label,
                             getattr(options, lst), chosen)  # fmt: skip

    fields = {
        "school_name_id": choice_field("school_name_id"),
        "degree_id": choice_field("degree_id"),
        "discipline_id": choice_field("discipline_id"),
        "start_date": _date_field("start_date", record, "education", "start_date", required=True),
        "end_date": _date_field("end_date", record, "education", "end_date", required=True),
    }
    if _bad_date_order(getattr(record, "start_date", None), getattr(record, "end_date", None)):
        for k in ("start_date", "end_date"):
            fields[k] = FieldResult(k, "needs_user", explanation=_BAD_DATE_ORDER)
    return RowResult(str(record.id), "education", fields)


def open_choices(records, options: EducationOptions, choices=None) -> list[dict]:
    """D164: each approved record's field that has your text and no option matching it by itself:
    what the form offers for it, and your choice for this application when one applies (`stale`:
    one was made, and no longer applies). Never a field the record leaves empty."""
    choices = choices or {}
    out = []
    for record in [r for r in records if _approved(r)]:
        row = resolve_education_row(record, options, choices)
        for name, (attr, label, lst) in CHOICE_FIELDS.items():
            text = getattr(record, attr, None)
            if not text or matched_option(name, text, options) is not None:
                continue
            fr = row.fields[name]
            chosen = fr.status == "resolved"
            out.append({
                "key": f"section:education:{record.id}:{name}",
                "record_id": str(record.id),
                "record_version": getattr(record, "version", None),
                "field": name,
                "label": label,
                "your_text": text,
                "options": [{"id": o.id, "text": o.text} for o in getattr(options, lst)],
                "chosen": {"id": fr.value["id"], "text": fr.display} if chosen else None,
                "stale": not chosen and (str(record.id), name) in choices,
            })  # fmt: skip
    return out


# -- employment ------------------------------------------------------------------------------


def _text_field(name: str, record, attr, label: str) -> FieldResult:
    text = getattr(record, attr, None)
    if not text or not text.strip():
        return FieldResult(name, "needs_user", explanation=f"No {label} on this record.")
    if "\n" in text or "\r" in text:  # D149 review: a form's text box cannot hold one
        return FieldResult(
            name, "needs_user",
            explanation=f"This record's {label} has a line break, which a form cannot hold; "
            "fix it in your profile.",
        )  # fmt: skip
    return FieldResult(
        name, "resolved", value={"text": text}, display=text, source="profile_fact",
        explanation=f"From your record's {label}.",
        fact_refs=[_ref(record, "employment", attr, text)],
    )  # fmt: skip


def _part_field(name: str, record, label: str, *, required: bool, lines: bool) -> FieldResult:
    """D155: a part an entry asks beyond the five always sent (Location, Role Description), from
    your record's own text, never inferred. Blank on the record: not sent, unless the page
    requires it (then the owner's to add). `lines`: a text area takes line breaks (each
    written as one LF, as a text area's value holds them); a text box does not."""
    text = getattr(record, name, None)
    if not text or not text.strip():
        if required:
            return FieldResult(
                name, "needs_user",
                explanation=f"The employer's form requires a {label} for each role, and this "
                "record has none; add it in your profile.",
            )  # fmt: skip
        return FieldResult(name, "omitted", explanation=f"No {label} on this record: none is sent.")
    if lines:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if any(line.startswith(DATES_NOTE) for line in text.split("\n")):
            return FieldResult(
                name, "needs_user",
                explanation=f"This record's {label} still holds the note NoEfforts added when "
                "it read your resume (\"Dates as written\"); edit it in your profile.",
            )  # fmt: skip
    elif "\n" in text or "\r" in text:
        return FieldResult(
            name, "needs_user",
            explanation=f"This record's {label} has a line break, which a form cannot hold; "
            "fix it in your profile.",
        )  # fmt: skip
    return FieldResult(
        name, "resolved", value={"text": text}, display=text, source="profile_fact",
        explanation=f"From your record's {label}.",
        fact_refs=[_ref(record, "employment", name, getattr(record, name))],
    )  # fmt: skip


EMPLOYMENT_PARTS = ENTRY_PARTS  # D155: as SectionSpec.parts, sorted
# D157: what each limited field is called when your record's is too long for the page.
_LIMIT_LABELS = {"company_name": "employer", "description": "role description",
                 "location": "location", "title": "job title"}  # fmt: skip
assert tuple(sorted(_LIMIT_LABELS)) == LIMITED_FIELDS


def _within(fields: dict, limits: dict) -> dict:
    """D157: a resolved field whose text is longer than the page accepts (`maxlength`, counted as
    its form sends it, `sent_len`) becomes yours to shorten: never cut, never sent cut. Its length
    and the limit are named, never its text."""
    for name, limit in limits.items():
        fr = fields.get(name)
        if fr is None or fr.status != "resolved" or not isinstance(fr.display, str):
            continue
        n = sent_len(fr.display)
        if n > limit:
            fields[name] = FieldResult(
                name, "needs_user",
                explanation=f"The employer's form accepts at most {limit} characters for the "
                f"{_LIMIT_LABELS[name]}, and this record's has {n} (a line break or an emoji "
                "counts as two); shorten it in your profile.",
            )  # fmt: skip
    return fields


def resolve_employment_row(record, parts=(), required_parts=(), limits=None) -> RowResult:
    """D120's five fields; D155: and the parts a section's entry asks beyond them (`parts`, from
    EMPLOYMENT_PARTS), only when it asks them, so every other section resolves as before. D157:
    each held to the page's length limit, where it has one (`limits`, by field name)."""
    is_current = getattr(record, "is_current", False)
    fields = {
        "company_name": _text_field("company_name", record, "employer", "employer"),
        "title": _text_field("title", record, "title", "job title"),
        "start_date": _date_field("start_date", record, "employment", "start_date", required=True),
        "current": FieldResult(
            "current",
            "resolved",
            value={"bool": bool(is_current)},
            display="Current" if is_current else "Not current",
            source="profile_fact",
            explanation="From your record.",
            fact_refs=[_ref(record, "employment", "is_current", bool(is_current))],
        ),  # fmt: skip
    }
    if is_current:
        # The contract omits end_date for a current role; never invent one.
        fields["end_date"] = FieldResult(
            "end_date", "omitted", explanation="Current role: no end date is sent."
        )
    else:
        fields["end_date"] = _date_field(
            "end_date", record, "employment", "end_date", required=True
        )
    if not is_current and _bad_date_order(
        getattr(record, "start_date", None), getattr(record, "end_date", None)
    ):
        for k in ("start_date", "end_date"):
            fields[k] = FieldResult(k, "needs_user", explanation=_BAD_DATE_ORDER)
    if "location" in parts:
        fields["location"] = _part_field(
            "location", record, "location", required="location" in required_parts, lines=False
        )
    if "description" in parts:
        fields["description"] = _part_field(
            "description", record, "role description",
            required="description" in required_parts, lines=True,
        )  # fmt: skip
    return RowResult(str(record.id), "employment", _within(fields, limits or {}))


# -- section reconciliation ------------------------------------------------------------------

SUPPORTED_KINDS = ("education", "employment")


def resolve_section(
    kind: str,
    records: list,
    *,
    options: EducationOptions | None = None,
    parts: tuple = (),
    required_parts: tuple = (),
    limits: dict | None = None,
    choices: dict | None = None,
) -> SectionResult:
    """Resolve one structured section from the owner's approved records, in record order. An
    unsupported section kind, or an education section with no option lists to match against,
    is returned as an explicit checkpoint (`supported=False`) rather than guessed. D164:
    `choices`, your choices for this application (education only)."""
    if kind not in SUPPORTED_KINDS:
        return SectionResult(kind, [], supported=False, reason=f"Unsupported section '{kind}'.")
    limits = dict(limits or {})
    if (parts or required_parts or limits) and kind != "employment":  # D155: never ignored silently
        return SectionResult(
            kind, [], supported=False, reason="The section's entries ask something unknown."
        )
    approved = [r for r in records if _approved(r)]
    if kind == "education":
        if options is None:
            return SectionResult(
                kind,
                [],
                supported=False,
                reason="Education option lists were not captured; this section stays a checkpoint.",
            )
        return SectionResult(kind, [resolve_education_row(r, options, choices) for r in approved])
    unknown = set(parts) - set(EMPLOYMENT_PARTS)
    bad_limits = (not set(limits) <= set(LIMITED_FIELDS)  # D157: never a limit guessed at
                  or not set(limits) & set(EMPLOYMENT_PARTS) <= set(parts)
                  or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX_LIMIT
                         for v in limits.values()))  # fmt: skip
    if unknown or bad_limits or not set(required_parts) <= set(parts):  # never a part guessed at
        return SectionResult(
            kind, [], supported=False, reason="The section's entries ask something unknown."
        )
    return SectionResult(
        kind, [resolve_employment_row(r, parts, required_parts, limits) for r in approved]
    )
