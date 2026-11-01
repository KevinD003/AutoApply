"""D111 §5: the milestone-B handoff for one application, shown in the app only.

One place that says, for the job you chose (privately, in your own account), what a
disclosure-only rehearsal through the Greenhouse pilot would do and what it still needs:

  * the destination, as you saved it;
  * the exact answers and documents of your current package, and which of them filling and
    uploading would put on the employer's page;
  * that a rehearsal stops before the final click, and what enforces it;
  * every prerequisite, each read from the system as it is now (never assumed), and the
    evidence a rehearsal leaves.

It reads; it never records, approves, queues or contacts anything. Nothing in it is a
permission: the owner's recorded permissions (app/core/authorizations.py) and your approval of
the exact package as a rehearsal are checked again by the gates themselves. The response is
for you only (your own application, 404 for anyone else); its contents are never logged or put
in audit metadata.
"""

from sqlalchemy.orm import Session

from app.core import authorizations
from app.core.config import get_settings
from app.modules.applications.models import Application
from app.modules.execution import live
from app.modules.identity.models import User
from app.modules.jobs.models import Job
from app.modules.preparation import package as pk
from app.modules.preparation import sending
from app.modules.preparation.models import ApprovalScope
from app.modules.providers.routing import form_checkpoint

PERMISSIONS = (
    ("read", "1. Read the public job post"),
    ("open", "2. Open the application page in the isolated browser"),
    ("disclose", "3. Disclose: fill in and upload on the employer's page"),
)
SUBMIT = ("submit", "4. Submit")

EXPOSURE = (
    "Each value below is typed or chosen on the employer's real page. Its own scripts can read "
    "it, and may save or send it, before and without any submission.",
    "Each document below is sent to the employer when it is attached (the page uploads it at "
    "once); that cannot be undone by stopping.",
    "A location typed into the page's own search is sent to that search as it is typed.",
    "As for any visit, the employer and Greenhouse see ordinary connection details (address, "
    "browser, timing).",
)

STOP = (
    "A rehearsal is your approval of this exact package with the scope 'rehearsal (fill and "
    "check, never submit)'. The runner reads that scope and stops after the read-back and the "
    "re-check, before the step that would click submit; it never reaches that step.",
    "Before anything is entered, the page is re-checked against the form you approved; any "
    "difference, an unlisted control, a CAPTCHA or a changed submit address stops it.",
    "Submitting needs a separate approval to submit and the owner's separate permission 4, and "
    "is never part of a rehearsal.",
)

EVIDENCE = (
    "The attempt ends as 'rehearsed', or stops earlier with a fixed reason: before anything was "
    "entered ('failed_safe'), or after ('abandoned', with what was already disclosed).",
    "One disclosure record per value entered and per document attached, with the page's upload "
    "acknowledgement (shown, none or error).",
    "A read-back count (how many fields kept their values) and the re-check result.",
    "Refused network requests, counted by destination category (never addresses).",
    "No evidence of a final click, because none is made. There is no independent ledger on a "
    "real employer's side: these records are NoEfforts' own. You can confirm on the employer's "
    "side that no application arrived.",
)


def _item(code: str, label: str, met: bool, detail: str = "") -> dict:
    return {"code": code, "label": label, "met": met, "detail": detail}


def _server(user: User, url: str | None) -> list[dict]:
    s = get_settings()
    stand_in = s.env == "test"  # the pilot then reaches only its local stand-in
    owners = {e.strip().lower() for e in s.live_owner_emails}
    note = "test environment: the local stand-in only" if stand_in else ""
    return [
        _item(
            "pilot_switch",
            "The pilot is switched on (NOEFFORTS_LIVE_GREENHOUSE_ENABLED)",
            bool(s.live_greenhouse_enabled),
            "a switch, not a permission",
        ),  # fmt: skip
        _item(
            "production",
            "Production mode (NOEFFORTS_ENV=production)",
            s.env == "production" or stand_in,
            note or s.env,
        ),  # fmt: skip
        _item(
            "container",
            "The browser's container isolation (Chromium's own sandbox on)",
            s.browser_isolation == "container" or stand_in,
            note or s.browser_isolation,
        ),  # fmt: skip
        _item(
            "owner_account",
            "This account is the server owner's (NOEFFORTS_LIVE_OWNER_EMAILS)",
            (user.email or "").strip().lower() in owners,
        ),  # fmt: skip
        _item(
            "greenhouse_posting",
            "The job is a Greenhouse-hosted job post the pilot accepts",
            live.posting(url) is not None,
        ),  # fmt: skip
    ]


