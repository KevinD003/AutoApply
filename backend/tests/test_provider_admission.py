"""Provider admission (I2, providers/admission.py, docs/provider-admission.md): each registered
provider's stage is computed from code tables and recorded evidence, what it claims never ranks
above it, every check is reachable and breakable, owner boundaries are never passed without
their record, nothing passes the cap, and computing it reads nothing and changes nothing.
The example provider (tests/admission_example.py) is synthetic and never registered."""

import ast
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import replace

import pytest

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import sanitize
from app.modules.execution import policy
from app.modules.providers import admission, evidence, path_a, readiness, registry, wording
from app.modules.providers.evidence import EVIDENCE_CLASSES, ReadOnlyRun
from app.modules.providers.model import Capability, Support
from tests import admission_example as ex
from tests.conftest import Api

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
DOC = ROOT / "docs" / "provider-admission.md"
IDENT = re.compile(r"[a-z][a-z0-9_]{0,47}")
GH_GAPS = ["identity_jid_any_host", "identity_rules_disagree",
           "identity_stored_unknown_not_redetected"]  # fmt: skip
GH_EXEC_GAPS = sorted([*GH_GAPS, "identity_unknown_skips_form_check"])
# What the code yields today (track, claimed, admitted, next, blocking, waived, gaps, end).
EXPECTED = {
    "fixture_ats": ("generic_execution", "fixture_only", "fixture_only", None, [], [], [],
                    "no_ats_identity"),
    "fake_api": ("generic_execution", "fixture_only", "fixture_only", None, [], [], [],
                 "no_ats_identity"),
    # D85: the Lever-style approximation's adapter has no Lever identity, so it ends on the
    # generic track; real Lever stays the planned specification below.
    "fixture_lever": ("generic_execution", "fixture_only", "fixture_only", None, [], [], [],
                      "no_ats_identity"),
    "greenhouse_hosted": ("ats_execution", "fixture_only", "fixture_only", "observed_read_only",
                          ["doc_review_recorded", "observed_cells_credited"],
                          ["doc_review_recorded"], GH_EXEC_GAPS, None),
    "greenhouse_dom": ("ats_execution", "observed_read_only", "observed_read_only",
                       "rehearsal_ready",
                       ["doc_review_recorded", "readiness_dropdowns",
                        "readiness_unmatched_required_controls", "readiness_location",
                        "known_gaps_closed"],
                       ["doc_review_recorded"], GH_EXEC_GAPS, None),
    "greenhouse_readonly": ("observation", "observed_read_only", "observed_read_only", None, [],
                            ["doc_review_recorded"], GH_GAPS, "read_only_by_kind"),
    "freehire_mock": ("discovery", "fixture_only", "fixture_only", None, [], [], [],
                      "discovery_by_kind"),
    "freehire": ("discovery", "fixture_only", "fixture_only", None, [], [], [],
                 "discovery_by_kind"),
    "workday": ("ats_execution", "planned", "planned", "public_doc_reviewed",
                ["doc_review_recorded"], [],
                ["identity_stored_unknown_not_redetected", "identity_variant_unrecognised"], None),
    "lever": ("ats_execution", "planned", "planned", "public_doc_reviewed",
              ["doc_review_recorded"], [], ["identity_stored_unknown_not_redetected"], None),
    "manual_handoff": ("manual", "manual", "registered", None, [], [], [], "handoff_by_kind"),
}  # fmt: skip
FIELDS = ("track", "claimed", "admitted", "next", "blocking", "waived", "known_gaps", "end")


@pytest.fixture(autouse=True)
def _nothing_registered():
    """No test here may add a provider to the registry: the example lives in table copies."""
    before = set(registry.PROVIDERS)
    yield
    assert set(registry.PROVIDERS) == before


def row(key, tables=None):
    return admission.evaluate(key, tables)


def status(r, check_id):
    return {c["id"]: c["status"] for c in r["checks"]}[check_id]


# -- the registered providers ---------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_each_registered_provider_gets_its_computed_admission(key):
    r = row(key)
    assert tuple(r[f] for f in FIELDS) == EXPECTED[key]


def test_every_registered_provider_is_admitted_to_what_it_claims():
    """The support state a page shows (providers/wording.py) never ranks above admission: a
    registry raise without the code and recorded evidence behind it fails here."""
    assert set(EXPECTED) == set(registry.PROVIDERS)
    for key in registry.PROVIDERS:
        assert row(key)["within_claim"], key


