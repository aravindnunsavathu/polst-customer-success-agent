import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import UserEventType
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey, pg_enum


class UserEvent(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "user_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    event_type: Mapped[UserEventType] = mapped_column(
        pg_enum(UserEventType, "user_event_type"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ProductError(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "product_errors"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
