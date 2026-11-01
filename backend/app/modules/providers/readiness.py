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

from app.core import authorizations
from app.modules.providers import path_a, registry
from app.modules.providers.evidence import EVIDENCE_CLASSES
from app.modules.providers.model import Capability

# The rules provider: greenhouse_dom's id mapping, fixture-only, never on a real destination.
# Provider admission (admission.py) keeps computing its row from it.
PROVIDER = "greenhouse_dom"
# D106: the activation checklist is the pilot's. The pilot (D102) applies greenhouse_dom's rules
# under its own name, and it is the only adapter whose real rehearsals and submissions could
# ever be recorded (RehearsalRecord.adapter, ExecutionAttempt.adapter). Computed for
# greenhouse_dom, real_upload, real_submission and capability_entry could never be met.
PILOT = "greenhouse_live"
OBSERVED = {"observed", "live_fill", "live_submit"}
# The capabilities a real application through the pilot uses, each to be raised from fixture to
# observed (or beyond) by a reviewed change once its own real evidence exists (condition 7).
USED_ON_A_REAL_PAGE = (
    Capability.posting_read, Capability.form_extract, Capability.deterministic_fill,
    Capability.custom_dropdowns, Capability.file_upload, Capability.final_submit,
    Capability.confirmation_detection,
)  # fmt: skip
# docs/live-pilot-gate.md: the posting is named by your approval of its package (per
# application, in the app); the permissions are the owner's recorded authorization of each
# step (app/core/authorizations.py, D103). One source of truth: the register.
PILOT_STEPS = ("read", "open", "disclose", "submit")


def recorded_steps() -> list[str]:
    """The pilot steps the owner's recorded authorization covers today."""
    return [s for s in PILOT_STEPS
            if authorizations.covers(authorizations.GREENHOUSE_PILOT, s)]  # fmt: skip


def disclosure_permission_recorded() -> bool:
    """Permissions 1-3 (C): read the post, open its page, disclose. What a rehearsal needs."""
    return {"read", "open", "disclose"} <= set(recorded_steps())


def submission_permission_recorded() -> bool:
    """Permission 4 (D), on top of C."""
    return set(PILOT_STEPS) <= set(recorded_steps())


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

