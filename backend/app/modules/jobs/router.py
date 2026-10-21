import hashlib
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.core.urlsafety import UnsafeURL
from app.modules.audit.service import record
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.jobs import spreadsheet
from app.modules.jobs.models import ImportBatch, Job, JobSource, JobStatus
from app.modules.jobs.service import explain, upsert_job
from app.modules.profiles.models import JobPreferences

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobIn(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    employer: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=300)
    requisition_id: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)
    notes: str | None = Field(default=None, max_length=10_000)
    posted_on: date | None = None

    @model_validator(mode="after")
    def _need(self):
        if not self.url and not (self.title and self.employer):
            raise ValueError("Provide a job URL, or both a title and an employer")
        return self


class JobPatch(BaseModel):
    status: JobStatus | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    title: str | None = Field(default=None, max_length=300)
    employer: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    exclusion_reason: str | None = Field(default=None, max_length=500)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employer: str | None
    title: str | None
    location: str | None
    url: str | None
    canonical_url: str | None
    ats_provider: str
    requisition_id: str | None
    source: JobSource
    status: JobStatus
    exclusion_reason: str | None
    notes: str | None
    posted_on: date | None
    first_seen_at: datetime
    last_seen_at: datetime
    seen_count: int


class JobDetail(JobOut):
    description: str | None
    explanations: list[dict]
    # Discovery sources that list this job (source attribution only; never verified facts).
    discovered_from: list[dict] = []


class JobCreated(BaseModel):
    job: JobOut
    duplicate: bool


class JobPage(BaseModel):
    items: list[JobOut]
    total: int


