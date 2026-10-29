"""The labelled local test double for drafting (fixture_provider.py) exists only in env "test",
only for accounts matching `drafting_test_fixture_users`, and its drafts pass through every
draft check like any provider's. It sends nothing anywhere. Synthetic data only."""

import pytest

from app.core.config import get_settings
from app.modules.preparation import drafting, fixture_provider
from tests.test_preparation import new_application, setup_candidate

ME = "synthetic.user@example.com"  # the `api` fixture's account


@pytest.fixture
def fixture_users(monkeypatch):
    monkeypatch.setattr(get_settings(), "drafting_test_fixture_users", ["synthetic.user@*"])


def test_only_in_env_test_and_only_for_listed_accounts(monkeypatch, fixture_users):
    s = get_settings()

    class U:
        email = ME

    class Other:
        email = "another.synthetic@example.com"

    assert s.env == "test" and fixture_provider.applies_to(U)
    assert not fixture_provider.applies_to(Other)
    for env in ("development", "production"):
        monkeypatch.setattr(s, "env", env)
        assert not fixture_provider.applies_to(U)


def test_off_by_default():
    class U:
        email = ME

    assert get_settings().drafting_test_fixture_users == []
    assert not fixture_provider.applies_to(U)


def test_a_fixture_draft_passes_the_draft_checks(api, other_api, fixture_users):
    setup_candidate(api)
    app_id = new_application(api)[1]["id"]
    v = api.get(f"/applications/{app_id}/package").json()
    assert v["drafting_status"] == "available"
    r = api.post(f"/applications/{app_id}/drafts", json={"key": "why_us"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["provider"] == fixture_provider.NAME and d["evidence"]
    # Another account is not listed: drafting stays unavailable there.
    setup_candidate(other_api)
    other = new_application(other_api)[1]["id"]
    assert other_api.get(f"/applications/{other}/package").json()["drafting_status"] == (
        "not_configured"
    )


def test_its_text_is_only_the_cited_facts():
    facts = (
        drafting.GroundingFact("employment:1", "employment", "Front Desk at Example: 3 doctors."),
        drafting.GroundingFact("education:1", "education", "Certificate, Example College"),
    )
    req = drafting.DraftRequest("Why us?", None, 40, None, None, None, facts)
    out = fixture_provider.FixtureDraftProvider().draft(req)
    assert (out.text, out.evidence) == ("Front Desk at Example: 3 doctors.", ["employment:1"])
    assert drafting.validate_draft(req, out) == out.text