def test_no_registered_text_names_an_identifier_or_claims_support():
    for key in registry.PROVIDERS:
        r = row(key)
        assert status(r, "text_names_nothing") == "met", key
        assert status(r, "text_claims_nothing") == "met", key


def test_the_summary_by_ats_shows_identities_with_no_provider():
    by_ats = admission.summary()["ats"]
    assert by_ats["greenhouse"]["admitted"] == "observed_read_only"
    assert (by_ats["lever"]["admitted"], by_ats["workday"]["admitted"]) == ("planned", "planned")
    for ats in ("ashby", "workable", "smartrecruiters"):  # identified, nothing else exists
        assert by_ats[ats] == {"providers": [], "admitted": "not_admitted", "waived": []}


# -- the checks: every requirement covered, every check reachable and breakable --------------------


def test_every_requirement_has_a_check():
    covered = [c.requirement for c in admission.CHECKS]
    assert set(covered) == set(admission.REQUIREMENTS)
    assert all(c.stage in admission.STAGES[1:] for c in admission.CHECKS)
    assert len({c.id for c in admission.CHECKS}) == len(admission.CHECKS)


def test_every_check_has_exactly_one_sabotage():
    assert set(ex.SABOTAGE) == {c.id for c in admission.CHECKS}


@pytest.mark.parametrize("check", [c.id for c in admission.CHECKS])
def test_every_check_is_met_on_the_complete_example(check):
    key, tables = ex.subject(check)
    assert status(row(key, tables), check) == "met"


@pytest.mark.parametrize("check", [c.id for c in admission.CHECKS])
def test_every_check_is_caught_by_its_sabotage(check):
    """Breaking the one thing a check reads makes it not met and stops the provider before
    the check's stage; a check that can never fail, or fails for another reason, fails here."""
    key, tables = ex.subject(check)
    stage = next(c.stage for c in admission.CHECKS if c.id == check)
    before = {c["id"]: c["status"] for c in row(key, tables)["checks"]}
    r = row(key, ex.SABOTAGE[check](tables))
    assert status(r, check) == "not_met"
    broken = {i for i, s in before.items() if s == "met" and status(r, i) == "not_met"}
    assert broken == {check} | ex.ALSO_BREAKS.get(check, set())
    assert admission._rank(r["admitted"]) < admission._rank(stage)
    if r["next"] and admission._rank(stage) <= admission._rank(r["next"]):
        assert check in r["blocking"]


@pytest.mark.parametrize("stage", ex.REACHABLE)
def test_the_example_reaches_each_stage_only_when_its_requirements_are_met(stage):
    assert row(ex.KEY, ex.tables(stage))["admitted"] == stage


def test_every_code_is_a_fixed_identifier_safe_to_record():
    a = admission
    codes = ({c.id for c in a.CHECKS} | {a.CAP} | set(a.TRACK_ENDS.values())
             | set(a.WAIVABLE.values()) | set(a.KNOWN_GAPS) | set(a.STATUSES) | set(a.STAGES)
             | set(a.TRACKS) | set(a.OWNER_BOUNDARIES.values()))  # fmt: skip
    for code in codes:
        assert IDENT.fullmatch(code), code
        assert sanitize({"reason_code": code}) == {"reason_code": code}, code


def test_every_track_end_is_produced():
    ends = {row(k)["end"] for k in registry.PROVIDERS} - {None}
    assert ends == set(admission.TRACK_ENDS.values())


def test_basis_uses_only_known_evidence_vocabulary():
    known = {"code"} | set(EVIDENCE_CLASSES) | set(readiness.MEETS_BY.values())
    assert {c.basis for c in admission.CHECKS} <= known


def test_stage_names_reuse_the_support_vocabulary():
    assert set(admission.CLAIM_STAGE) == set(wording.SUPPORT_LABELS) | {"live"}
    assert set(admission.CLAIM_STAGE.values()) <= set(admission.STAGES)
    for name, track in admission.TRACKS.items():
        assert list(track) == sorted(track, key=admission._rank), name


# -- owner boundaries, the cap and waivers ---------------------------------------------------------


def test_nothing_passes_the_real_destination_cap():
    r = row(ex.KEY, ex.complete())  # every check met, permissions and a live label included
    assert (r["admitted"], r["next"], r["blocking"]) == ("rehearsal_ready", "rehearsed",
                                                         [admission.CAP])  # fmt: skip
    assert r["owner_boundary_next"] == "disclosure_permission"


