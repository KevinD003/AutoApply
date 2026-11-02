"""D115: the answer brain's training labels and each account's trained model.

A label is the account's own verdict on one suggestion: this saved answer does (or does not)
answer this new question. The model learns only from those verdicts, per account."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base, new_id, utcnow


class LearningLabel(Base):
    __tablename__ = "learning_labels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question_key: Mapped[str] = mapped_column(String(64))
    bank_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("answer_bank.id", ondelete="SET NULL")
    )
    accepted: Mapped[bool] = mapped_column(Boolean)
    # The pair's numeric features at the time (features.NAMES); no question or answer text.
    features: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningModel(Base):
    __tablename__ = "learning_models"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    engine: Mapped[str] = mapped_column(String(20))  # lightgbm | xgboost
    samples: Mapped[int] = mapped_column(Integer)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    blob: Mapped[bytes] = mapped_column(LargeBinary)
