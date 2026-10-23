"""Nothing that could be real candidate data, a secret or a captured session is committed (C1).

Read from `git ls-files`: the tracked files, plus untracked files that are not ignored (what
`git add .` would commit), so a local run already sees what a commit would contain. Synthetic
documents in tests are built in code; none is a tracked file."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Documents, spreadsheets, environment files, keys, browser captures and databases.
FORBIDDEN = re.compile(
    r"\.(pdf|docx?|rtf|odt|pages|xlsx?|ods|csv|tsv|pem|key|p12|pfx|har|sqlite3?|db)$"
    r"|(^|/)\.env(\..+)?$"
    r"|(^|[/._-])trace\.zip$"
    r"|(^|/)(\.auth|captures|playwright-report|test-results)/"
    r"|(storage[-_]?state|cookies?)[^/]*\.json$|(^|/)auth[^/]*\.json$",
    re.IGNORECASE,
)
ALLOWED_FILES = {".env.example"}  # synthetic defaults only (tested by docker-smoke)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
# Reserved for documentation (RFC 2606, RFC 6761), and the repository owner's commit identity.
RESERVED = {"example.com", "example.org", "example.net"}
RESERVED_SUFFIXES = (".example", ".invalid", ".test", ".localhost", ".internal")
ALLOWED_ADDRESSES = {"74347164+kevind003@users.noreply.github.com"}


def committable() -> list[str]:
    def ls(*flags):
        out = subprocess.run(
            ["git", "ls-files", "-z", *flags], cwd=ROOT, capture_output=True, check=True
        ).stdout.decode()
        return [f for f in out.split("\0") if f]

    tracked = ls()
    assert len(tracked) > 100  # the checkout is the repository, not a fragment
    return sorted(set(tracked) | set(ls("--others", "--exclude-standard")))


def unreserved(text: str) -> set[str]:
    out = set()
    for m in EMAIL.finditer(text):
        address, domain = m.group(0).lower(), m.group(1).lower()
        if address in ALLOWED_ADDRESSES or domain in RESERVED:
            continue
        if not domain.endswith(RESERVED_SUFFIXES):
            out.add(domain)
    return out


def test_no_document_secret_or_session_file_is_committed():
    bad = [f for f in committable() if FORBIDDEN.search(f) and f not in ALLOWED_FILES]
    assert bad == []


def test_every_email_address_in_the_repository_uses_a_reserved_domain():
    bad = set()
    for f in committable():
        path = ROOT / f
        if not path.is_file():
            continue  # deleted in the working tree
        # Every file, whatever its encoding: a file that is not UTF-8 is not skipped.
        text = path.read_bytes().decode("utf-8", errors="replace")
        bad |= {(f, domain) for domain in unreserved(text)}
    assert sorted(bad) == []


def test_the_rules_catch_what_they_are_for():
    for name in ("resume.pdf", "x/Cover Letter.docx", "candidates.xlsx", "export.csv", ".env",
                 "backend/.env.local", "e2e/storage_state.json", "my-storageState.json",
                 "auth.json", "frontend/.auth/user.json", "trace.zip", "test-results/a/trace.zip",
                 "ledger.sqlite", "run.har", "captures/page.html"):  # fmt: skip
        assert FORBIDDEN.search(name), name
    for name in (".env.example", "docs/answer-policy.md", "backend/app/main.py",
                 "docs/author.md", "frontend/package.json"):  # fmt: skip
        assert not FORBIDDEN.search(name) or name in ALLOWED_FILES, name
    # Built at run time, so this file's own text holds no address that is not reserved.
    sample = "sam" + "@" + "realmail.co"
    assert unreserved(f"write to {sample} for details") == {"realmail.co"}
    other = "someone" + "@" + "users.noreply.github.com"
    assert unreserved(other) == {"users.noreply.github.com"}  # only the owner's is allowed
    assert unreserved("sam.synthetic@example.com, x@broker.internal") == set()