@pytest.mark.parametrize(
    "boundary,remove,stops_at",
    [
        ("public_doc_reviewed", lambda t: replace(t, doc_reviews=t.doc_reviews - {ex.ATS}),
         "planned"),
        ("observed_read_only", lambda t: replace(t, credited_cells={}), "fixture_only"),
        ("rehearsed", lambda t: replace(t, disclosure_permission_recorded=False),
         "rehearsal_ready"),
        ("live", lambda t: replace(t, submission_permission_recorded=False), "rehearsed"),
    ],
)  # fmt: skip
def test_an_owner_boundary_is_never_passed_without_its_record(boundary, remove, stops_at,
                                                              monkeypatch):  # fmt: skip
    """Even with the cap lifted (here only), a stage the owner opens needs its record."""
    monkeypatch.setattr(admission, "MAX_REACHABLE", "live")
    assert row(ex.KEY, ex.complete())["admitted"] == "live"  # the cap was all that stopped it
    r = row(ex.KEY, remove(ex.complete()))
    assert r["admitted"] == stops_at and r["next"] == boundary
    assert r["owner_boundary_next"] == admission.OWNER_BOUNDARIES[boundary]


def test_a_waiver_never_advances_a_provider_beyond_its_claim():
    """greenhouse_dom with every rehearsal condition met in memory and its gaps closed still
    stops at its claim: its waived doc review counts only up to observed_read_only."""
    t = admission.current_tables()
    rows = [{"id": c, "met": True} for c in readiness.MEETS_BY]
    cells = {**t.credited_cells,
             **{("greenhouse_dom", c): frozenset({"behaviour"})
                for c in ("custom_dropdowns", "location_picker")}}  # fmt: skip
    t = replace(t, readiness={"greenhouse_dom": lambda: rows}, known_gaps={},
                credited_cells=cells)  # fmt: skip
    r = row("greenhouse_dom", t)
    assert (r["admitted"], r["blocking"]) == ("observed_read_only", ["doc_review_recorded"])
    assert status(r, "doc_review_recorded") == "waived"


def test_waivers_are_frozen_to_the_pre_admission_providers_and_still_real():
    assert set(admission.PRE_ADMISSION) == {
        "fixture_ats", "greenhouse_hosted", "greenhouse_dom", "fake_api", "greenhouse_readonly",
        "freehire_mock", "freehire", "workday", "lever", "manual_handoff",
    }  # fmt: skip
    for key, stage in admission.PRE_ADMISSION.items():  # each frozen at the claim it had at I2
        assert stage == admission.CLAIM_STAGE[wording.support_state(registry.get(key))], key
    t = admission.current_tables()
    unwaived = replace(t, waivers={})
    for (key, check), reason in admission.GRANDFATHERED.items():
        assert key in admission.PRE_ADMISSION and admission.WAIVABLE[check] == reason
        assert status(row(key, t), check) == "waived"
        assert status(row(key, unwaived), check) == "not_met"  # each waiver covers a real gap


def test_a_waiver_for_a_new_provider_has_no_effect():
    t = ex.SABOTAGE["doc_review_recorded"](ex.complete())
    t = replace(
        t, waivers={**t.waivers, (ex.KEY, "doc_review_recorded"): "terms_review_unrecorded"}
    )
    assert status(row(ex.KEY, t), "doc_review_recorded") == "not_met"


# -- readiness and recorded evidence ---------------------------------------------------------------


def test_no_stage_needs_evidence_only_a_later_stage_produces():
    assert admission.CLAIM_GUARDS <= {c.id for c in admission.CHECKS}
    for c in admission.CHECKS:
        if c.basis in admission.EVIDENCE_PRODUCED_AT and c.id not in admission.CLAIM_GUARDS:
            assert admission._rank(c.stage) >= admission._rank(
                admission.EVIDENCE_PRODUCED_AT[c.basis]
            ), c.id
    for cond, stage in admission.READINESS_STAGE.items():
        produced = admission.EVIDENCE_PRODUCED_AT[readiness.MEETS_BY[cond]]
        assert admission._rank(stage) >= admission._rank(produced), cond


def test_every_readiness_condition_belongs_to_one_stage():
    generated = {c.id for c in admission.CHECKS if c.id.startswith("readiness_")} - {
        "readiness_profile_defined"
    }
    assert generated == {f"readiness_{c}" for c in readiness.MEETS_BY}
    assert set(admission.READINESS_STAGE) == set(readiness.MEETS_BY)


