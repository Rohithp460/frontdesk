from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TicketWaitPeriod(Base):
    """
    Tracks discrete periods where a ticket was in a waiting state
    (e.g. waiting for customer reply, waiting on third-party).
    Used for accurate SLA elapsed-time calculations that exclude wait periods.
    """

    __tablename__ = "ticket_wait_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    ticket_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("UTC_TIMESTAMP(6)")
    )

    # NULL means the wait period is still active
    ended_at: Mapped[Optional[datetime]] = mapped_column(DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("UTC_TIMESTAMP(6)")
    )

    ticket: Mapped["Ticket"] = relationship(  # noqa: F821
        "Ticket", back_populates="wait_periods"
    )

    def __repr__(self) -> str:
        return (
            f"<TicketWaitPeriod id={self.id} ticket_id={self.ticket_id} "
            f"started={self.started_at} ended={self.ended_at}>"
        )
