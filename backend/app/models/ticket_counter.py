from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TicketCounter(Base):
    __tablename__ = "ticket_counters"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
