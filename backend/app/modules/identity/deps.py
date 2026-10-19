import hmac
from datetime import UTC

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.modules.identity.models import User, UserSession
from app.modules.identity.security import hash_token

SESSION_COOKIE = "ne_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    expires = sess.expires_at if sess.expires_at.tzinfo else sess.expires_at.replace(tzinfo=UTC)
    if expires <= utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(sent, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    return sess


def current_user(sess: UserSession = Depends(get_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user