def test_a_structure_only_observation_never_meets_a_rehearsal_condition(monkeypatch):
    """Raise greenhouse_dom's dropdowns to observed in memory: the readiness module counts the
    level, but admission also needs a behaviour credit, and the runs credit structure only."""
    gd = registry.PROVIDERS["greenhouse_dom"]
    raised = {**gd.capabilities, Capability.custom_dropdowns: Support(fixture=True, observed=True)}
    monkeypatch.setitem(registry.PROVIDERS, "greenhouse_dom", replace(gd, capabilities=raised))
    assert {r["id"]: r["met"] for r in readiness.conditions(None)}["dropdowns"]
    t = admission.current_tables()
    cells = {**t.credited_cells, ("greenhouse_dom", "custom_dropdowns"): frozenset({"structure"})}
    assert status(row("greenhouse_dom", replace(t, credited_cells=cells)),
                  "readiness_dropdowns") == "not_met"  # fmt: skip
    r = row(ex.KEY, ex.STRUCTURE_ONLY(ex.complete()))
    assert status(r, "readiness_dropdowns") == status(r, "readiness_location") == "not_met"


def test_the_owners_manual_observation_changes_no_admission(monkeypatch):
    before = admission.summary()
    favourable = path_a.Observation(
        answers={q: opts[0] for q, opts in path_a.QUESTIONS.items()},
        observed_on="2026-10-01", dropdowns_checked=2)  # fmt: skip
    monkeypatch.setattr(path_a, "load", lambda: favourable)
    assert admission.summary() == before


def test_a_run_without_its_own_approval_or_not_completed_credits_nothing():
    cells = frozenset({("greenhouse_dom", "posting_read", "behaviour")})
    traits = frozenset({("greenhouse_dom", "login_required", "no")})
    for approval, outcome in (
        ("not_single_use", "completed"),
        ("single_use", "stopped"),
        ("single_use", "no_page_evidence"),
        ("single_use", "not_sent"),
    ):
        run = ReadOnlyRun(99, "greenhouse_readonly", outcome, approval, cells, traits)
        assert evidence.credited_cells((run,)) == {} and not evidence.credited_traits((run,))
    run = ReadOnlyRun(99, "greenhouse_readonly", "completed", "single_use", cells, traits)
    assert evidence.credited_cells((run,)) and evidence.credited_traits((run,)) == traits


def test_every_observed_cell_is_credited_by_a_completed_single_use_run():
    credited = evidence.credited_cells()
    for p in registry.PROVIDERS.values():
        for cap, s in p.capabilities.items():
            if s.observed:
                assert (p.name, cap.value) in credited, (p.name, cap)
    for r in evidence.READ_ONLY_RUNS:
        assert r.outcome in evidence.RUN_OUTCOMES and r.approval in evidence.RUN_APPROVALS
        assert r.observer in admission.current_tables().observers
        assert all(k in evidence.CREDIT_KINDS for _, _, k in r.cells)


def test_no_doc_review_is_recorded_today():
    """Pinned empty: recording one needs the owner's approval and a decision, and edits this."""
    assert evidence.DOC_REVIEWS == ()


# -- isolation: reads nothing, changes nothing, imported by nothing that acts ---------------------


def test_admission_reads_no_database_and_no_repository_file(monkeypatch):
    before = admission.summary()  # every module it needs is imported now

    def refuse(*a, **kw):
        raise AssertionError("admission read something")

    import builtins

    from app.core import db

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(pathlib.Path, "read_text", refuse)
    monkeypatch.setattr(pathlib.Path, "open", refuse)
    monkeypatch.setattr(db, "SessionLocal", refuse)
    assert admission.summary() == before


def test_admission_imports_no_browser_code():
    code = ("import sys; from app.modules.providers import admission; admission.summary(); "
            "print([m for m in sys.modules if m.split('.')[0] == 'playwright' "
            "or m == 'app.modules.execution.runner'])")  # fmt: skip
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", capture_output=True,
                         text=True, timeout=120)  # fmt: skip
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "[]"


