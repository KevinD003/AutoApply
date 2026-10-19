from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.applications import states
from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.states import Actor, AppState


def transition(
    db: Session, app: Application, target: AppState, actor: Actor, reason: str | None = None
) -> None:
    """Validate and apply a transition. The version column makes concurrent writers conflict."""
    states.check(app.state, target, actor)
    db.add(
        ApplicationEvent(
            application_id=app.id,
            kind="state_change",
            from_state=app.state,
            to_state=target,
            actor=actor,
            reason=reason,
        )
    )
    app.state = target
    app.state_changed_at = utcnow()
