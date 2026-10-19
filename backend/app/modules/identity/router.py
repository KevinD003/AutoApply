from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, utcnow
from app.modules.audit.service import record
from app.modules.identity.deps import SESSION_COOKIE, current_user, get_session
from app.modules.identity.models import User, UserSession
from app.modules.identity.security import (
    hash_password,
    hash_token,
    login_limiter,
    new_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)


class SessionOut(BaseModel):
    user_id: str
    email: str
    csrf_token: str


def _start_session(db: Session, user: User, response: Response) -> SessionOut:
    settings = get_settings()
    token = new_token()
    sess = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_token(),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(sess)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return SessionOut(user_id=str(user.id), email=user.email, csrf_token=sess.csrf_token)


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    record(db, user.id, "auth.register", "user", user.id)
    return _start_session(db, user, response)


@router.post("/login", response_model=SessionOut)
def login(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut:
    email = body.email.lower()
    client = request.client.host if request.client else "unknown"
    if not login_limiter.allow(f"{client}:{email}", get_settings().login_rate_limit_per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try later")
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    record(db, user.id, "auth.login", "user", user.id)
    return _start_session(db, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response, sess: UserSession = Depends(get_session), db: Session = Depends(get_db)
) -> None:
    db.delete(sess)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=SessionOut)
def me(sess: UserSession = Depends(get_session), user: User = Depends(current_user)) -> SessionOut:
    return SessionOut(user_id=str(user.id), email=user.email, csrf_token=sess.csrf_token)
