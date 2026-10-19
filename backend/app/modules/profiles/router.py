import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import conflict, not_found
from app.modules.audit.service import record
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.profiles import schemas as s
from app.modules.profiles.models import (
    Approval,
    CandidateProfile,
    Credential,
    EducationRecord,
    EmploymentRecord,
    FactVersion,
    JobPreferences,
    WorkAuthorization,
)
from app.modules.profiles.service import apply_fact_update

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=s.ProfileOut | None)
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))


@router.put("", response_model=s.ProfileOut)
def put_profile(
    body: s.ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    if prof is None:
        prof = CandidateProfile(user_id=user.id)
    if apply_fact_update(db, prof, body.model_dump(), entity_type="profile"):
        record(db, user.id, "profile.update", "profile", prof.id, version=prof.version)
    db.commit()
    return prof


@router.get("/preferences", response_model=s.PreferencesOut)
def get_preferences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    prefs = db.scalar(select(JobPreferences).where(JobPreferences.user_id == user.id))
    return prefs or s.PreferencesOut()


@router.put("/preferences", response_model=s.PreferencesOut)
def put_preferences(
    body: s.PreferencesIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    prefs = db.scalar(select(JobPreferences).where(JobPreferences.user_id == user.id))
    if prefs is None:
        prefs = JobPreferences(user_id=user.id)
        db.add(prefs)
    data = body.model_dump()
    for k, v in data.items():
        setattr(prefs, k, v)
    record(db, user.id, "preferences.update", "preferences", None)
    db.commit()
    db.refresh(prefs)
    return prefs


@router.get("/history/{entity_id}")
def fact_history(
    entity_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[dict]:
    rows = db.scalars(
        select(FactVersion)
        .where(FactVersion.user_id == user.id, FactVersion.entity_id == entity_id)
        .order_by(FactVersion.version)
    ).all()
    return [
        {"version": r.version, "snapshot": r.snapshot, "created_at": r.created_at} for r in rows
    ]


def _record_routes(
    path: str, model, schema_in: type[BaseModel], schema_out: type[BaseModel], entity: str
) -> None:
    """Register list/create/update/delete/approve routes for a user-owned fact table."""

    def _get_owned(db: Session, user: User, item_id: uuid.UUID):
        obj = db.get(model, item_id)
        if obj is None or obj.user_id != user.id:
            raise not_found(entity)
        return obj

    @router.get(f"/{path}", response_model=list[schema_out], name=f"list_{entity}")
    def list_items(user: User = Depends(current_user), db: Session = Depends(get_db)):
        return db.scalars(select(model).where(model.user_id == user.id)).all()

    @router.post(
        f"/{path}",
        response_model=schema_out,
        status_code=status.HTTP_201_CREATED,
        name=f"create_{entity}",
    )
    def create_item(
        body: schema_in,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),  # type: ignore[valid-type]
    ):
        obj = model(user_id=user.id)
        try:
            apply_fact_update(db, obj, body.model_dump(), entity_type=entity)
        except IntegrityError:
            db.rollback()
            raise conflict(f"{entity} already exists") from None
        record(db, user.id, f"{entity}.create", entity, obj.id)
        db.commit()
        return obj

    @router.put(f"/{path}/{{item_id}}", response_model=schema_out, name=f"update_{entity}")
    def update_item(
        item_id: uuid.UUID,
        body: schema_in,  # type: ignore[valid-type]
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ):
        obj = _get_owned(db, user, item_id)
        try:
            if apply_fact_update(db, obj, body.model_dump(), entity_type=entity):
                record(db, user.id, f"{entity}.update", entity, obj.id, version=obj.version)
        except IntegrityError:
            db.rollback()
            raise conflict(f"{entity} already exists") from None
        db.commit()
        return obj

    @router.post(
        f"/{path}/{{item_id}}/approve", response_model=schema_out, name=f"approve_{entity}"
    )
    def approve_item(
        item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
    ):
        obj = _get_owned(db, user, item_id)
        obj.approval_status = Approval.approved
        record(db, user.id, f"{entity}.approve", entity, obj.id, version=obj.version)
        db.commit()
        return obj

    @router.delete(
        f"/{path}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT, name=f"delete_{entity}"
    )
    def delete_item(
        item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
    ) -> None:
        obj = _get_owned(db, user, item_id)
        db.delete(obj)
        record(db, user.id, f"{entity}.delete", entity, item_id)
        db.commit()


_record_routes(
    "work-authorizations",
    WorkAuthorization,
    s.WorkAuthorizationIn,
    s.WorkAuthorizationOut,
    "work_authorization",
)
_record_routes("employment", EmploymentRecord, s.EmploymentIn, s.EmploymentOut, "employment")
_record_routes("education", EducationRecord, s.EducationIn, s.EducationOut, "education")
_record_routes("credentials", Credential, s.CredentialIn, s.CredentialOut, "credential")
