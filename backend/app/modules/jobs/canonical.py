"""Canonical identities for jobs, so the same posting is recognised across links and imports."""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = re.compile(
    r"^(utm_.*|gh_src|source|src|ref|referrer|lever-source.*|gclid|fbclid)$", re.I
)
_SPACE = re.compile(r"\s+")
_LEGAL_SUFFIX = re.compile(
    r"[,.]?\s+(inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|limited|corp|corp\.|corporation|co|co\.|gmbh|plc|"
    r"s\.a\.|pvt\.? ltd\.?|pty ltd)$",
    re.I,
)


@dataclass(frozen=True)
class AtsIdentity:
    provider: str
    company: str | None
    requisition_id: str | None


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)]
    # Greenhouse embeds keep the job id in gh_jid; keep it, drop pure tracking params.
    query = sorted((k, v) for k, v in query if not TRACKING_PARAMS.match(k))
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit(
        (
            "https" if parts.scheme in ("http", "https") else parts.scheme,
            host,
            path,
            urlencode(query),
            "",
        )
    )


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "greenhouse",
        re.compile(
            r"^(?:job-)?boards(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?(?P<company>[^/?]+)/jobs/(?P<req>\d+)"
        ),
    ),
    ("lever", re.compile(r"^jobs(?:\.eu)?\.lever\.co/(?P<company>[^/]+)/(?P<req>[0-9a-f-]{36})")),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com/(?P<company>[^/]+)/(?P<req>[0-9a-f-]{36})")),
    (
        "workable",
        re.compile(r"^apply\.workable\.com/(?P<company>[^/]+)/j/(?P<req>[0-9A-Z]+)", re.I),
    ),
    (
        "workday",
        re.compile(
            r"^(?P<company>[^.]+)\.wd\d+\.myworkdayjobs\.com/.*?_(?P<req>[A-Z]*-?\d[\w-]*)$", re.I
        ),
    ),
    ("smartrecruiters", re.compile(r"^jobs\.smartrecruiters\.com/(?P<company>[^/]+)/(?P<req>\d+)")),
]
# Every ATS identity detect_ats can return besides "unknown", and the vendor's product name for
# each (wording only; providers/admission.py checks every registered ATS has both).
ATS_NAMES = frozenset(name for name, _ in _PATTERNS)
ATS_DISPLAY = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby",
               "workable": "Workable", "workday": "Workday",
               "smartrecruiters": "SmartRecruiters"}  # fmt: skip


def detect_ats(canonical_url: str) -> AtsIdentity:
    parts = urlsplit(canonical_url)
    hostpath = f"{parts.hostname}{parts.path}"
    q = dict(parse_qsl(parts.query))
    if parts.hostname and "greenhouse.io" in parts.hostname and "gh_jid" in q:
        return AtsIdentity("greenhouse", q.get("for"), q["gh_jid"])
    # S3 (D59, R5.10): Greenhouse's embedded form, /embed/job_app?for=<board>&token=<job id>.
    # The pattern below reads host and path only, so the query was never matched.
    if (
        parts.hostname
        and re.match(r"^(?:job-)?boards(?:\.eu)?\.greenhouse\.io$", parts.hostname)
        and parts.path == "/embed/job_app"
        and re.fullmatch(r"\d+", q.get("token", ""))
    ):
        return AtsIdentity("greenhouse", (q.get("for") or "").lower() or None, q["token"])
    for provider, pat in _PATTERNS:
        m = pat.match(hostpath)
        if m:
            return AtsIdentity(provider, m.group("company").lower(), m.group("req"))
    if "gh_jid" in q:  # Greenhouse embedded on an employer's own careers site
        return AtsIdentity("greenhouse", None, q["gh_jid"])
    return AtsIdentity("unknown", None, None)


def normalize_text(s: str | None) -> str:
    return _SPACE.sub(" ", (s or "").strip()).lower()


def employer_key(name: str | None) -> str:
    n = normalize_text(name)
    prev = None
    while prev != n:
        prev = n
        n = _LEGAL_SUFFIX.sub("", n).strip()
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")


DEDUPE_KEY_MAX = 200  # jobs.dedupe_key is String(200)


def _bounded(key: str) -> str:
    """A key longer than its column becomes its kind and a digest of the whole key: still one
    stable key per identity (a longer one could never have been stored)."""
    if len(key) <= DEDUPE_KEY_MAX:
        return key
    return f"{key.split(':', 1)[0]}:h:{hashlib.sha256(key.encode()).hexdigest()[:48]}"


def url_key(canonical_url: str) -> str:
    """The identity of a URL no ATS pattern recognises (and the one a job stored before its ATS
    was recognised still carries)."""
    return "url:" + hashlib.sha256(canonical_url.encode()).hexdigest()[:32]


def dedupe_key(
    *,
    canonical_url: str | None,
    employer: str | None,
    title: str | None,
    location: str | None,
    requisition_id: str | None = None,
) -> str:
    """Stable identity: ATS requisition > canonical URL > employer+title+location fingerprint."""
    if canonical_url:
        ats = detect_ats(canonical_url)
        if ats.provider != "unknown" and ats.requisition_id:
            return _bounded(
                f"ats:{ats.provider}:{ats.company or employer_key(employer)}:{ats.requisition_id}"
            )
    ek = employer_key(employer)
    if requisition_id and ek:
        return _bounded(f"req:{ek}:{normalize_text(requisition_id)}")
    if canonical_url:
        return url_key(canonical_url)
    raw = "|".join([ek, normalize_text(title), normalize_text(location)])
    return "fp:" + hashlib.sha256(raw.encode()).hexdigest()[:32]
