from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import TicketPriority, TicketStatus


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Human-readable reference, e.g. "INC-00042"
    public_ref: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # FK → customers
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # FK → agents (nullable — ticket may be unassigned)
    assigned_agent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, name="ticket_priority", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=TicketPriority.MEDIUM,
        server_default=TicketPriority.MEDIUM.value,
    )

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=TicketStatus.OPEN,
        server_default=TicketStatus.OPEN.value,
    )

    # SLA / lifecycle timestamps
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)

    # SLA deadlines (computed when ticket is created / escalated)
    response_deadline: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)
    resolution_deadline: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)
    response_sla_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    resolution_sla_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # For reopened tickets: until when reopening is allowed
    reopened_until: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)
    reopened_from_ticket_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("UTC_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=text("UTC_TIMESTAMP(6)"),
        onupdate=text("UTC_TIMESTAMP(6)")
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", foreign_keys=[customer_id], lazy="select"
    )
    assigned_agent: Mapped[Optional["Agent"]] = relationship(  # noqa: F821
        "Agent", foreign_keys=[assigned_agent_id], lazy="select"
    )
    events: Mapped[list["TicketEvent"]] = relationship(  # noqa: F821
        "TicketEvent",
        back_populates="ticket",
        order_by="(TicketEvent.occurred_at, TicketEvent.id)",
        lazy="dynamic",
    )
    wait_periods: Mapped[list["TicketWaitPeriod"]] = relationship(  # noqa: F821
        "TicketWaitPeriod",
        back_populates="ticket",
        order_by="(TicketWaitPeriod.started_at, TicketWaitPeriod.id)",
        lazy="select",
    )
    reopened_from_ticket: Mapped[Optional["Ticket"]] = relationship(  # noqa: F821
        "Ticket",
        remote_side="Ticket.id",
        foreign_keys=[reopened_from_ticket_id],
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} ref={self.public_ref!r} status={self.status}>"
