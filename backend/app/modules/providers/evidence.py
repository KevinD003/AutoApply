"""The evidence classes NoEfforts keeps apart everywhere (docs/upload-and-submission-evidence.md,
"Evidence classes", is tested against this). A class says where a piece of evidence came from;
it never stands in for another class, and none of them is support on its own."""

from dataclasses import dataclass

EVIDENCE_CLASSES: dict[str, str] = {
    "fixture": "a run against a local, fictional test fixture",
    "public_doc_expectation": "what public documentation describes; unverified, never seen",
    "read_only_observation": "a real page seen read-only in an approved run; never filled there",
    "rehearsal": "a real form filled and checked under an approval to disclose only; nothing "
    "submitted",
    "real_submission": "a real final submit with an attempt-bound confirmation",
}


# -- recorded owner-approved evidence (providers/admission.py reads it; nothing else does) -------
#
# Each approved read-only observation run, transcribed from the Runs table of
# docs/greenhouse-readonly-compatibility-proposal.md (tests/test_provider_contracts.py checks the
# transcription). Run numbers, outcomes and fixed names only: no host, revision, posting or text.
# A run credits a capability or a trait only if it was approved for that one run ("authorized
# once") and completed; a run under an earlier or general approval credits nothing.

RUN_OUTCOMES = ("completed", "stopped", "not_sent", "no_page_evidence")
RUN_APPROVALS = ("single_use", "not_single_use")
# "structure": the controls were seen at load. "behaviour": the capability's own action was
# performed read-only and its effect seen (a read, a mapping). Opening a dropdown with no list
# seen is structure only.
CREDIT_KINDS = ("structure", "behaviour")


@dataclass(frozen=True)
class ReadOnlyRun:
    run: int
    observer: str  # the observation provider that ran it
    outcome: str  # RUN_OUTCOMES
    approval: str  # RUN_APPROVALS
    cells: frozenset[tuple[str, str, str]] = frozenset()  # (provider, capability, credit kind)
    traits: frozenset[tuple[str, str, str]] = frozenset()  # (provider, trait, value)


_READ = frozenset({
    ("greenhouse_readonly", "posting_read", "behaviour"),
    ("greenhouse_readonly", "form_extract", "behaviour"),
    ("greenhouse_dom", "posting_read", "behaviour"),
    ("greenhouse_dom", "form_extract", "behaviour"),
})  # fmt: skip
_DROPDOWNS_SEEN = frozenset({("greenhouse_readonly", "custom_dropdowns", "structure")})
_ONE_PAGE_NO_ACCOUNT = frozenset({
    (p, t, "no") for p in ("greenhouse_readonly", "greenhouse_dom")
    for t in ("login_required", "multi_step")
})  # fmt: skip
_GH = "greenhouse_readonly"
READ_ONLY_RUNS: tuple[ReadOnlyRun, ...] = (
    ReadOnlyRun(1, _GH, "not_sent", "not_single_use"),  # the secret was not set yet
    ReadOnlyRun(2, _GH, "stopped", "not_single_use"),  # under a general statement
    ReadOnlyRun(3, _GH, "completed", "not_single_use"),  # under a general statement
    ReadOnlyRun(4, _GH, "completed", "single_use", _READ, _ONE_PAGE_NO_ACCOUNT),  # B2
    ReadOnlyRun(5, _GH, "completed", "single_use"),  # host identification only
    ReadOnlyRun(6, _GH, "completed", "single_use", _READ, _ONE_PAGE_NO_ACCOUNT),  # B3
    ReadOnlyRun(7, _GH, "no_page_evidence", "single_use"),  # the page observation failed
    ReadOnlyRun(8, _GH, "completed", "single_use",
                frozenset({("greenhouse_readonly", "posting_read", "behaviour")}) | _DROPDOWNS_SEEN,
                _ONE_PAGE_NO_ACCOUNT),  # widget inspection: opened, no list seen
    ReadOnlyRun(9, _GH, "completed", "single_use", _READ | _DROPDOWNS_SEEN,
                _ONE_PAGE_NO_ACCOUNT),  # diagnostic re-observation: not opened within 600 ms
)  # fmt: skip


def _crediting(runs) -> list[ReadOnlyRun]:
    return [r for r in runs if r.approval == "single_use" and r.outcome == "completed"]


def credited_cells(runs=READ_ONLY_RUNS) -> dict[tuple[str, str], frozenset[str]]:
    """{(provider, capability): the credit kinds seen} from crediting runs only."""
    out: dict[tuple[str, str], set[str]] = {}
    for r in _crediting(runs):
        for provider, cap, kind in r.cells:
            out.setdefault((provider, cap), set()).add(kind)
    return {k: frozenset(v) for k, v in out.items()}


def credited_traits(runs=READ_ONLY_RUNS) -> frozenset[tuple[str, str, str]]:
    return frozenset(t for r in _crediting(runs) for t in r.traits)


@dataclass(frozen=True)
class DocReview:
    """The owner's approved review of an ATS's public documentation and terms (an external
    read), recorded as the decision that records it (docs/decisions.md)."""

    ats: str
    decision: str  # "D<n>"


# None has been given or recorded: every ATS stops before `public_doc_reviewed` (a pre-I2
# provider keeps its claim through a frozen waiver; providers/admission.py).
DOC_REVIEWS: tuple[DocReview, ...] = ()
