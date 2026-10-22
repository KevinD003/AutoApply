"""No API path carries a posting's question key or any other external text. Path parameters are
internal ids (UUIDs) or NoEfforts' own names, so a proxy in front of the app can log a path
without logging anything a posting wrote. Answers, consents, cleared answers and drafts take the
question key in the request body. Synthetic data and local fixtures only."""

import pytest

from app.main import app
from tests.execution_harness import Receiver, synthetic_candidate
from tests.test_greenhouse_dom import v2_job

# The only path parameter that is not a UUID: NoEfforts' own fixture-form and provider names.
OWN_NAMES = {"name"}
KEY = "question_8101"  # a key of the synthetic Greenhouse-style posting


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def path_params():
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            for p in op.get("parameters", []):
                if p["in"] == "path":
                    yield method, path, p


def application(api) -> str:
    synthetic_candidate(api)
    job_id = v2_job(api)
    assert api.post(f"/jobs/{job_id}/form/greenhouse").status_code == 201
    return api.post("/applications", json={"job_id": job_id}).json()["id"]


def answer(view: dict, key: str) -> dict:
    return next(a for a in view["package"]["content"]["answers"] if a["key"] == key)


def test_every_path_parameter_is_an_internal_id_or_one_of_our_own_names():
    seen = set()
    for method, path, p in path_params():
        seen.add(p["name"])
        if p["name"] not in OWN_NAMES:
            assert p["schema"].get("format") == "uuid", (method, path, p["name"])
    assert {"app_id", "job_id", "draft_id"} <= seen  # the scan read the routes at all


def test_the_key_in_path_routes_are_gone(api, receiver):
    app_id = application(api)
    old = [
        ("put", f"/applications/{app_id}/answers/{KEY}", {"value": {"label": "Yes"}}),
        ("delete", f"/applications/{app_id}/answers/{KEY}", None),
        ("put", f"/applications/{app_id}/consents/{KEY}", {"choice": "agree"}),
        ("post", f"/applications/{app_id}/answers/{KEY}/draft", None),
    ]
    for method, path, body in old:
        r = getattr(api, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 404, (method, path)  # the application exists: no such route


def test_answers_consents_clearing_and_drafts_take_the_key_in_the_body(api, other_api, receiver):
    app_id = application(api)
    view = api.put(f"/applications/{app_id}/answers",
                   json={"key": "preferred_name", "value": {"text": "Sammy"}}).json()  # fmt: skip
    assert answer(view, "preferred_name")["value"] == {"text": "Sammy"}
    view = api.post(f"/applications/{app_id}/answers/clear", json={"key": "preferred_name"}).json()
    assert answer(view, "preferred_name")["status"] == "needs_user"  # back to unanswered
    r = api.put(f"/applications/{app_id}/consents", json={"key": KEY, "choice": "agree"})
    assert r.status_code == 400 and KEY not in r.text  # this question takes no consent choice
    r = api.post(f"/applications/{app_id}/drafts", json={"key": KEY})
    assert r.status_code == 400 and KEY not in r.text  # only long-form questions are drafted
    unknown = api.put(f"/applications/{app_id}/answers",
                      json={"key": "question_0000", "value": {"text": "x"}})  # fmt: skip
    assert unknown.status_code == 404 and "question_0000" not in unknown.text
    for bad in ("../question_8101", "question 8101", ""):
        r = api.put(f"/applications/{app_id}/answers", json={"key": bad, "value": {"text": "x"}})
        assert r.status_code == 422, bad  # never reaches the handler
    for method, path, body in [
        ("put", "answers", {"key": "preferred_name", "value": {"text": "Sammy"}}),
        ("post", "answers/clear", {"key": "preferred_name"}),
        ("put", "consents", {"key": KEY, "choice": "agree"}),
        ("post", "drafts", {"key": KEY}),
    ]:
        r = getattr(other_api, method)(f"/applications/{app_id}/{path}", json=body)
        assert r.status_code == 404, path  # another user's application is not found
