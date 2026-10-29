"""L1 (D72): text from an uploaded resume (PDF, DOCX or TXT) becomes proposed profile facts:
work history, education and credentials, each `proposed` until the user approves it, and never
used before. No LLM; only what the text states in a recognisable layout; never a legal-status
or sensitive fact, a date it does not state in full, or a completed degree. Synthetic files."""

import io
import uuid
import zipfile
from datetime import date

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.documents.extract import MAX_PAGES, ExtractError, extract_text
from app.modules.preparation import drafting
from app.modules.profiles.models import Approval, Provenance
from app.modules.profiles.resume_parse import propose

RESUME = """Sam Synthetic
Experience
Front Desk Lead at Synthetic Care Clinic, Jan 2020 – Present
• Handled patient intake for 3 doctors
Receptionist — Example Health (2017-2019)
- Answered phones
US citizen, no sponsorship needed
As a woman and veteran I bring discipline.
Education
Associate of Applied Science, Medical Assisting — Example Community College
Certifications
Phlebotomy Technician, issued by Synthetic Board, expires 2027-05-31
CPR | Example Heart Association
Skills
Scheduling, EHR
"""


def pdf(lines: list[str], pages: int = 1) -> bytes:
    """A minimal valid PDF, one text line per row, the same lines on every page."""

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(f"({esc(x)}) '" for x in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * i} 0 R" for i in range(pages))
            + f"] /Count {pages} >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]  # fmt: skip
    for i in range(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i}"
                    " 0 R /Resources << /Font << /F1 3 0 R >> >> >>")  # fmt: skip
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for n, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for o in offsets:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
              .encode())  # fmt: skip
    return out.getvalue()


def docx(lines: list[str]) -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{x}</w:t></w:r></w:p>" for x in lines)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body>'
                                        "</w:document>")  # fmt: skip
    return buf.getvalue()


PDF_T = "application/pdf"
DOCX_T = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# -- extraction ------------------------------------------------------------------------------


def test_text_is_read_from_pdf_docx_and_txt():
    lines = ["Experience", "Front Desk Lead at Synthetic Care Clinic"]
    for ctype, data in ((PDF_T, pdf(lines)), (DOCX_T, docx(lines)),
                        ("text/plain", "\n".join(lines).encode())):  # fmt: skip
        assert extract_text(ctype, data).splitlines() == lines, ctype


def test_only_the_first_pages_of_a_long_pdf_are_read():
    text = extract_text(PDF_T, pdf(["Page line"], pages=MAX_PAGES + 5))
    assert text.count("Page line") == MAX_PAGES


@pytest.mark.parametrize(
    "ctype,data,code",
    [
        (PDF_T, b"%PDF-1.4\nnot really a pdf", "unreadable"),
        (DOCX_T, b"PK\x03\x04 not a zip", "unreadable"),
        ("text/plain", b"   \n  ", "no_text"),
        ("image/png", b"\x89PNG", "unsupported"),
    ],
)
def test_unreadable_documents_say_why(ctype, data, code):
    with pytest.raises(ExtractError) as e:
        extract_text(ctype, data)
    assert e.value.code == code


def test_a_docx_whose_document_part_is_too_large_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<a>" + " " * 6_000_000 + "</a>")
    with pytest.raises(ExtractError) as e:
        extract_text(DOCX_T, buf.getvalue())
    assert e.value.code == "too_large"


# -- what is proposed ------------------------------------------------------------------------


def test_only_stated_facts_are_proposed():
    p = propose(RESUME)
    assert [(e["title"], e["employer"]) for e in p.employment] == [
        ("Front Desk Lead", "Synthetic Care Clinic"),
        ("Receptionist", "Example Health"),
    ]
    assert p.employment[0]["description"].splitlines() == [
        "Dates as written: Jan 2020 – Present",
        "Handled patient intake for 3 doctors",
    ]
    assert p.education == [{"degree": "Associate of Applied Science, Medical Assisting",
                            "institution": "Example Community College"}]  # fmt: skip
    assert p.credential == [
        {"name": "Phlebotomy Technician", "issuer": "Synthetic Board",
         "expires_on": date(2027, 5, 31)},
        {"name": "CPR", "issuer": "Example Heart Association", "expires_on": None},
    ]  # fmt: skip
    assert p.skipped_sensitive == 2  # citizenship and sponsorship; gender and veteran status


