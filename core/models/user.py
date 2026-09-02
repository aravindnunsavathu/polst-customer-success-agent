import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "users"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    # Nullable at the DB level — a user without a department is a data gap
    # to be caught by the fail-loud rule in /metrics, not a constraint
    # violation that would block ingestion of otherwise-usable rows.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
