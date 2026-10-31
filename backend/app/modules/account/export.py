"""Full data export (priority B, D77): everything NoEfforts holds about one account, as one ZIP.

`noefforts-export.json` holds every row of every table that names the account, column by column
from EXPORTED; `documents/` holds each document's file; `README.txt` says what is left out and
why. Only listed columns are read, so a column added later is not exported until it is listed
here (tests/test_account.py fails until it is listed or excluded with a reason).

Left out: login and session secrets, keyed references and digests (HMACs under the server's
key: harmless to you, but internal security material), worker lease and fencing internals, a
verification code, where files are stored on the server, and two internal tables. Every query is
scoped to the account; nothing of another account can be read."""

import io
import json
import re
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from app.core.db import Base, utcnow
from app.modules.documents.storage import Storage

FORMAT_VERSION = 1
WORKER = "worker lease and fencing internals"
KEYED = "a keyed reference (an HMAC under the server's key): internal security material"

# Tables left out entirely, with why.
EXCLUDED_TABLES = {
    "user_sessions": "session secrets (token digests and CSRF tokens)",
    "outbox_messages": "an internal delivery queue (attempt ids and dispatch counters only)",
    "discovery_backoffs": "a timer that spaces out requests to a source; nothing about you",
}

# Columns left out of exported tables, with why.
EXCLUDED_COLUMNS = {
    "users": {"password_hash": "your password's hash: a login secret"},
    "applications": {"lock_version": "an internal concurrency counter"},
    "documents": {"storage_key": "where the server keeps the file; the file is in documents/"},
    "execution_attempts": {
        "generation": WORKER,
        "lease_owner": WORKER,
        "lease_expires_at": WORKER,
        "heartbeat_at": WORKER,
        "path_ref": KEYED,
    },
    "api_tokens": {"secret_hash": "an API token's hash: a login secret"},
    "email_settings": {"code_digest": KEYED + " (of a pending verification code)"},
    "email_deliveries": {
        "recipient_ref": KEYED,
        "generation": WORKER,
        "claimed_by": WORKER,
        "lease_until": WORKER,
    },
    "attempt_events": {"generation": WORKER},
    "checkpoints": {"code": "a verification code: a secret, erased once used"},
    "rehearsal_records": {"path_ref": KEYED},
}

# Inside JSON values: keys holding keyed digests, and strings that are keyed references
# (audit/service.py: `ref:v2:` + 32 hex, or the legacy `ref:` + 12 hex), are left out.
KEYED_JSON_KEYS = {"value_digest": KEYED, "consent_digests": KEYED}
_KEYED_REF = re.compile(r"^ref:(v2:[0-9a-f]{32}|[0-9a-f]{12})$")

# How each table is scoped to the account: by its own user_id, or through its parent's.
PARENT = {
    "application_events": ("application_id", "applications"),
    "attempt_events": ("attempt_id", "execution_attempts"),
}