def test_nothing_is_inferred():
    """No dates on work or education records, no completion, no expiry unless written in full,
    nothing outside a known section."""
    p = propose("Sam Synthetic\nNurse at Nowhere Hospital\nCertifications\nBLS, expires 05/2027\n"
                "Education\nExample University\n")  # fmt: skip
    assert p.employment == []  # above any section heading
    assert p.credential == [{"name": "BLS, expires 05/2027", "issuer": None, "expires_on": None}]
    assert p.education == [{"degree": None, "institution": "Example University"}]


# -- the endpoint ----------------------------------------------------------------------------


def upload(api, data, name, ctype, kind="resume") -> dict:
    r = api.post("/documents", files={"file": (name, data, ctype)}, data={"kind": kind})
    assert r.status_code == 201, r.text
    return r.json()


def test_proposed_facts_wait_for_approval_and_are_not_used_until_then(api):
    doc = upload(api, docx(RESUME.splitlines()), "resume.docx", DOCX_T)
    r = api.post(f"/documents/{doc['id']}/propose-facts")
    assert r.status_code == 200, r.text
    assert r.json() == {"proposed": {"employment": 2, "education": 1, "credential": 2},
                        "skipped": {"existing": 0, "sensitive": 2}}  # fmt: skip
    jobs = api.get("/profile/employment").json()
    assert {(j["approval_status"], j["provenance"]) for j in jobs} == {
        (Approval.proposed.value, Provenance.resume_parse.value)}  # fmt: skip
    assert all(j["start_date"] is None and j["end_date"] is None for j in jobs)
    assert api.get("/profile/education").json()[0]["completed"] == "unknown"
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        assert drafting.grounding_facts(db, me) == ()  # nothing proposed grounds a draft
    first = jobs[0]
    approved = api.post(f"/profile/employment/{first['id']}/approve").json()
    assert approved["approval_status"] == "approved"
    with SessionLocal() as db:
        assert [f.id for f in drafting.grounding_facts(db, me)] == [f"employment:{first['id']}"]
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "document.facts_proposed"))
    assert audit.meta == {"employment": 2, "education": 1, "credential": 2}


def test_proposing_again_adds_nothing_already_there(api):
    doc = upload(api, RESUME.encode(), "resume.txt", "text/plain")
    api.post(f"/documents/{doc['id']}/propose-facts")
    again = api.post(f"/documents/{doc['id']}/propose-facts").json()
    assert again["proposed"] == {"employment": 0, "education": 0, "credential": 0}
    assert again["skipped"]["existing"] == 5
    assert len(api.get("/profile/employment").json()) == 2


def test_a_pdf_resume_proposes_too(api):
    doc = upload(api, pdf(["Experience", "Front Desk Lead at Synthetic Care Clinic"]),
                 "resume.pdf", PDF_T)  # fmt: skip
    r = api.post(f"/documents/{doc['id']}/propose-facts").json()
    assert r["proposed"]["employment"] == 1


def test_errors_and_other_users(api, other_api):
    letter = upload(api, b"Dear hiring manager", "letter.txt", "text/plain", kind="cover_letter")
    assert api.post(f"/documents/{letter['id']}/propose-facts").status_code == 400
    mine = upload(api, RESUME.encode(), "resume.txt", "text/plain")
    assert other_api.post(f"/documents/{mine['id']}/propose-facts").status_code == 404
    assert other_api.get("/profile/employment").json() == []
    blank = upload(api, b"%PDF-1.4\n% no text at all\n", "blank.pdf", PDF_T)
    r = api.post(f"/documents/{blank['id']}/propose-facts")
    assert r.status_code == 422 and r.json()["detail"].endswith(")")
