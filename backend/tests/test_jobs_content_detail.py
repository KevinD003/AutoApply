"""D125 (Slice D): the job-detail API surfaces the full, structured, sanitized `content` —
the complete description (not the truncated summary), the source's own sections, and salary with
its provenance — consolidated from the discovery records that list the job, with the job's own
saved text as the fallback. Synthetic data only."""

import uuid

from app.core.db import SessionLocal
from app.modules.discovery.boards import normalize as board_normalize
from app.modules.discovery.models import DiscoveredJob
from app.modules.jobs.models import Job


def _link_discovered(job_id: uuid.UUID, normalized: dict, provider: str, source_job_id: str):
    """Attach a discovery record (as a provider's normalizer produced it) to an existing job."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        db.add(
            DiscoveredJob(
                user_id=job.user_id,
                provider=provider,
                source_job_id=source_job_id,
                fingerprint=normalized.get("raw_fingerprint", "x")[:64],
                normalized=normalized,
                source_facts=normalized.get("source_facts") or {},
                status="linked",
                job_id=job_id,
                link_basis="job_url",
            )
        )
        db.commit()


def test_detail_shows_full_lever_content_with_structured_salary(api):
    created = api.post("/jobs", json={"title": "Nurse", "employer": "Globex (fictional)"}).json()
    job_id = created["job"]["id"]
    n = board_normalize(
        "lever",
        "src-1",
        "Globex (fictional)",
        {
            "id": "p-1",
            "text": "Nurse",
            "hostedUrl": "https://jobs.example.test/globex/p-1",
            "description": "<p>Care for synthetic patients.</p><script>steal()</script>",
            "lists": [
                {"text": "Responsibilities", "content": "<ul><li>Give care</li></ul>"},
                {"text": "Requirements", "content": "<ul><li>Licensed</li></ul>"},
            ],
            "categories": {
                "commitment": "Full-time",
                "department": "Clinical",
                "allLocations": ["Shelbyville", "Remote - US"],
            },
            "salaryRange": {
                "min": 70000,
                "max": 90000,
                "currency": "USD",
                "interval": "per-year-salary",
            },
        },  # fmt: skip
    ).as_dict()
    _link_discovered(job_id, n, "board:lever", "src-1:p-1")

    detail = api.get(f"/jobs/{job_id}").json()
    content = detail["content"]
    assert content["origin"] == "discovery"
    # The whole description is present (not a 500-char summary) and the script is gone.
    text = " ".join(s["text"] for b in content["description"]["blocks"] for s in b.get("spans", []))
    assert "Care for synthetic patients." in text and "steal" not in text
    headings = [s["heading"] for s in content["description"]["sections"]]
    assert "Responsibilities" in headings and "Requirements" in headings
    assert content["salary"]["source"] == "structured"
    assert content["salary"]["currency"] == "USD" and content["salary"]["period"] == "year"
    assert content["facts"]["employment_type"] == "Full-time"
    assert content["facts"]["department"] == "Clinical"
    assert content["facts"]["locations"] == ["Shelbyville", "Remote - US"]
    assert content["facts"]["source_url"] == "https://jobs.example.test/globex/p-1"


def test_detail_falls_back_to_your_own_text_and_extracts_its_salary(api):
    created = api.post(
        "/jobs",
        json={
            "title": "Welder",
            "employer": "Acme (fictional)",
            "description": "Shop welder. Pay is $28 per hour. Great team.",
        },
    ).json()
    detail = api.get(f"/jobs/{created['job']['id']}").json()
    content = detail["content"]
    assert content["origin"] == "your_entry"
    assert content["salary"]["source"] == "extracted"
    assert content["salary"]["period"] == "hour" and content["salary"]["amount"] == "28"


def test_detail_says_nothing_when_no_salary_is_known(api):
    created = api.post(
        "/jobs",
        json={
            "title": "Clerk",
            "employer": "Initech (fictional)",
            "description": "Front desk. Competitive pay and benefits.",
        },  # fmt: skip
    ).json()
    content = api.get(f"/jobs/{created['job']['id']}").json()["content"]
    # salary is null: the UI then shows "Salary not provided." — nothing is invented.
    assert content["salary"] is None
    assert content["origin"] == "your_entry"


def test_detail_content_is_empty_shape_for_a_bare_job(api):
    created = api.post("/jobs", json={"title": "Analyst", "employer": "Hooli (fictional)"}).json()
    content = api.get(f"/jobs/{created['job']['id']}").json()["content"]
    assert content["origin"] == "none"
    assert content["salary"] is None
    assert content["description"]["blocks"] == []