EXPORTED: dict[str, tuple[str, ...]] = {
    "answer_bank": (
        "id",
        "user_id",
        "question_key",
        "question_text",
        "help_text",
        "answer_shape",
        "value",
        "options_snapshot",
        "sensitive",
        "source_application_id",
        "provenance",
        "approval_status",
        "version",
        "updated_at",
    ),
    "answer_drafts": (
        "id",
        "application_id",
        "user_id",
        "field_key",
        "input_hash",
        "provider",
        "model",
        "text",
        "evidence",
        "grounding_hash",
        "status",
        "cost_usd",
        "created_at",
    ),
    "api_tokens": (
        "id",
        "user_id",
        "public_id",
        "label",
        "scopes",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
    ),
    "api_authorizations": (
        "id",
        "user_id",
        "provider",
        "origin",
        "scope",
        "granted_at",
        "revoked_at",
    ),
    "application_events": (
        "id",
        "application_id",
        "kind",
        "from_state",
        "to_state",
        "actor",
        "reason",
        "from_outcome",
        "to_outcome",
        "source",
        "occurred_on",
        "evidence_note",
        "created_at",
    ),
    "application_inputs": (
        "id",
        "application_id",
        "user_id",
        "kind",
        "field_key",
        "value",
        "provenance",
        "meta",
        "updated_at",
    ),
    "application_packages": (
        "id",
        "application_id",
        "user_id",
        "version",
        "content",
        "content_hash",
        "change_summary",
        "created_at",
    ),
    "applications": (
        "id",
        "user_id",
        "job_id",
        "state",
        "state_changed_at",
        "outcome",
        "notes",
        "created_at",
        "updated_at",
    ),
    "attempt_events": ("id", "attempt_id", "kind", "detail", "created_at"),
    "audit_events": ("id", "user_id", "action", "entity_type", "entity_id", "meta", "created_at"),
    "candidate_profiles": (
        "id",
        "user_id",
        "full_name",
        "given_name",
        "family_name",
        "preferred_name",
        "contact_email",
        "phone",
        "residence_country",
        "residence_region",
        "residence_city",
        "links",
        "skills",
        "summary",
        "provenance",
        "approval_status",
        "version",
        "updated_at",
    ),
    "checkpoints": (
        "id",
        "attempt_id",
        "application_id",
        "user_id",
        "kind",
        "status",
        "round",
        "wrong_attempts",
        "max_attempts",
        "message",
        "expires_at",
        "created_at",
    ),
    "credentials": (
        "id",
        "user_id",
        "name",
        "issuer",
        "issued_on",
        "expires_on",
        "provenance",
        "approval_status",
        "version",
        "updated_at",
    ),
    "board_sources": (
        "id",
        "user_id",
        "provider",
        "region",
        "board",
        "employer",
        "paused",
        "created_at",
        "updated_at",
        "last_attempt_at",
        "last_success_at",
        "last_status",
        "last_error_code",
        "last_count",
        "failures",
        "next_allowed_at",
        "daily_check",
        "baseline_at",
    ),
    "discovered_jobs": (
        "id",
        "user_id",
        "board_source_id",
        "provider",
        "source_job_id",
        "fingerprint",
        "normalized",
        "source_facts",
        "status",
        "job_id",
        "stale",
        "stale_reason",
        "stale_since",
        "first_seen_at",
        "last_seen_at",
        "imported_at",
        "link_basis",
        "filter_result",
        "changed_fields",
        "changed_at",
        "raw_ref",
    ),
    "discovery_run_approvals": (
        "id",
        "user_id",
        "provider",
        "query",
        "max_pages",
        "not_before",
        "not_after",
        "retention",
        "created_at",
        "consumed_at",
    ),
    "discovery_watches": (
        "id",
        "user_id",
        "provider",
        "query",
        "interval_seconds",
        "not_before",
        "not_after",
        "retention",
        "created_at",
        "revoked_at",
        "paused_reason",
        "next_check_at",
        "last_checked_at",
        "last_outcome",
        "failures",
        "found_total",
        "budget_day",
        "requests_on_day",
    ),
    "documents": (
        "id",
        "user_id",
        "lineage_id",
        "version",
        "kind",
        "label",
        "original_filename",
        "content_type",
        "size_bytes",
        "sha256",
        "origin",
        "base_document_id",
        "grounding_hash",
        "accepted_at",
        "made_for_application_id",
        "grounded_on",
        "created_at",
    ),
    "drafting_consents": (
        "id",
        "user_id",
        "provider",
        "consent_version",
        "given_at",
        "withdrawn_at",
    ),
    "drafting_usage": (
        "id",
        "user_id",
        "day",
        "provider",
        "model",
        "status",
        "outcome",
        "reserved_usd",
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "created_at",
        "settled_at",
    ),
    "education_records": (
        "id",
        "user_id",
        "institution",
        "degree",
        "field_of_study",
        "start_date",
        "end_date",
        "completed",
        "provenance",
        "approval_status",
        "version",
        "updated_at",
    ),
    "employment_records": (
        "id",
        "user_id",
        "employer",
        "title",
        "location",
        "start_date",
        "end_date",
        "is_current",
        "description",
        "provenance",
        "approval_status",
        "version",
        "updated_at",
    ),
    "email_deliveries": (
        "id",
        "user_id",
        "kind",
        "dedupe_key",
        "status",
        "attempts",
        "next_attempt_at",
        "item_keys",
        "item_count",
        "outcome_code",
        "created_at",
        "sent_at",
        "updated_at",
    ),
    "email_settings": (
        "id",
        "user_id",
        "address",
        "verified_at",
        "code_expires_at",
        "code_attempts",
        "enabled",
        "attention",
        "follow_ups",
        "digest_hour_utc",
        "updated_at",
    ),
    "execution_attempts": (
        "id",
        "application_id",
        "user_id",
        "package_id",
        "package_hash",
        "approval_id",
        "adapter",
        "state",
        "retry_count",
        "cancel_requested",
        "destination_class",
        "rehearsal_prerequisite",
        "disclosure_started_at",
        "send_started_at",
        "finished_at",
        "outcome_detail",
        "created_at",
    ),
    "execution_evidence": (
        "id",
        "attempt_id",
        "application_id",
        "user_id",
        "kind",
        "strength",
        "data",
        "created_at",
        "retain_until",
    ),
    "fact_versions": (
        "id",
        "user_id",
        "entity_type",
        "entity_id",
        "version",
        "snapshot",
        "created_at",
    ),
    "follow_ups": (
        "id",
        "user_id",
        "application_id",
        "followed_up_on",
        "remind_on",
        "stopped",
        "updated_at",
    ),
    "import_batches": (
        "id",
        "user_id",
        "filename",
        "file_format",
        "file_sha256",
        "total_rows",
        "created_count",
        "duplicate_count",
        "error_count",
        "rows",
        "created_at",
    ),
    "job_forms": (
        "id",
        "user_id",
        "job_id",
        "version",
        "source",
        "source_ref",
        "extraction_version",
        "fingerprint",
        "schema",
        "captured_at",
    ),
    "job_preferences": (
        "id",
        "user_id",
        "titles",
        "fields",
        "industries",
        "seniority",
        "employment_types",
        "work_modes",
        "excluded_employers",
        "target_locations",
        "willing_to_relocate",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "updated_at",
    ),
    "jobs": (
        "id",
        "user_id",
        "dedupe_key",
        "employer",
        "employer_key",
        "title",
        "location",
        "url",
        "canonical_url",
        "ats_provider",
        "requisition_id",
        "description",
        "source",
        "status",
        "exclusion_reason",
        "notes",
        "posted_on",
        "first_seen_at",
        "last_seen_at",
        "seen_count",
        "open_confirmed_at",
        "distinct_confirmed_at",
        "created_at",
        "updated_at",
    ),
    "notification_reads": ("id", "user_id", "item_key", "read_at"),
    "package_approvals": (
        "id",
        "package_id",
        "application_id",
        "user_id",
        "content_hash",
        "adapter",
        "adapter_version",
        "scope",
        "approved_at",
        "expires_at",
        "invalidated_at",
        "invalidation_reason",
        "prerequisite_attempt_id",
    ),
    "rehearsal_records": (
        "id",
        "user_id",
        "application_id",
        "attempt_id",
        "approval_id",
        "destination_class",
        "route",
        "adapter",
        "adapter_version",
        "uploads_expected",
        "uploads_acknowledged",
        "readback_mismatched",
        "recheck_matched",
        "egress_proxy_denied",
        "unresolved",
        "recorded_at",
        "revoked_at",
        "revoked_reason",
    ),
    "users": ("id", "email", "created_at", "updated_at"),
    "work_authorizations": (
        "id",
        "user_id",
        "country_code",
        "authorized",
        "sponsorship_needed_now",
        "sponsorship_needed_future",
        "notes",
        "provenance",
        "approval_status",
        "version",
        "updated_at",
    ),
}

EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}


def _scrub(value):
    """A JSON value without keyed digests or keyed references (KEYED_JSON_KEYS, _KEYED_REF)."""
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k not in KEYED_JSON_KEYS}
    if isinstance(value, list):
        return [_scrub(v) for v in value if not (isinstance(v, str) and _KEYED_REF.match(v))]
    if isinstance(value, str) and _KEYED_REF.match(value):
        return "[keyed reference left out]"
    return value


def _plain(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value") and not isinstance(value, dict | list | str):  # enums
        return value.value
    return _scrub(value)


def _rows(db: Session, table: Table, user_id: uuid.UUID) -> list[dict]:
    cols = [table.c[name] for name in EXPORTED[table.name]]
    q = select(*cols)
    if table.name == "users":
        q = q.where(table.c.id == user_id)
    elif table.name in PARENT:
        fk, parent_name = PARENT[table.name]
        parent = Base.metadata.tables[parent_name]
        q = q.where(table.c[fk].in_(select(parent.c.id).where(parent.c.user_id == user_id)))
    else:
        q = q.where(table.c.user_id == user_id)
    if "created_at" in table.c:
        q = q.order_by(table.c.created_at, table.c.id)
    elif "id" in table.c:
        q = q.order_by(table.c.id)
    return [{k: _plain(v) for k, v in row._mapping.items()} for row in db.execute(q)]


def _readme(counts: dict[str, int], files: int, missing: int) -> str:
    lines = [
        "NoEfforts data export",
        "",
        "noefforts-export.json: every record NoEfforts holds about your account, by table.",
        f"documents/: {files} document file(s), named by their id in the 'documents' table.",
    ]
    if missing:
        lines.append(f"{missing} document file(s) could not be read on the server and are missing.")
    lines += ["", "Records per table:"]
    lines += [f"  {name}: {n}" for name, n in sorted(counts.items())]
    lines += ["", "Left out, and why:"]
    lines += [f"  table {t}: {why}" for t, why in sorted(EXCLUDED_TABLES.items())]
    for t, cols in sorted(EXCLUDED_COLUMNS.items()):
        lines += [f"  {t}.{c}: {why}" for c, why in sorted(cols.items())]
    lines += [f"  inside JSON values, '{k}': {why}" for k, why in sorted(KEYED_JSON_KEYS.items())]
    lines.append("  inside JSON values, keyed references (ref:...): " + KEYED)
    return "\n".join(lines) + "\n"


def build(db: Session, user_id: uuid.UUID, storage: Storage) -> tuple[bytes, dict]:
    """The ZIP's bytes and a summary (counts only) for the audit event."""
    tables = {name: _rows(db, Base.metadata.tables[name], user_id) for name in sorted(EXPORTED)}
    d = Base.metadata.tables["documents"]
    keys = {
        str(i): k
        for i, k in db.execute(select(d.c.id, d.c.storage_key).where(d.c.user_id == user_id))
    }
    buf = io.BytesIO()
    files = missing = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for doc in tables["documents"]:
            # Named by id: the original filename is in the JSON, never used as a path.
            name = f"documents/{doc['id']}{EXTENSIONS.get(doc['content_type'], '.bin')}"
            try:
                z.writestr(name, storage.get(keys[doc["id"]]))
            except (OSError, ValueError):
                doc["file"], missing = None, missing + 1
                continue
            doc["file"], files = name, files + 1
        counts = {name: len(rows) for name, rows in tables.items()}
        export = {
            "format": "noefforts-export",
            "format_version": FORMAT_VERSION,
            "exported_at": utcnow().isoformat(),
            "tables": tables,
            "left_out": {
                "tables": EXCLUDED_TABLES,
                "columns": EXCLUDED_COLUMNS,
                "json_keys": KEYED_JSON_KEYS,
            },
        }
        z.writestr("noefforts-export.json", json.dumps(export, indent=1, ensure_ascii=False))
        z.writestr("README.txt", _readme(counts, files, missing))
    return buf.getvalue(), {"tables": len(tables), "rows": sum(counts.values()), "files": files}
