"""Whether a live Greenhouse filling pilot could even be proposed: the seven conditions of
docs/greenhouse-readiness-gap.md ("Before a live filling pilot can be proposed"), each derived
from recorded evidence, never asserted by hand.

A condition is met only by evidence of its own kind (`meets_by`): a capability level the
registry records for the adapter (reaching `observed` needs an approved read-only run), the
live-pilot gate's separate permissions, and for the two real conditions both
`real_destinations` and recorded evidence of their own class: a rehearsal that still holds on a
real destination, or a real submission with an attempt-bound confirmation. Recorded evidence is
the caller's own, counted by the class it was recorded in (execution/rehearsal.py
readiness_evidence); fixture evidence is shown but meets nothing. The owner's manual observation
(Path A) is shown beside the conditions it bears on but meets none: it is advisory. A condition
with no evidence of its kind is not met. Nothing here approves or enables anything, and nothing
here reads the database: the caller passes the counts."""

from dataclasses import asdict, dataclass

from app.modules.providers import path_a, registry
from app.modules.providers.evidence import EVIDENCE_CLASSES
from app.modules.providers.model import Capability

PROVIDER = "greenhouse_dom"
OBSERVED = {"observed", "live_fill", "live_submit"}
# docs/live-pilot-gate.md: the owner names the posting and gives permissions C (disclosure)
# and D (submission) separately. None has been given; none is recorded anywhere.
GATE_PERMISSIONS_RECORDED = False

_UNSET = object()


@dataclass(frozen=True)
class RecordedEvidence:
    """One user's recorded execution evidence for the adapter, by evidence class: counts only,
    never an attempt, host or posting. `baseline`: none read (no user)."""

    scope: str = "baseline"
    fixture_rehearsals: int = 0
    fixture_submissions: int = 0
    rehearsals_valid: int = 0
    rehearsals_valid_with_upload: int = 0
    rehearsals_not_valid: int = 0
    real_submissions: int = 0


NO_EVIDENCE = RecordedEvidence()
# The class (EVIDENCE_CLASSES) or other prerequisite that alone can meet each condition.
MEETS_BY = {
    "dropdowns": "read_only_observation",
    "unmatched_required_controls": "mapping_rule",
    "location": "read_only_observation",
    "real_upload": "rehearsal",
    "real_submission": "real_submission",
    "pilot_gate": "owner_permission",
    "capability_entry": "reviewed_change",
}


def conditions(observation=_UNSET, *, evidence: RecordedEvidence = NO_EVIDENCE) -> list[dict]:
    obs = path_a.load() if observation is _UNSET else observation
    advice = path_a.assess(obs)
    spec = registry.get(PROVIDER)

    def level(cap: Capability) -> str:
        return spec.support(cap).level()

    real = spec.real_destinations_enabled
    no_real = (
        "real destinations are enabled"
        if real
        else "real destinations are disabled, so NoEfforts cannot have made one"
    )
    if evidence.scope == "baseline":
        upload_ev = submit_ev = "recorded evidence: not read (baseline)"
    else:
        fixture = (f"fixture evidence: {evidence.fixture_rehearsals} rehearsal(s) and "
                   f"{evidence.fixture_submissions} submission(s) on local fixtures, never "
                   "counted")  # fmt: skip
        upload_ev = (f"rehearsal evidence: {evidence.rehearsals_valid_with_upload} holding on "
                     f"real destinations with an upload; {fixture}")  # fmt: skip
        submit_ev = (f"real-submission evidence: {evidence.real_submissions} with an "
                     "attempt-bound confirmation after the rehearsal prerequisite held; "
                     f"{fixture}")  # fmt: skip
    rows = [
        ("dropdowns", "each required dropdown opens through one bounded, fixture-tested "
         "strategy, with the complete list", level(Capability.custom_dropdowns) in OBSERVED,
         f"custom_dropdowns: {level(Capability.custom_dropdowns)}; Path A: "
         f"{advice['dropdowns']['state']}"),
        ("unmatched_required_controls", "the two required controls no question matches are "
         "understood and mapped by evidence", False,
         f"no mapping rule exists; Path A: u1 {advice['u1']['state']}, "
         f"u2 {advice['u2']['state']}"),
        ("location", "a supported, evidence-backed way to set the location without writing "
         "hidden coordinates", level(Capability.location_picker) in OBSERVED,
         f"location_picker: {level(Capability.location_picker)}"),
        ("real_upload", "attachments uploaded to a real form, proven on their own",
         real and evidence.rehearsals_valid_with_upload > 0,
         f"file_upload: {level(Capability.file_upload)}; {upload_ev}; {no_real}"),
        ("real_submission", "a real final submit and its confirmation, proven separately",
         real and evidence.real_submissions > 0,
         f"final_submit: {level(Capability.final_submit)}; {submit_ev}; {no_real}"),
        ("pilot_gate", "the owner named the posting and gave separate permissions for "
         "disclosure and submission", GATE_PERMISSIONS_RECORDED,
         "docs/live-pilot-gate.md: no permission given"),
        ("capability_entry", "the capabilities used are raised from fixture to observed, with "
         "a reviewed change to real destinations", real,
         f"real_destinations_enabled: {str(real).lower()}"),
    ]  # fmt: skip
    return [
        {"id": i, "condition": c, "met": bool(m), "evidence": e, "meets_by": MEETS_BY[i]}
        for i, c, m, e in rows
    ]


def evidence_classes(evidence: RecordedEvidence = NO_EVIDENCE) -> dict:
    """Each evidence class, the conditions it alone can meet, and the caller's counts in it."""
    spec = registry.get(PROVIDER)
    observed = sorted(c.value for c in Capability if spec.support(c).level() in OBSERVED)
    counts = {
        "fixture": {"rehearsals": evidence.fixture_rehearsals,
                    "submissions": evidence.fixture_submissions},
        "public_doc_expectation": {},
        "read_only_observation": {"capabilities": observed},
        "rehearsal": {"valid": evidence.rehearsals_valid,
                      "valid_with_upload": evidence.rehearsals_valid_with_upload,
                      "not_valid": evidence.rehearsals_not_valid},
        "real_submission": {"confirmed": evidence.real_submissions},
    }  # fmt: skip
    return {
        c: {"meaning": EVIDENCE_CLASSES[c],
            "meets": [i for i, by in MEETS_BY.items() if by == c],
            "counts": counts[c]}
        for c in EVIDENCE_CLASSES
    }  # fmt: skip


def summary(observation=_UNSET, *, evidence: RecordedEvidence = NO_EVIDENCE) -> dict:
    obs = path_a.load() if observation is _UNSET else observation
    rows = conditions(obs, evidence=evidence)
    return {
        "provider": PROVIDER,
        "scope": evidence.scope,
        "met": sum(r["met"] for r in rows),
        "total": len(rows),
        "proposable": all(r["met"] for r in rows),
        "path_a": "pending" if obs is None else "recorded",
        "conditions": rows,
        "evidence_classes": evidence_classes(evidence),
        "recorded_evidence": asdict(evidence),
    }