# D106: what each condition needs, and the smallest next step. `needs`: code, observation,
# configuration, consent, owner_machine. `enforced_by`: what stops a real attempt at run time
# whatever this checklist says (the checklist is advisory; it enables nothing). Conditions 1-3
# describe the one posting observed so far: the run-time checks apply them to every posting,
# so a posting without such a control is not blocked by them, but none is met by that.
NEEDS = ("code", "observation", "configuration", "consent", "owner_machine")
PATHS: dict[str, dict] = {
    "dropdowns": {
        "needs": ["observation", "code"],
        "why": "run #11 (read-only, locale files loaded) opened all 12 dropdowns at the "
        "control's click and read 11 lists completely, the 7 mapped ones equal to their job "
        "data; but a required one (u3) showed no readable options, the pilot still refuses the "
        "locale files, and custom_dropdowns stays fixture-level for the pilot",
        "next_action": "the owner's approval of the pilot's locale exception (prepared, D110) "
        "with the first rehearsal, on a posting whose required dropdowns all have readable lists",
        "independent": "path C, click_container and the react-select readback (D109); after "
        "evidence that the lists open, a fixture mirroring it, the pilot's locale exception if "
        "the evidence requires it, and a reviewed change raising custom_dropdowns",
        "owner": "approval of the pilot's locale exception, as part of the rehearsal request",
        "enforced_by": "dropdowns.verify before the disclosure gate: a list it cannot open, "
        "read completely and match exactly stops the attempt before anything is entered",
        "verified_by": "tests/test_dropdown_strategies.py; tests/test_pilot_readiness.py",
    },
    "unmatched_required_controls": {
        "needs": ["observation", "code"],
        "why": "run #11: u1 (required, in the phone group) opened with 244 options and u3 "
        "(required, standalone) opened without readable options; neither matches a question, "
        "and no rule maps them on a real page",
        "next_action": "for a first rehearsal, a posting without such controls; for this one, "
        "the owner's manual note of what u1 and u3 ask (Path A 8a, 8b)",
        "independent": "once their kind is observed: a fixture mirroring them, a mapping rule "
        "for that structure on real pages, its tests, a reviewed change",
        "owner": "Path A answers",
        "enforced_by": "capture refuses a required control the job data does not list (E3); "
        "one that appears after approval stops the attempt before disclosure",
        "verified_by": "tests/test_greenhouse_dom.py (unlisted dropdowns); "
        "tests/test_greenhouse_controls.py",
    },
    "location": {
        "needs": ["observation", "consent", "code"],
        "why": "the observed posting showed no location control at load though its job data "
        "requires one; D104's location search runs on local stand-ins only",
        "next_action": "for a first rehearsal, choose a posting whose job data asks no location; "
        "for this one, the owner notes how its location control appears (typing into it would "
        "be a disclosure, permission 3)",
        "independent": "after an observation: a fixture mirroring the real control and a "
        "reviewed change letting D104's search run on that structure",
        "owner": "the choice of posting; a Path A note on the location control",
        "enforced_by": "a location search on a real page stops the attempt before anything is "
        "entered (STAND_IN_ONLY); hidden coordinates are never written",
        "verified_by": "tests/test_greenhouse_controls.py; tests/test_greenhouse_dom.py",
    },
    "real_upload": {
        "needs": ["consent", "configuration", "owner_machine"],
        "why": "it needs a disclosure-only rehearsal that uploaded a document to a real form "
        "and still holds; none can run: permissions 1-3 are not recorded and the pilot runs "
        "nowhere",
        "next_action": "the owner records permissions 1-3, starts the production configuration "
        "on their machine, and approves a rehearsal of one application",
        "independent": "nothing further in code: the rehearsal scope, its stop before the send "
        "gate, the rehearsal record and its counting exist and are tested",
        "owner": "the permission, the start, the approval, watching the run",
        "enforced_by": "a rehearsal stops before the send gate, which refuses an approval to "
        "disclose only; only a record that still holds on a real destination counts",
        "verified_by": "tests/test_rehearsal_stop.py; tests/test_pilot_readiness.py",
    },
    "real_submission": {
        "needs": ["consent", "owner_machine"],
        "why": "it needs a real final submit confirmed by the employer's page after a valid "
        "rehearsal on that path (E6); permission 4 is not recorded",
        "next_action": "after the rehearsal holds: the owner records permission 4 and approves "
        "the submission of that application",
        "independent": "nothing further in code: one final click, an attempt-bound "
        "confirmation, an uncertain outcome quarantined and never retried",
        "owner": "permission 4 and the approval",
        "enforced_by": "the rehearsal prerequisite at approval, queueing and both gates; the "
        "send gate needs permission 4; no retry after the final click",
        "verified_by": "tests/test_rehearsal_prerequisite.py; tests/test_greenhouse_live.py",
    },
    "pilot_gate": {
        "needs": ["consent"],
        "why": "none of the pilot's four permissions is recorded in app/core/authorizations.py",
        "next_action": "the owner's written permission (the form in docs/activation-status.md), "
        "entered in the register by a reviewed change",
        "independent": "entering the owner's words exactly, with the decision and its test; "
        "never without them",
        "owner": "the words",
        "enforced_by": "live.permission_refusal at capture, routing, queueing, before the page "
        "opens and at both gates",
        "verified_by": "tests/test_greenhouse_live.py; tests/test_authorizations.py; "
        "tests/test_pilot_readiness.py",
    },
    "capability_entry": {
        "needs": ["code"],
        "why": "the reviewed real-destination entry exists (D102); the capabilities a real "
        "application uses are still at fixture level, and only their own real evidence can "
        "raise them",
        "next_action": "after evidence that the dropdowns open, the first real rehearsal and "
        "submission: a reviewed change "
        "raising exactly the capabilities whose evidence then exists",
        "independent": "that change and its tests, once the evidence exists; never before",
        "owner": "nothing beyond the steps that produce the evidence",
        "enforced_by": "the registry's levels and policy.CAPABILITIES; model.PILOTS allows real "
        "destinations to the pilot alone",
        "verified_by": "tests/test_pilot_readiness.py; tests/test_provider_contracts.py",
    },
}