def _owned(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise not_found("Job")
    return job


@router.post("", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobIn,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        job, created = upsert_job(
            db,
            user.id,
            source=JobSource.url if body.url else JobSource.manual,
            **body.model_dump(),
        )
    except UnsafeURL as e:
        raise bad_request(str(e)) from None
    record(db, user.id, "job.create" if created else "job.duplicate", "job", job.id)
    db.commit()
    if not created:
        response.status_code = status.HTTP_200_OK
    return JobCreated(job=job, duplicate=not created)


@router.get("", response_model=JobPage)
def list_jobs(
    status_: JobStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Job).where(Job.user_id == user.id)
    if status_:
        stmt = stmt.where(Job.status == status_)
    if q:
        like = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        stmt = stmt.where(
            or_(Job.title.ilike(like), Job.employer.ilike(like), Job.location.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Job.last_seen_at.desc()).limit(limit).offset(offset)).all()
    return JobPage(items=items, total=total or 0)


@router.get("/export")
def export_jobs(
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    jobs = db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.first_seen_at)).all()
    rows = [
        {
            "row_id": str(j.id),
            "job_url": j.url,
            "employer": j.employer,
            "title": j.title,
            "location": j.location,
            "status": j.status.value,
            "posted_on": j.posted_on.isoformat() if j.posted_on else None,
            "requisition_id": j.requisition_id,
            "ats_provider": j.ats_provider,
            "first_seen_at": j.first_seen_at.isoformat(),
            "notes": j.notes,
        }
        for j in jobs
    ]
    content = spreadsheet.export_rows(rows, format)
    media = (
        "text/csv"
        if format == "csv"
        else ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="noefforts-jobs.{format}"'},
    )


@router.post("/import")
async def import_jobs(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    name = (file.filename or "upload").rsplit("/", 1)[-1][:255]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("csv", "xlsx"):
        raise bad_request("Upload a .csv or .xlsx file")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise bad_request("File is too large")
    try:
        parsed = spreadsheet.parse(content, ext, settings.max_import_rows)
    except spreadsheet.SpreadsheetError as e:
        raise bad_request(str(e)) from None

    batch = ImportBatch(
        user_id=user.id,
        filename=name,
        file_format=ext,
        file_sha256=hashlib.sha256(content).hexdigest(),
    )
    results = []
    for row in parsed:
        row_id = row.values.get("row_id") or f"row-{row.row_number}"
        entry: dict = {"row": row.row_number, "row_id": row_id}
        if row.errors:
            entry |= {"outcome": "error", "errors": row.errors}
        else:
            v = row.values
            try:
                with db.begin_nested():
                    job, created = upsert_job(
                        db,
                        user.id,
                        source=JobSource(ext),
                        url=v["job_url"],
                        employer=v["employer"],
                        title=v["title"],
                        location=v["location"],
                        requisition_id=v["requisition_id"],
                        notes=v["notes"],
                        posted_on=date.fromisoformat(v["posted_on"]) if v["posted_on"] else None,
                        status=JobStatus(v["status"]) if v["status"] else None,
                    )
                entry |= {"outcome": "created" if created else "duplicate", "job_id": str(job.id)}
            except UnsafeURL as e:
                entry |= {"outcome": "error", "errors": [f"job_url: {e}"]}
        results.append(entry)
    batch.rows = results
    batch.total_rows = len(results)
    batch.created_count = sum(r["outcome"] == "created" for r in results)
    batch.duplicate_count = sum(r["outcome"] == "duplicate" for r in results)
    batch.error_count = sum(r["outcome"] == "error" for r in results)
    db.add(batch)
    db.flush()
    record(
        db,
        user.id,
        "jobs.import",
        "import_batch",
        batch.id,
        created=batch.created_count,
        duplicates=batch.duplicate_count,
        errors=batch.error_count,
    )
    db.commit()
    return {
        "batch_id": str(batch.id),
        "total_rows": batch.total_rows,
        "created": batch.created_count,
        "duplicates": batch.duplicate_count,
        "errors": batch.error_count,
        "rows": results,
    }


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _owned(db, user, job_id)
    prefs = db.scalar(select(JobPreferences).where(JobPreferences.user_id == user.id))
    from app.modules.discovery.models import DiscoveredJob
    from app.modules.discovery.provider import PROVIDERS

    sources = db.scalars(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == user.id, DiscoveredJob.job_id == job.id
        )
    )
    return JobDetail(
        **JobOut.model_validate(job).model_dump(),
        description=job.description,
        explanations=explain(job, prefs),
        discovered_from=[
            {
                "provider": d.provider,
                "label": PROVIDERS[d.provider].label if d.provider in PROVIDERS else d.provider,
                "source_url": (d.normalized or {}).get("job_url"),
                "attribution": (d.normalized or {}).get("attribution")
                or {
                    "text": PROVIDERS[d.provider].label if d.provider in PROVIDERS else d.provider,
                    "url": None,
                },
                "last_seen_at": d.last_seen_at.isoformat(),
                "stale": d.stale,
                "stale_reason": d.stale_reason,
                "changed_fields": d.changed_fields or [],
            }
            for d in sources
        ],
    )


@router.get("/{job_id}/route")
def get_route(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """How NoEfforts could apply to this job now: an authorized API, a supported browser
    adapter, a checkpoint for the user, or a manual handoff, with the reasons in order."""
    from app.modules.providers import registry, routing

    job = _owned(db, user, job_id)
    d = routing.route_for_job(db, job)
    spec = registry.PROVIDERS.get(d.provider)
    return {"route": d.route, "provider": d.provider, "message": d.message, "steps": d.steps,
            "stage": spec.stage if spec else None}  # fmt: skip


@router.patch("/{job_id}", response_model=JobOut)
def patch_job(
    job_id: uuid.UUID,
    body: JobPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    job = _owned(db, user, job_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(job, k, v)
    if (
        body.status
        and body.status != JobStatus.excluded
        and "exclusion_reason" not in body.model_fields_set
    ):
        job.exclusion_reason = None
    record(db, user.id, "job.update", "job", job.id, fields=sorted(body.model_fields_set))
    db.commit()
    return job
