"""Lever-shaped postings (D85): which posting a job address names, and where its form is.

A hosted Lever posting is `https://jobs.lever.co/SITE/POSTING-ID` (EU: `jobs.eu.lever.co`), its
form at `.../apply` (the Postings API README; docs/research/lever.md §3-4). The local Lever-style
approximation serves the same shape under `/lever/SITE/POSTING-ID` on a fixture origin
(fixtures/ats_receiver/lever_like.py). Only that local approximation is ever read or filled:
a real Lever posting is identified so that it can be refused, never fetched.

The form itself is read from the page by the generic extractor (forms.extract_form_schema):
Lever's public API does not list an employer's custom questions."""

import re
from typing import NamedTuple
from urllib.parse import urlsplit

_REAL = re.compile(r"^/(?P<site>[A-Za-z0-9_.-]{1,100})/(?P<posting>[0-9a-f-]{36})(?:/apply)?/?$")
_FIXTURE = re.compile(
    r"^/lever/(?P<site>[a-z0-9-]{1,64})/(?P<posting>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"
    r"(?:/apply)?/?$"
)
REAL_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})


class Posting(NamedTuple):
    site: str
    posting_id: str
    fixture: bool


def parse_posting(url: str | None, *, fixture_origin: bool) -> Posting | None:
    """The posting a job address names: a real hosted Lever posting, or the local Lever-style
    approximation on a fixture origin. None for anything else (never a guess)."""
    try:
        p = urlsplit(url or "")
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or p.username or p.password:
        return None
    host = (p.hostname or "").lower()
    if host in REAL_HOSTS:
        m = _REAL.fullmatch(p.path)
        return Posting(m["site"], m["posting"], False) if m else None
    if fixture_origin:
        m = _FIXTURE.fullmatch(p.path)
        return Posting(m["site"], m["posting"], True) if m else None
    return None


def apply_path(posting: Posting) -> str:
    """The form's path on the fixture origin (the approximation's layout)."""
    return f"/lever/{posting.site}/{posting.posting_id}/apply"


def form_url(url: str) -> str:
    """The form page for a posting address: the posting itself if it already names `/apply`,
    otherwise its `/apply` page. Same scheme and host as the address, no query or fragment."""
    p = urlsplit(url)
    path = p.path.rstrip("/")
    if not path.endswith("/apply"):
        path += "/apply"
    return f"{p.scheme}://{p.netloc}{path}"