def test_computing_admission_changes_nothing(api):
    def state():
        return (json.dumps(registry.summary(), sort_keys=True),
                json.dumps(readiness.summary(None), sort_keys=True),
                dict(policy.ADAPTER_VERSIONS),
                {k: wording.support_state(p) for k, p in registry.PROVIDERS.items()})  # fmt: skip

    from app.core.db import SessionLocal

    before = state()
    with SessionLocal() as s:
        events = s.query(AuditEvent).count()
    admission.summary()
    assert api.get("/providers/admission").status_code == 200
    assert state() == before
    with SessionLocal() as s:
        assert s.query(AuditEvent).count() == events


def test_nothing_routes_labels_or_approves_on_admission():
    """Only the providers API imports admission: no route, label, approval or gate reads it."""
    importers = set()
    for path in APP.rglob("*.py"):
        for n in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(n, ast.ImportFrom) and n.module:
                names = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
            elif isinstance(n, ast.Import):
                names = [a.name for a in n.names]
            if "app.modules.providers.admission" in names:
                importers.add(path.relative_to(APP).as_posix())
    assert importers == {"modules/providers/router.py"}


# -- served ---------------------------------------------------------------------------------------


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, item in v.items():
            yield k
            yield from _strings(item)
    elif isinstance(v, list):
        for item in v:
            yield from _strings(item)


def test_served_admission_carries_only_fixed_identifiers():
    """Registry keys, ATS names, stages, tracks, checks, statuses, codes: no note, status line,
    host, posting or label can be served."""
    for s in _strings(admission.summary()):
        assert IDENT.fullmatch(s), s


def test_the_api_serves_admission(api):
    r = api.get("/providers/admission")
    assert r.status_code == 200 and r.json() == json.loads(json.dumps(admission.summary()))
    assert Api().get("/providers/admission").status_code == 401


# -- the documentation is the code -----------------------------------------------------------------


def _table(text: str, heading: str) -> list[list[str]]:
    block = text.split(heading, 1)[1]
    lines = block.split("\n|", 1)[1].split("\n\n", 1)[0]
    rows = [r for r in ("|" + lines).splitlines() if r.startswith("|")]
    return [[c.strip().strip("`") for c in r.strip("|").split("|")] for r in rows[2:]]


def test_the_documented_admission_tables_are_the_code():
    text = DOC.read_text()
    reqs = [r[1] for r in _table(text, "## The eleven requirements")]
    assert reqs == list(admission.REQUIREMENTS)
    tracks = {r[0]: [s.strip().strip("`") for s in r[1].split(",")]
              for r in _table(text, "## Tracks and stages")}  # fmt: skip
    assert tracks == {k: list(v) for k, v in admission.TRACKS.items()}
    owners = {r[0]: r[1] for r in _table(text, "## Owner boundaries")}
    assert owners == admission.OWNER_BOUNDARIES
    checks = [(r[0], r[1], r[2], r[3]) for r in _table(text, "## Checks")]
    assert checks == [(c.id, c.requirement, c.stage, c.basis) for c in admission.CHECKS]
    today = {r[0]: (r[1], r[2], r[3], r[4] if r[4] != "–" else None)
             for r in _table(text, "## Admission today")}  # fmt: skip
    assert today == {k: (row(k)["track"], row(k)["claimed"], row(k)["admitted"], row(k)["next"])
                     for k in registry.PROVIDERS}  # fmt: skip
    waivers = {(r[0], r[1]): r[2] for r in _table(text, "## Waivers")}
    assert waivers == admission.GRANDFATHERED
    gaps = {r[0]: sorted(s.strip().strip("`") for s in r[1].split(","))
            for r in _table(text, "## Known gaps")}  # fmt: skip
    assert gaps == {k: sorted(v) for k, v in admission.KNOWN_GAPS.items()}


def test_raising_a_claim_never_raises_a_waiver():
    """greenhouse_hosted raised in memory to observed, with credited runs: its waived doc review
    still counts only up to its frozen claim (fixture_only), so the raise is caught."""
    t = admission.current_tables()
    gh = t.providers["greenhouse_hosted"]
    seen = Support(fixture=True, observed=True)
    raised = replace(gh, capabilities={**gh.capabilities, Capability.posting_read: seen,
                                       Capability.form_extract: seen})  # fmt: skip
    cells = {**t.credited_cells, **{("greenhouse_hosted", c): frozenset({"behaviour"})
                                    for c in ("posting_read", "form_extract")}}  # fmt: skip
    r = row("greenhouse_hosted", replace(t, providers={**t.providers, "greenhouse_hosted": raised},
                                         credited_cells=cells))  # fmt: skip
    assert r["claimed"] == "observed_read_only" and r["admitted"] == "fixture_only"
    assert r["blocking"] == ["doc_review_recorded"] and not r["within_claim"]


