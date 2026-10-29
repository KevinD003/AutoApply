"""C17 (D70): a document version, or every version of it, is deleted with its file, and never
while a live approval or a running attempt needs it. An application that chose it asks again.
Synthetic documents and the generic receiver only."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.audit.models import AuditEvent
from app.modules.documents.models import Document
from app.modules.documents.storage import LocalStorage
from app.modules.preparation.models import ApplicationInput, PackageApproval
from tests.execution_harness import Receiver, prepared_application, queue

PDF = b"%PDF-1.4\n% synthetic document\n"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def upload(api, name="resume.pdf", kind="resume", lineage=None) -> dict:
    data = {"kind": kind} | ({"lineage_id": lineage} if lineage else {})
    r = api.post("/documents", files={"file": (name, PDF, "application/pdf")}, data=data)
    assert r.status_code == 201, r.text
    return r.json()


def file_of(doc_id: str):
    with SessionLocal() as db:
        key = db.get(Document, uuid.UUID(doc_id)).storage_key
    return LocalStorage(get_settings().storage_dir)._path(key)


def delete(api, doc_id, scope=None):
    return api.delete(f"/documents/{doc_id}" + (f"?scope={scope}" if scope else ""))


def code_of(r) -> str:
    assert r.status_code == 409, r.text
    return r.json()["detail"].rsplit("(reason: ", 1)[1].rstrip(")")


def resume_of(api, app_id) -> str:
    docs = api.get(f"/applications/{app_id}/package").json()["package"]["content"]["documents"]
    return next(d["document_id"] for d in docs if d["field"] == "resume")


def test_deleting_a_version_removes_its_row_and_file_only(api):
    v1 = upload(api)
    v2 = upload(api, lineage=v1["lineage_id"])
    f1, f2 = file_of(v1["id"]), file_of(v2["id"])
    assert delete(api, v1["id"]).status_code == 204
    assert api.get(f"/documents/{v1['id']}/download").status_code == 404
    assert not f1.exists() and f2.exists()
    assert [d["version"] for d in api.get(f"/documents/{v2['id']}/versions").json()] == [2]
    with SessionLocal() as db:
        row = db.scalar(select(AuditEvent).where(AuditEvent.action == "document.delete"))
    assert row.meta == {"scope": "version", "versions": 1}


def test_deleting_a_document_removes_every_version(api):
    v1 = upload(api)
    v2 = upload(api, lineage=v1["lineage_id"])
    files = [file_of(v1["id"]), file_of(v2["id"])]
    assert delete(api, v2["id"], "lineage").status_code == 204
    assert api.get("/documents").json() == []
    assert all(not f.exists() for f in files)
    for d in (v1, v2):
        assert api.get(f"/documents/{d['id']}/download").status_code == 404


def test_another_users_document_is_404_and_untouched(api, other_api):
    mine = upload(api)
    for scope in (None, "lineage"):
        assert delete(other_api, mine["id"], scope).status_code == 404
    assert file_of(mine["id"]).exists()
    assert api.get(f"/documents/{mine['id']}/download").status_code == 200


def test_a_document_in_an_approved_package_is_not_deleted_until_revoked(api, receiver):
    app_id = prepared_application(api, receiver)  # approved, with the synthetic resume
    doc_id = resume_of(api, app_id)
    r = delete(api, doc_id, "lineage")
    assert code_of(r) == "document_in_approval" and file_of(doc_id).exists()
    assert api.post(f"/applications/{app_id}/package/revoke").status_code == 200
    assert delete(api, doc_id, "lineage").status_code == 204
    view = api.get(f"/applications/{app_id}/package").json()
    assert view["package"]["content"]["documents"] == []
    assert any(a["key"] == "resume" and a["status"] != "resolved"
               for a in view["package"]["content"]["answers"])  # fmt: skip


def test_a_document_a_running_attempt_needs_is_not_deleted(api, receiver):
    """Refused for the attempt itself, even once its approval is no longer live."""
    app_id = prepared_application(api, receiver)
    doc_id = resume_of(api, app_id)
    queue(api, app_id)  # pending: no worker in this test
    with SessionLocal() as db:
        for a in db.scalars(select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(app_id))):  # fmt: skip
            a.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert code_of(delete(api, doc_id)) == "document_in_attempt"
    assert file_of(doc_id).exists()


def test_an_application_that_chose_a_deleted_version_asks_again(api, receiver):
    app_id = prepared_application(api, receiver, approve=False)
    letter = upload(api, "letter.pdf", "cover_letter")
    r = api.put(
        f"/applications/{app_id}/documents", json={"cover_letter_document_id": letter["id"]}
    )
    assert r.status_code == 200, r.text
    assert delete(api, letter["id"]).status_code == 204
    with SessionLocal() as db:
        left = db.scalars(select(ApplicationInput).where(
            ApplicationInput.application_id == uuid.UUID(app_id),
            ApplicationInput.kind == "document")).all()  # fmt: skip
    assert all(i.value.get("document_id") != letter["id"] for i in left)
    docs = api.get(f"/applications/{app_id}/package").json()["package"]["content"]["documents"]
    assert letter["id"] not in {d["document_id"] for d in docs}


def test_a_past_package_version_keeps_only_what_it_recorded(api, receiver):
    """Versions are immutable: a past one keeps the id, version, size, type, digest and the name
    it showed; the file and the document row are gone."""
    app_id = prepared_application(api, receiver, approve=False)
    doc_id = resume_of(api, app_id)
    before = api.get(f"/applications/{app_id}/package").json()["package"]
    assert delete(api, doc_id, "lineage").status_code == 204
    api.get(f"/applications/{app_id}/package")  # a new version without it
    diff = api.get(f"/applications/{app_id}/package/diff",
                   params={"from_version": before["version"]}).json()  # fmt: skip
    assert [d["field"] for d in diff["documents"]] == ["resume"]
    assert diff["documents"][0]["after"] is None


def test_a_delete_waiting_for_an_approval_in_progress_sees_it(api, receiver):
    """Approving holds the application's lock; a deletion arriving meanwhile waits for it, then
    sees the approval and deletes nothing (a barrier on the real lock, not a sleep)."""
    from app.modules.preparation import package as pk
    from tests.test_lock_order import Side, lock_waiters, no_errors, wait_until

    app_id = prepared_application(api, receiver, approve=False)
    doc_id = resume_of(api, app_id)
    approving = SessionLocal()
    try:
        app = pk.lock_application(approving, uuid.UUID(app_id))
        pkg = pk.latest_package(approving, app.id)
        before = lock_waiters()
        side = Side("delete", lambda: delete(api, doc_id, "lineage"))
        wait_until(lambda: lock_waiters() > before, "the deletion waits for the application")
        approving.add(PackageApproval(package_id=pkg.id, application_id=app.id,
                                      user_id=app.user_id, content_hash=pkg.content_hash,
                                      expires_at=utcnow() + timedelta(hours=1)))  # fmt: skip
        approving.commit()
    finally:
        approving.close()
    side.join()
    no_errors(side)
    assert code_of(side.result) == "document_in_approval" and file_of(doc_id).exists()
