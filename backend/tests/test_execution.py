"""Phase C execution against the synthetic receiver. Receiver ledger counts are the oracle."""

import pytest

from app.modules.execution import runner
from tests.execution_harness import Receiver, attempt, prepared_application, queue


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset_receiver(receiver):
    receiver.reset()


def test_happy_path_submits_once_with_receipt(api, receiver):
    app_id = prepared_application(api, receiver)
    aid = queue(api, app_id)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    led = receiver.ledger()
    assert led["accepted"] == 1
    fields = led["acceptances"][0]["fields"]
    # The receiver saw exactly the approved values.
    assert fields["first_name"] == "Sam" and fields["country"] == "US"
    assert fields["work_auth_us"] == "1" and fields["sponsorship_us"] == "no"
    assert fields["hear_about"] == "referral" and fields["privacy_ack"] == "on"
    assert "gender" not in fields or fields["gender"] == ""
    assert [d["kind"] for d in led["disclosures"]] == ["upload"]
    a = api.get(f"/applications/{app_id}").json()
    assert a["state"] == "submitted_confirmed"
    att = api.get(f"/applications/{app_id}/attempts").json()[0]
    receipt = next(e for e in att["evidence"] if e["kind"] == "receipt")
    assert receipt["strength"] == "employer_receipt"
    assert receipt["data"]["receipt_id"] == led["acceptances"][0]["receipt"]
    assert attempt(aid).state == "confirmed"
