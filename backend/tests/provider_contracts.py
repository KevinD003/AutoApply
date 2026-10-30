"""Data for tests/test_provider_contracts.py: the identity contract every ATS name must meet,
the probes that show each known gap still exists, and the receipt keys each adapter may keep.
Every company and posting id is fictional, lookalike hosts end in .invalid, and nothing here is
ever requested."""

from app.modules.jobs.canonical import canonicalize_url, detect_ats
from app.modules.preparation import greenhouse as gh
from app.modules.providers import routing

UUID = "0b9c6d2e-1f3a-4e5b-8c7d-9a0b1c2d3e4f"
LEVER = f"https://jobs.lever.co/acme/{UUID}"
WORKDAY = "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_R-100001"

# For each ATS name (jobs.canonical.ATS_NAMES): a posting and what it identifies as; variants
# that must identify the same (case, region, suffix); tracking parameters that must not change
# its dedupe key; and URLs that must not be identified at all. `foreign_form`: the route a job
# on this ATS gets with a form captured as another ATS's, or from a local approximation with no
# ATS identity such as the Lever-style one (D85) (None: no such source exists).
IDENTITY_CASES: dict[str, dict] = {
    "greenhouse": {
        "positive": ("https://boards.greenhouse.io/acme/jobs/4000001", ("acme", "4000001")),
        "variants": ["https://job-boards.greenhouse.io/Acme/jobs/4000001",
                     "https://boards.eu.greenhouse.io/acme/jobs/4000001/"],
        "tracking": "?gh_src=feed&utm_source=board",
        "not_ats": ["https://www.greenhouse.io/", "https://boards.greenhouse.io/acme",
                    "https://boards.greenhouse.io.example.invalid/acme/jobs/4000001",
                    "https://boards.greenhouse.io/acme/jobs/not-a-number"],
        "foreign_form": "form_ats_mismatch",  # a Lever-style approximation's form (D85)
    },
    "lever": {
        "positive": (LEVER, ("acme", UUID)),
        "variants": [f"https://jobs.lever.co/Acme/{UUID}/apply", f"https://jobs.eu.lever.co/acme/{UUID}"],
        "tracking": "?lever-source=feed",
        "not_ats": ["https://www.lever.co/", "https://jobs.lever.co/acme",
                    "https://jobs.lever.co/acme/not-a-posting-id",
                    f"https://jobs.lever.co.example.invalid/acme/{UUID}"],
        "foreign_form": "planned_adapter_only",
    },
    "ashby": {
        "positive": (f"https://jobs.ashbyhq.com/acme/{UUID}", ("acme", UUID)),
        "variants": [f"https://jobs.ashbyhq.com/Acme/{UUID}/application"],
        "tracking": "?utm_source=feed",
        "not_ats": ["https://www.ashbyhq.com/", "https://jobs.ashbyhq.com/acme",
                    f"https://jobs.ashbyhq.com.example.invalid/acme/{UUID}"],
        "foreign_form": "form_ats_mismatch",
    },
    "workable": {
        "positive": ("https://apply.workable.com/acme/j/AB12CD34EF", ("acme", "AB12CD34EF")),
        "variants": ["https://apply.workable.com/Acme/j/AB12CD34EF/apply/"],
        "tracking": "?utm_source=feed&utm_medium=board",
        "not_ats": ["https://www.workable.com/", "https://apply.workable.com/acme/",
                    "https://apply.workable.com.example.invalid/acme/j/AB12CD34EF"],
        "foreign_form": "form_ats_mismatch",
    },
    "workday": {
        "positive": (WORKDAY, ("acme", "R-100001")),
        "variants": ["https://ACME.wd1.myworkdayjobs.com/External/job/Remote/Engineer_R-100001"],
        "tracking": "?source=feed&utm_campaign=board",
        "not_ats": ["https://www.workday.com/", "https://acme.wd5.myworkdayjobs.com/en-US/External",
                    "https://acme.wd5.myworkdayjobs.com.example.invalid/x/Engineer_R-100001"],
        "foreign_form": "planned_adapter_only",
    },
    "smartrecruiters": {
        "positive": ("https://jobs.smartrecruiters.com/acme/743999000000001-engineer",
                     ("acme", "743999000000001")),
        "variants": ["https://jobs.smartrecruiters.com/Acme/743999000000001"],
        "tracking": "?utm_source=feed",
        "not_ats": ["https://www.smartrecruiters.com/", "https://jobs.smartrecruiters.com/acme",
                    "https://jobs.smartrecruiters.com.example.invalid/acme/743999000000001"],
        "foreign_form": "form_ats_mismatch",
    },
}  # fmt: skip


def _ats(url: str) -> str:
    return detect_ats(canonicalize_url(url)).provider