def test_a_new_adapter_under_a_pre_admission_key_inherits_no_waiver():
    """An implemented adapter registered as "lever" (the planned spec's key) with every required
    scenario recorded as a gap and waived: the waiver counts only up to "planned", the frozen
    claim of that key, so the adapter is not admitted to fixture_only on it."""
    base = admission.current_tables()
    t = ex.tables("fixture_only", base)
    lever = replace(t.providers[ex.KEY], name="lever", ats="lever")
    gaps = frozenset(("lever", s) for s in admission.required_scenarios(lever))
    t = replace(t, providers={**{k: v for k, v in t.providers.items() if k != ex.KEY},
                              "lever": lever},
                browser_capabilities={**t.browser_capabilities,
                                      "lever": t.browser_capabilities[ex.KEY]},
                adapter_versions={**t.adapter_versions, "lever": ex.VERSION},
                form_source_adapters={ex.SOURCE: "lever"},
                form_source_ats={ex.SOURCE: "lever"},
                doc_reviews=t.doc_reviews | {"lever"}, scenario_gaps=gaps,
                waivers={**t.waivers,
                         ("lever", "fixture_scenarios_complete"): "scenario_untested"})  # fmt: skip
    r = row("lever", t)
    assert status(r, "fixture_scenarios_complete") == "waived"
    assert r["admitted"] == "public_doc_reviewed" and not r["within_claim"]


def test_the_by_ats_view_shows_what_is_held_only_by_a_waiver():
    gh = admission.summary()["ats"]["greenhouse"]
    assert gh["admitted"] == "observed_read_only" and gh["waived"] == ["doc_review_recorded"]
    assert admission.summary()["ats"]["lever"]["waived"] == []


@pytest.mark.parametrize(
    "key,kind,ats,safe",
    [
        ("exampleats_form", "browser", "exampleats", True),
        ("exampleats", "browser", "exampleats", True),
        ("acme_form", "browser", "exampleats", False),  # not named after its ATS
        ("ExampleATS_form", "browser", "exampleats", False),  # not a lowercase identifier
        ("exampleats_" + "x" * 40, "browser", "exampleats", False),  # too long
        ("fixture_example", "browser", None, True),
        ("example_form", "browser", None, False),  # a generic adapter is fixture_ or fake_
        ("fake_example", "api", None, True),
        ("manual_example", "manual", None, True),
        ("handoff", "manual", None, False),
    ],
)  # fmt: skip
def test_a_key_is_safe_only_when_named_after_its_ats_or_kind(key, kind, ats, safe):
    from app.modules.providers.model import Kind

    spec = replace(ex.spec("fixture_only"), name=key, kind=Kind(kind), ats=ats)
    t = ex.tables("fixture_only")
    x = admission.Ctx(key, spec, replace(t, providers={**t.providers, key: spec}))
    assert admission._key_is_safe(x) is safe


@pytest.mark.parametrize(
    "text",
    ["seen on https://example.invalid/x", "write to someone@example.invalid",
     "observed on careers.acme.de", "jobs.acme.eu posting", "boards.acme.ch",
     "posting 8c7e5a3f-1b2c-4d5e-9f00-a1b2c3d4e5f6", "req R0012345", "job 4012001"],
)  # fmt: skip
def test_text_naming_an_identifier_is_caught(text):
    assert admission.names_identifier(text)


@pytest.mark.parametrize(
    "text",
    ["docs/provider-architecture.md §7", "providers/evidence.py", "runs #3-#9 and D45",
     "Playwright 1.56.0", "e.g. a checkpoint, i.e. never solved", "fixture design",
     "the user's grant plus a token"],
)  # fmt: skip
def test_text_naming_no_identifier_passes(text):
    assert not admission.names_identifier(text)


def test_manual_evidence_that_would_change_a_condition_is_caught():
    """Path A recorded in any way leaves every readiness condition as it was (computed); if it
    did not, the check would not be met."""
    t = admission.current_tables()
    assert status(row("greenhouse_dom", t), "manual_evidence_meets_nothing") == "met"
    t = replace(t, manual_evidence_inert={"greenhouse_dom": lambda: False})
    assert status(row("greenhouse_dom", t), "manual_evidence_meets_nothing") == "not_met"
