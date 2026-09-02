import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey


class FeedbackItem(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "feedback_items"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    verbatim: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str | None] = mapped_column(String, nullable=True)
    routed_to: Mapped[str | None] = mapped_column(String, nullable=True)
    linked_ticket: Mapped[str | None] = mapped_column(String, nullable=True)