# Each known gap (providers/admission.py KNOWN_GAPS) is True here while any behaviour it records
# still reproduces: a gap is removed only once all of it is fixed.
_EMBED = "https://boards.greenhouse.io/embed/job_app?for=acme&token=4000001"
PROBES = {
    # gh_jid on any host, and on a host merely containing the vendor's domain.
    "identity_jid_any_host": lambda: any(_ats(u) == "greenhouse" for u in (
        "https://careers.example.invalid/openings?gh_jid=4000001",
        "https://boards.greenhouse.io.example.invalid/x?gh_jid=4000001"))
    or _ats(f"https://careers.example.invalid/jobs?ashby_jid={UUID}") == "ashby",
    # The posting parser and the identity rules disagree on a Greenhouse URL form.
    "identity_rules_disagree": lambda: any(
        (_ats(u) == "greenhouse") != (gh.parse_posting(u, fixture_origin=False) is not None)
        for u in (_EMBED, "https://boards.greenhouse.io/acme/jobs/4000001/apply",
                  "https://boards.greenhouse.io/acme/jobs/4000001abc",
                  "https://boards.greenhouse.io/" + "a" * 101 + "/jobs/4000001")),
    "identity_unknown_skips_form_check": lambda: routing._identity_refusal(
        {"url": "https://careers.example.invalid/apply", "form_source": "greenhouse_api_dom"}, [])
    is None,
    "identity_stored_unknown_not_redetected": lambda: routing._identity_refusal(
        {"url": LEVER, "ats_provider": "unknown"}, []) is None,
    "identity_variant_unrecognised": lambda: _ats(f"{WORKDAY}/apply") == "unknown",
}  # fmt: skip

# The keys each adapter's receipt evidence may keep (docs/upload-and-submission-evidence.md:
# receipt id, confirmation, final origin, HTTP status; the API keeps a digest of its receipt).
RECEIPT_KEYS = {
    "fixture_ats": {"receipt_id", "final_origin", "http_status"},
    "greenhouse_hosted": {"receipt_id", "confirmation", "final_origin", "http_status"},
    "greenhouse_dom": {"receipt_id", "confirmation", "final_origin", "http_status"},
    "fake_api": {"route", "receipt_ref_sha256", "http_status"},
    "fixture_lever": {"receipt_id", "confirmation", "final_origin", "http_status"},
}

# The ledger test that shows each scenario an execution provider's fixture levels require
# (providers/admission.py required_scenarios). Mapped by a read-only search and an adversarial
# check of each mapping; tests/test_provider_contracts.py checks every entry structurally.
_EF, _GH, _GD = ("tests/test_execution_failures.py", "tests/test_greenhouse_adapter.py",
                 "tests/test_greenhouse_dom.py")  # fmt: skip
