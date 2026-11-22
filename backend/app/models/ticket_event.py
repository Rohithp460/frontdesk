from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, event, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ActorType, EventType


class TicketEvent(Base):
    """
    Append-only audit log of everything that happens on a ticket.

    Application-layer invariant: rows must NEVER be updated or deleted.
    The table has no `updated_at` column intentionally to enforce this.
    INSERT-only permissions should be granted at the DB level in production.
    """

    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    ticket_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )

    # Nullable because system events have no actor_id
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        index=True,
    )

    # Flexible JSON bag: before/after values, comment body, etc.
    payload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("UTC_TIMESTAMP(6)"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("UTC_TIMESTAMP(6)")
    )

    # Relationship back to ticket
    ticket: Mapped["Ticket"] = relationship(  # noqa: F821
        "Ticket", back_populates="events"
    )

    def __repr__(self) -> str:
        return (
            f"<TicketEvent id={self.id} ticket_id={self.ticket_id} "
            f"type={self.event_type} actor={self.actor_type}:{self.actor_id}>"
        )


@event.listens_for(TicketEvent, "before_update")
def prevent_event_update(mapper, connection, target) -> None:
    raise ValueError("Ticket events are immutable")


@event.listens_for(TicketEvent, "before_delete")
def prevent_event_delete(mapper, connection, target) -> None:
    raise ValueError("Ticket events cannot be deleted")
