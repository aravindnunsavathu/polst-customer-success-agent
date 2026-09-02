import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def pg_enum(enum_cls, name: str) -> Enum:
    """SQLAlchemy's Enum(SomePyEnum) stores members by .name by default —
    for our `str, enum.Enum` classes that means uppercase Python
    identifiers ("REJECTED"), not the lowercase .value strings the rest of
    the codebase (and any JSON-serialized API output) actually uses
    ("rejected"). values_callable makes the native Postgres enum type
    store .value instead, so DB rows, Python code, and API payloads agree."""
    return Enum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TemporalMixin:
    """SCD2-style versioning for entities with mutable dimensions we need to
    reconstruct historically (BUILD-PROMPT.md §4: "I need to reconstruct
    what the system believed about an account two quarters ago"). Each row
    is one version; valid_to IS NULL marks the current version. A partial
    unique index (in the migration) enforces exactly one current row per
    business key.
    """

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