_UP, _API = "tests/test_upload_evidence.py", "tests/test_api_provider.py"
_LV = "tests/test_lever_adapter.py"
_RECONCILE = f"{_EF}::test_reconciling_an_unknown_outcome_never_sends_again"
SCENARIO_TESTS: dict[tuple[str, str], str] = {
    ("fixture_ats", "full_run_matches_ledger"):
        "tests/test_execution.py::test_happy_path_submits_once_with_receipt",
    ("fixture_ats", "changed_form_stops_before_disclosure"):
        f"{_EF}::test_receiver_failure_modes",  # the conditional_field case
    ("fixture_ats", "unknown_outcome_never_resent"): f"{_EF}::test_accepted_but_response_dropped",
    ("fixture_ats", "readback_mismatch_stops_before_submit"):
        "tests/test_execution_validation.py::test_page_altering_a_filled_value_stops_before_submit",
    ("fixture_ats", "upload_failure_stops_with_evidence"):
        f"{_UP}::test_a_refused_upload_is_kept_as_refused",
    ("fixture_ats", "code_entered_by_user_only"):
        "tests/test_execution_security.py::test_code_checkpoint_wrong_then_right_code_and_replay",
    ("fixture_ats", "rejection_is_not_confirmation"):
        f"{_EF}::test_receiver_failure_modes",  # the validation_fail case
    ("fixture_ats", "reconcile_never_resends"): _RECONCILE,
    ("fixture_ats", "confirmation_bound_to_attempt"): f"{_EF}::test_confirmation_bound_to_attempt",
    ("greenhouse_hosted", "full_run_matches_ledger"):
        f"{_GH}::test_full_run_is_confirmed_and_sends_exactly_the_approved_values",
    ("greenhouse_hosted", "changed_form_stops_before_disclosure"):
        f"{_GH}::test_form_changed_after_approval_stops_before_disclosure",
    ("greenhouse_hosted", "unknown_outcome_never_resent"): f"{_GH}::test_outcome_classification",
    ("greenhouse_hosted", "readback_mismatch_stops_before_submit"):
        f"{_GH}::test_page_altering_a_filled_value_stops_before_submit",
    ("greenhouse_hosted", "upload_failure_stops_with_evidence"):
        f"{_UP}::test_a_failed_upload_keeps_the_evidence_of_every_upload_before_it",
    ("greenhouse_hosted", "challenge_stops_before_disclosure"):
        f"{_GH}::test_captcha_stops_before_anything_is_disclosed",
    ("greenhouse_hosted", "code_entered_by_user_only"):
        f"{_GH}::test_security_code_wrong_then_right",
    ("greenhouse_hosted", "rejection_is_not_confirmation"): f"{_GH}::test_outcome_classification",
    ("greenhouse_hosted", "reconcile_never_resends"): _RECONCILE,
    ("greenhouse_hosted", "confirmation_bound_to_attempt"):
        f"{_GH}::test_confirmation_bound_to_attempt",
    ("greenhouse_hosted", "each_step_read_back_before_next"):
        f"{_GH}::test_each_step_read_back_before_next_a_second_page_stops_before_disclosure",
    ("greenhouse_dom", "full_run_matches_ledger"):
        f"{_GD}::test_full_run_sends_exactly_the_approved_values",
    ("greenhouse_dom", "changed_form_stops_before_disclosure"):
        f"{_GD}::test_drift_after_approval_stops_before_anything_is_disclosed",
    ("greenhouse_dom", "unknown_outcome_never_resent"): f"{_GD}::test_outcome_classification",
    ("greenhouse_dom", "readback_mismatch_stops_before_submit"):
        f"{_GD}::test_combobox_that_does_not_keep_its_choice_is_caught_by_readback",
    ("greenhouse_dom", "upload_failure_stops_with_evidence"):
        f"{_UP}::test_a_failed_upload_keeps_the_evidence_of_every_upload_before_it",
    ("greenhouse_dom", "challenge_stops_before_disclosure"):
        f"{_GD}::test_a_captcha_on_the_form_stops_before_anything_is_disclosed",
    ("greenhouse_dom", "rejection_is_not_confirmation"): f"{_GD}::test_outcome_classification",
    ("greenhouse_dom", "reconcile_never_resends"): _RECONCILE,
    ("greenhouse_dom", "confirmation_bound_to_attempt"):
        f"{_GD}::test_confirmation_bound_to_attempt",
    ("greenhouse_dom", "unlisted_option_is_checkpoint"):
        f"{_GD}::test_unlisted_option_is_checkpoint",
    ("fake_api", "full_run_matches_ledger"):
        f"{_API}::test_authorized_api_submission_sends_exactly_the_approved_package",
    ("fake_api", "changed_form_stops_before_disclosure"):
        f"{_API}::test_refusals_before_disclosure",
    ("fake_api", "unknown_outcome_never_resent"):
        f"{_API}::test_accepted_but_response_lost_is_unknown_and_never_resent",
    ("fake_api", "upload_failure_stops_with_evidence"):
        f"{_UP}::test_the_api_route_keeps_the_same_evidence",
    ("fake_api", "rejection_is_not_confirmation"): f"{_API}::test_outcomes_after_sending",
    ("fake_api", "no_grant_never_contacted"):
        f"{_API}::test_without_authorization_the_api_is_never_contacted",
    ("fake_api", "reconcile_never_resends"):
        f"{_API}::test_accepted_but_response_lost_is_unknown_and_never_resent",
    ("fake_api", "confirmation_bound_to_attempt"): f"{_API}::test_confirmation_bound_to_attempt",
    ("fixture_lever", "full_run_matches_ledger"):
        f"{_LV}::test_full_run_sends_exactly_the_approved_values_and_byte_identical_documents",
    ("fixture_lever", "changed_form_stops_before_disclosure"):
        f"{_LV}::test_form_changed_after_approval_stops_before_disclosure",
    ("fixture_lever", "unknown_outcome_never_resent"):
        f"{_LV}::test_an_uncertain_final_send_is_quarantined_and_never_retried",
    ("fixture_lever", "readback_mismatch_stops_before_submit"):
        f"{_LV}::test_a_parsed_resume_that_changes_a_field_stops_before_submit",
    ("fixture_lever", "upload_failure_stops_with_evidence"):
        f"{_LV}::test_a_partial_upload_failure_keeps_the_evidence_of_the_earlier_disclosure",
    ("fixture_lever", "challenge_stops_before_disclosure"):
        f"{_LV}::test_a_bot_check_that_appears_after_approval_stops_before_disclosure",
    ("fixture_lever", "rejection_is_not_confirmation"):
        f"{_LV}::test_outcomes_after_the_final_click",
    ("fixture_lever", "reconcile_never_resends"): _RECONCILE,
    ("fixture_lever", "confirmation_bound_to_attempt"):
        f"{_LV}::test_confirmation_bound_to_attempt",
}  # fmt: skip
# What a scenario test must name to exercise its provider: its builder, or the provider itself.
BUILDERS = {
    "fixture_ats": ("prepared_application", "fixture_ats"),
    "greenhouse_hosted": ("gh_application", "greenhouse_hosted"),
    "greenhouse_dom": ("v2_application", "greenhouse_dom"),
    "fake_api": ("api_application", "fake_api", "fapi_requests"),
    "fixture_lever": ("lever_application", "fixture_lever"),
}
