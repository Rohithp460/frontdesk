from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.models.enums import TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.services.sla_service import (
    add_working_minutes,
    calculate_resolution_deadline,
    calculate_response_deadline,
    is_working_moment,
    next_working_moment,
    working_minutes_between,
)

KOLKATA = ZoneInfo("Asia/Kolkata")


def local_time(day: int, hour: int, minute: int, *, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=KOLKATA).astimezone(timezone.utc)


def stored_utc(day: int, hour: int, minute: int, *, month: int = 11) -> datetime:
    return local_time(day, hour, minute, month=month).replace(tzinfo=None)


def make_ticket(created_at: datetime, priority: TicketPriority) -> Ticket:
    ticket = Ticket(
        id=1,
        public_ref="INC-0001",
        title="SLA timezone regression",
        customer_id=1,
        priority=priority,
        status=TicketStatus.OPEN,
        created_at=created_at,
    )
    ticket.wait_periods = []
    return ticket


def test_utc_timestamp_is_converted_to_kolkata_before_working_hour_check():
    utc = datetime(2026, 11, 24, 4, 30, tzinfo=timezone.utc)  # Tuesday 10:00 IST
    assert is_working_moment(utc)
    assert add_working_minutes(utc, 60) == stored_utc(24, 11, 0)


def test_naive_datetime_is_treated_as_utc_not_kolkata_wall_time():
    naive_utc = datetime(2026, 11, 24, 4, 30)
    assert is_working_moment(naive_utc)  # 10:00 IST
    assert is_working_moment(datetime(2026, 11, 24, 9, 30))  # 15:00 IST


def test_friday_critical_deadlines_and_remaining_thirty_minutes_carry_over():
    friday_1800 = stored_utc(27, 18, 0)
    ticket = make_ticket(friday_1800, TicketPriority.CRITICAL)
    assert calculate_response_deadline(ticket) == stored_utc(30, 11, 0)
    assert calculate_resolution_deadline(ticket) == stored_utc(30, 18, 0)
    assert add_working_minutes(friday_1800, 60) == stored_utc(30, 10, 0)


def test_friday_1831_starts_on_monday():
    friday_1831 = stored_utc(27, 18, 31)
    assert not is_working_moment(friday_1831)
    assert next_working_moment(friday_1831) == local_time(30, 9, 30)


def test_monday_1829_1830_and_1831_boundaries():
    assert add_working_minutes(stored_utc(23, 18, 29), 1) == stored_utc(23, 18, 30)
    assert add_working_minutes(stored_utc(23, 18, 30), 1) == stored_utc(24, 9, 31)
    assert add_working_minutes(stored_utc(23, 18, 31), 1) == stored_utc(24, 9, 31)


def test_weekends_and_holidays_are_skipped_when_carrying_deadlines():
    friday = stored_utc(27, 18, 0)
    assert add_working_minutes(friday, 60) == stored_utc(30, 10, 0)

    holiday_wednesday = datetime(2026, 11, 25).date()
    tuesday_evening = stored_utc(24, 18, 0)
    ticket = make_ticket(tuesday_evening, TicketPriority.CRITICAL)
    assert calculate_response_deadline(
        ticket, holidays={holiday_wednesday}
    ) == stored_utc(26, 11, 0)

    # A full working day plus one minute must continue after a holiday/weekend.
    assert add_working_minutes(
        stored_utc(24, 9, 30), 541, holidays={holiday_wednesday}
    ) == stored_utc(26, 9, 31)


def test_working_minutes_between_skips_weekend_and_uses_kolkata_hours():
    start = stored_utc(27, 17, 30)
    end = stored_utc(30, 10, 30)
    assert working_minutes_between(start, end) == 120
