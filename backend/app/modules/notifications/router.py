"""Your notifications (priority C, D83): read them, and mark them read or unread. In the app
only: nothing is emailed, texted or pushed. Each route acts on the signed-in account only."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.errors import not_found
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.notifications import service
from app.modules.notifications.models import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


class Keys(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=200)


@router.get("")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    items = service.feed(db, user.id)
    return {"items": items[:limit], "total": len(items), "unread": service.unread(items)}


@router.get("/unread")
def unread_count(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"unread": service.unread(service.feed(db, user.id))}


def _mark(db: Session, user: User, keys: set[str], read: bool) -> dict:
    """Marks only keys of this account's current notifications: any other key is 404, and then
    nothing is marked (another account's key is never confirmed or touched)."""
    items = service.feed(db, user.id)
    if not keys <= {i["key"] for i in items}:
        raise not_found("Notification")
    if read:
        db.execute(
            insert(NotificationRead)
            .values([{"user_id": user.id, "item_key": k, "read_at": utcnow()} for k in keys])
            .on_conflict_do_nothing(constraint="uq_notification_read")
        )
    else:
        db.execute(
            delete(NotificationRead).where(
                NotificationRead.user_id == user.id, NotificationRead.item_key.in_(keys)
            )
        )
    db.commit()
    return {"unread": service.unread(service.feed(db, user.id))}


@router.post("/read")
def mark_read(body: Keys, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _mark(db, user, set(body.keys), True)


@router.post("/unread")
def mark_unread(body: Keys, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _mark(db, user, set(body.keys), False)


@router.post("/read-all")
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    keys = {i["key"] for i in service.feed(db, user.id) if not i["read"]}
    return _mark(db, user, keys, True) if keys else {"unread": 0}