def _permissions() -> list[dict]:
    out = []
    for action, label in PERMISSIONS:
        ok = authorizations.covers(authorizations.GREENHOUSE_PILOT, action)
        why = "recorded" if ok else "not recorded (app/core/authorizations.py)"
        out.append(_item(f"permission_{action}", label, ok, why))
    return out


def handoff(db: Session, user: User, app: Application) -> dict:
    job = db.get(Job, app.job_id)
    url = (job.url or job.canonical_url) if job else None
    pkg = pk.latest_package(db, app.id)
    content = pkg.content if pkg else None
    appr = pk.active_approval(db, pkg)
    dest = (content or {}).get("destination") or {}
    form = pk.latest_form(db, app.job_id)

    will, withheld = [], []
    for a in (content or {}).get("answers", []):
        row = {"key": a["key"], "label": a["label"], "source": a["source"]}
        if sending.sendable(a):
            how = ("uploaded" if a["type"] == "file"
                   else "searched" if a.get("widget") == "location_search"
                   else "chosen" if a["options"] else "typed")  # fmt: skip
            will.append(row | {"how": how, "display": a["display"]})
        else:
            withheld.append(row | {"status": a["status"], "why": a["explanation"]})
    documents = [{"field": d["field"], "display": d["display"], "version": d["version"],
                  "size_bytes": d["size_bytes"], "content_type": d["content_type"]}
                 for d in (content or {}).get("documents", [])]  # fmt: skip

    captured = form is not None and form.source == live.FORM_SOURCE
    unresolved = list((content or {}).get("unresolved") or [])
    blocking = form_checkpoint(form.schema) if form is not None else []
    scope = None if appr is None else str(getattr(appr.scope, "value", appr.scope))
    rehearsal_ok = scope == ApprovalScope.disclose_only.value
    application = [
        _item(
            "captured_through_pilot",
            "The form was read through the pilot",
            captured,
            "" if form is None else f"form version {form.version}",
        ),  # fmt: skip
        _item(
            "no_checkpoints",
            "No question is left open or blocking",
            pkg is not None and not unresolved and not blocking,
            f"{len(unresolved)} open, {len(blocking)} blocking",
        ),  # fmt: skip
        _item(
            "rehearsal_approval",
            "You approved this exact package as a rehearsal",
            rehearsal_ok,
            "none" if scope is None else f"approved as {scope}",
        ),  # fmt: skip
    ]
    prerequisites = _server(user, url) + _permissions() + application
    submit_ok = authorizations.covers(authorizations.GREENHOUSE_PILOT, SUBMIT[0])
    return {
        "application_id": str(app.id),
        "milestone": "B: one disclosure-only rehearsal on a real Greenhouse page",
        "destination": {
            "url": url,
            "origin": dest.get("origin"),
            "employer": job.employer if job else None,
            "title": job.title if job else None,
            "form_source": form.source if form else None,
        },
        "package": None
        if pkg is None
        else {
            "version": pkg.version,
            "content_hash": pkg.content_hash,
            "approved": appr is not None,
            "approval_scope": scope,
            "approved_at": None if appr is None else appr.approved_at,
            "expires_at": None if appr is None else appr.expires_at,
        },
        "will_disclose": will,
        "documents": documents,
        "not_disclosed": withheld,
        "exposure": list(EXPOSURE),
        "stop_before_submit": list(STOP),
        "prerequisites": prerequisites,
        "outstanding": [p["code"] for p in prerequisites if not p["met"]],
        "ready": all(p["met"] for p in prerequisites),
        # Permission 4 stays separate: never part of a rehearsal, shown so it is not assumed.
        "submit_permission": _item(
            f"permission_{SUBMIT[0]}", SUBMIT[1], submit_ok, "not needed for a rehearsal"
        ),  # fmt: skip
        "expected_evidence": list(EVIDENCE),
        "not_a_permission": "This page grants nothing: every gate checks again when an attempt "
        "runs.",
    }