def conditions(
    observation=_UNSET, *, evidence: RecordedEvidence = NO_EVIDENCE, provider: str = PILOT
) -> list[dict]:
    obs = path_a.load() if observation is _UNSET else observation
    advice = path_a.assess(obs)
    spec = registry.get(provider)

    def level(cap: Capability) -> str:
        return spec.support(cap).level()

    from app.modules.execution import policy

    real = spec.real_destinations_enabled
    no_real = (
        "real destinations are enabled (the pilot, off until the owner's permissions are "
        "recorded and it is switched on)"
        if real
        else "real destinations are disabled, so NoEfforts cannot have made one"
    )
    # Condition 7, two parts: a reviewed real-destination capability entry (D102 for the
    # pilot), and every capability a real application uses raised past fixture by evidence.
    entry = real and bool(policy.CAPABILITIES.get(provider, {}).get("real_destinations"))
    still_fixture = [c.value for c in USED_ON_A_REAL_PAGE if level(c) not in OBSERVED]
    steps = recorded_steps()
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
         f"no mapping rule exists for a real page (D104's phone country rule runs on local "
         f"stand-ins only); Path A: u1 {advice['u1']['state']}, u2 {advice['u2']['state']}"),
        ("location", "a supported, evidence-backed way to set the location without writing "
         "hidden coordinates", level(Capability.location_picker) in OBSERVED,
         f"location_picker: {level(Capability.location_picker)}"),
        ("real_upload", "attachments uploaded to a real form, proven on their own",
         real and evidence.rehearsals_valid_with_upload > 0,
         f"file_upload: {level(Capability.file_upload)}; {upload_ev}; {no_real}"),
        ("real_submission", "a real final submit and its confirmation, proven separately",
         real and evidence.real_submissions > 0,
         f"final_submit: {level(Capability.final_submit)}; {submit_ev}; {no_real}"),
        ("pilot_gate", "the owner's separate, recorded permissions for each step (read, "
         "open, disclose, submit), the posting named by the approval of its package",
         set(PILOT_STEPS) <= set(steps),
         "recorded in app/core/authorizations.py: " + (", ".join(steps) or "none")
         + "; missing: " + (", ".join(s for s in PILOT_STEPS if s not in steps) or "none")),
        ("capability_entry", "the capabilities used are raised from fixture to observed, with "
         "a reviewed change to real destinations", entry and not still_fixture,
         ("real-destination entry: reviewed (D102)" if entry
          else f"real_destinations_enabled: {str(real).lower()}")
         + "; still at fixture: " + (", ".join(still_fixture) or "none")),
    ]  # fmt: skip
    return [
        {"id": i, "condition": c, "met": bool(m), "evidence": e, "meets_by": MEETS_BY[i],
         "path": PATHS[i]}
        for i, c, m, e in rows
    ]  # fmt: skip


def evidence_classes(evidence: RecordedEvidence = NO_EVIDENCE, provider: str = PILOT) -> dict:
    """Each evidence class, the conditions it alone can meet, and the caller's counts in it."""
    spec = registry.get(provider)
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


def summary(
    observation=_UNSET, *, evidence: RecordedEvidence = NO_EVIDENCE, provider: str = PILOT
) -> dict:
    obs = path_a.load() if observation is _UNSET else observation
    rows = conditions(obs, evidence=evidence, provider=provider)
    return {
        "provider": provider,
        "scope": evidence.scope,
        "met": sum(r["met"] for r in rows),
        "total": len(rows),
        "proposable": all(r["met"] for r in rows),
        "path_a": "pending" if obs is None else "recorded",
        "conditions": rows,
        "evidence_classes": evidence_classes(evidence, provider),
        "recorded_evidence": asdict(evidence),
    }
