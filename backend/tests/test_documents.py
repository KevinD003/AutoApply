PDF = b"%PDF-1.4\n% synthetic test resume\n"


def test_upload_version_download(api):
    r = api.post(
        "/documents",
        files={"file": ("../../etc/My Resume.pdf", PDF, "application/pdf")},
        data={"kind": "resume"},
    )
    assert r.status_code == 201, r.text
    d1 = r.json()
    assert d1["original_filename"] == "My Resume.pdf" or ".." not in d1["original_filename"]
    assert d1["version"] == 1
    r = api.post(
        "/documents",
        files={"file": ("resume-v2.pdf", PDF + b"v2", "application/pdf")},
        data={"lineage_id": d1["lineage_id"]},
    )
    d2 = r.json()
    assert d2["version"] == 2 and d2["lineage_id"] == d1["lineage_id"]
    assert len(api.get("/documents").json()) == 1
    assert [v["version"] for v in api.get(f"/documents/{d1['id']}/versions").json()] == [1, 2]
    # Old version remains downloadable and unchanged.
    dl = api.get(f"/documents/{d1['id']}/download")
    assert dl.content == PDF
    assert dl.headers["cache-control"] == "private, no-store"


def test_upload_rejects_mismatched_or_disallowed(api):
    assert (
        api.post(
            "/documents", files={"file": ("cv.pdf", b"MZ\x90\x00", "application/pdf")}
        ).status_code
        == 400
    )
    assert (
        api.post(
            "/documents", files={"file": ("run.exe", b"MZ", "application/octet-stream")}
        ).status_code
        == 400
    )
    assert (
        api.post("/documents", files={"file": ("empty.txt", b"", "text/plain")}).status_code == 400
    )


def test_cross_tenant_document_access_denied(api, other_api):
    d = api.post("/documents", files={"file": ("cv.pdf", PDF, "application/pdf")}).json()
    assert other_api.get(f"/documents/{d['id']}/download").status_code == 404
    assert other_api.get(f"/documents/{d['id']}/versions").status_code == 404
    r = other_api.post(
        "/documents",
        files={"file": ("cv.pdf", PDF, "application/pdf")},
        data={"lineage_id": d["lineage_id"]},
    )
    assert r.status_code == 404
