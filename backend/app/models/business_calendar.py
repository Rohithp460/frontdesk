from datetime import date as date_type
from typing import Optional

from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BusinessCalendar(Base):
    """
    One row per calendar date.
    Used to calculate SLA deadlines, skipping weekends and holidays.
    """

    __tablename__ = "business_calendar"

    # Named 'calendar_date' to avoid shadowing Python's built-in `date`
    calendar_date: Mapped[date_type] = mapped_column(
        "date", Date, primary_key=True, nullable=False
    )
    is_working_day: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    is_holiday: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BusinessCalendar date={self.calendar_date} "
            f"working={self.is_working_day} holiday={self.is_holiday}>"
        )
