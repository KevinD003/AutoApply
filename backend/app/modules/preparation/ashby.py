"""Ashby-shaped postings (D87): which posting a job address names, where its form is, and how
its form is read.

A hosted Ashby posting is `https://jobs.ashbyhq.com/BOARD/POSTING-ID`, its form on the
`/application` tab (search-reported; docs/research/ashby.md section 4; `jobs/canonical.py`
identifies it). The local Ashby-style approximation serves the same shape under
`/ashby/BOARD/POSTING-ID` on a fixture origin (fixtures/ats_receiver/ashby_like.py). Only that
approximation is ever read or filled: a real Ashby posting is identified so that it can be
refused, never fetched.

Ashby's spam protection is documented only as a score with no widget (docs/research/ashby.md
section 3), so nothing can detect it on a real page. The approximation marks its own with
`data-ashby-spam-check`; `extract_schema` turns that into the same required bot-check field a
documented CAPTCHA gets, so it is a checkpoint at capture and changes the form if it appears
after approval. It is never solved."""

import re
from typing import NamedTuple
from urllib.parse import urlsplit

from app.modules.preparation.forms import (
    BOT_CHECK_KEY,
    FormSchema,
    _bot_check,
    extract_form_schema,
)

_REAL = re.compile(r"^/(?P<board>[^/]{1,100})/(?P<posting>[0-9a-f-]{36})(?:/application)?/?$")
_FIXTURE = re.compile(
    r"^/ashby/(?P<board>[a-z0-9-]{1,64})/(?P<posting>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"
    r"(?:/application)?/?$"
)
REAL_HOSTS = frozenset({"jobs.ashbyhq.com"})
SPAM_CHECK = re.compile(r"\bdata-ashby-spam-check\b", re.IGNORECASE)
SPAM_CHECK_SELECTOR = "[data-ashby-spam-check]"


class Posting(NamedTuple):
    board: str
    posting_id: str
    fixture: bool


def parse_posting(url: str | None, *, fixture_origin: bool) -> Posting | None:
    """The posting a job address names: a real hosted Ashby posting, or the local Ashby-style
    approximation on a fixture origin. None for anything else (never a guess). An embedded
    posting on an employer's site (`?ashby_jid=`) names no board, so it is None here."""
    try:
        p = urlsplit(url or "")
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or p.username or p.password:
        return None
    host = (p.hostname or "").lower()
    if host in REAL_HOSTS:
        m = _REAL.fullmatch(p.path)
        return Posting(m["board"], m["posting"].lower(), False) if m else None
    if fixture_origin:
        m = _FIXTURE.fullmatch(p.path)
        return Posting(m["board"], m["posting"], True) if m else None
    return None


def application_path(posting: Posting) -> str:
    """The form's path on the fixture origin (the approximation's layout)."""
    return f"/ashby/{posting.board}/{posting.posting_id}/application"


def form_url(url: str) -> str:
    """The form page for a posting address: its `/application` tab. Same scheme and host as the
    address, no query or fragment."""
    p = urlsplit(url)
    path = p.path.rstrip("/")
    if not path.endswith("/application"):
        path += "/application"
    return f"{p.scheme}://{p.netloc}{path}"


def extract_schema(html: str) -> FormSchema:
    """The generic extractor (documented CAPTCHAs included), plus the approximation's own spam
    check as the bot-check field."""
    schema = extract_form_schema(html, challenges=True)
    if SPAM_CHECK.search(html) and all(f.key != BOT_CHECK_KEY for f in schema.fields):
        schema.fields.append(_bot_check())
    return schema
