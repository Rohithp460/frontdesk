from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Set
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_calendar import BusinessCalendar
from app.models.enums import TicketPriority
from app.models.ticket import Ticket
from app.models.ticket_wait_period import TicketWaitPeriod

WORK_START_TIME = time(9, 30)
WORK_END_TIME = time(18, 30)
WORK_MINUTES_PER_DAY = 540
KOLKATA = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

SLA_CONFIG = {
    TicketPriority.CRITICAL: {"response_minutes": 120, "resolution_minutes": 540},
    TicketPriority.MEDIUM: {"response_minutes": 270, "resolution_minutes": 1620},
    TicketPriority.LOW: {"response_minutes": 540, "resolution_minutes": 2700},
}


def _utc_datetime(value: datetime) -> datetime:
    """Interpret naive database datetimes as UTC; normalize aware values to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _local_datetime(value: datetime) -> datetime:
    return _utc_datetime(value).astimezone(KOLKATA)


def _db_datetime(value: datetime) -> datetime:
    """Return a naive UTC datetime suitable for MySQL DATETIME columns."""
    return _utc_datetime(value).replace(tzinfo=None)


def is_working_day(
    d: date,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
) -> bool:
    if d.weekday() >= 5 or (holidays is not None and d in holidays):
        return False
    if db is not None:
        day = db.execute(
            select(BusinessCalendar).where(BusinessCalendar.calendar_date == d)
        ).scalar_one_or_none()
        if day is not None and (not day.is_working_day or day.is_holiday):
            return False
    return True


def is_working_moment(
    dt: datetime,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
) -> bool:
    local = _local_datetime(dt)
    return (
        is_working_day(local.date(), db=db, holidays=holidays)
        and WORK_START_TIME <= local.time() < WORK_END_TIME
    )


def next_working_moment(
    dt: datetime,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
) -> datetime:
    local = _local_datetime(dt)
    if is_working_day(local.date(), db=db, holidays=holidays):
        if local.time() < WORK_START_TIME:
            return datetime.combine(local.date(), WORK_START_TIME, KOLKATA)
        if local.time() < WORK_END_TIME:
            return local

    candidate = local.date() + timedelta(days=1)
    while not is_working_day(candidate, db=db, holidays=holidays):
        candidate += timedelta(days=1)
    return datetime.combine(candidate, WORK_START_TIME, KOLKATA)


def add_working_minutes(
    start: datetime,
    minutes: int,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
) -> datetime:
    if minutes < 0:
        raise ValueError("working minutes cannot be negative")
    if minutes == 0:
        return _db_datetime(start)

    current = next_working_moment(start, db=db, holidays=holidays)
    remaining = minutes
    while remaining:
        day_end = datetime.combine(current.date(), WORK_END_TIME, KOLKATA)
        available = int((day_end - current).total_seconds() // 60)
        if remaining <= available:
            current += timedelta(minutes=remaining)
            remaining = 0
        else:
            remaining -= available
            current = next_working_moment(
                day_end + timedelta(microseconds=1), db=db, holidays=holidays
            )
    return _db_datetime(current)


def working_minutes_between(
    start: datetime,
    end: datetime,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
) -> int:
    start_utc, end_utc = _utc_datetime(start), _utc_datetime(end)
    if end_utc <= start_utc:
        return 0
    current = next_working_moment(start_utc, db=db, holidays=holidays)
    end_local = end_utc.astimezone(KOLKATA)
    total = 0
    while current < end_local:
        close = datetime.combine(current.date(), WORK_END_TIME, KOLKATA)
        segment_end = min(end_local, close)
        if segment_end > current:
            total += int((segment_end - current).total_seconds() // 60)
        current = next_working_moment(
            close + timedelta(microseconds=1), db=db, holidays=holidays
        )
    return total


def get_ticket_total_wait_minutes(
    ticket: Ticket,
    as_of: Optional[datetime] = None,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
) -> int:
    total = 0
    for period in getattr(ticket, "wait_periods", []) or []:
        # An active wait is excluded only once it has actually ended.
        if period.ended_at is not None:
            total += working_minutes_between(
                period.started_at, period.ended_at, db=db, holidays=holidays
            )
    return total


def _calculate_deadline(
    ticket: Ticket,
    sla_minutes: int,
    *,
    db: Optional[Session],
    holidays: Optional[Set[date]],
    exclude_waiting: bool,
    from_time: Optional[datetime],
) -> datetime:
    start = from_time or ticket.created_at
    deadline = add_working_minutes(start, sla_minutes, db=db, holidays=holidays)
    if exclude_waiting:
        for period in sorted(
            getattr(ticket, "wait_periods", []) or [],
            key=lambda item: item.started_at,
        ):
            if period.ended_at is None:
                continue
            wait_start = max(_utc_datetime(period.started_at), _utc_datetime(start))
            wait_end = _utc_datetime(period.ended_at)
            if wait_end > wait_start:
                wait_minutes = working_minutes_between(
                    wait_start, wait_end, db=db, holidays=holidays
                )
                deadline = add_working_minutes(
                    deadline, wait_minutes, db=db, holidays=holidays
                )
    return deadline


def calculate_response_deadline(
    ticket: Ticket,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
    exclude_waiting: bool = True,
    from_time: Optional[datetime] = None,
) -> datetime:
    config = SLA_CONFIG[ticket.priority]
    return _calculate_deadline(
        ticket,
        config["response_minutes"],
        db=db,
        holidays=holidays,
        exclude_waiting=exclude_waiting,
        from_time=from_time,
    )


def calculate_resolution_deadline(
    ticket: Ticket,
    db: Optional[Session] = None,
    holidays: Optional[Set[date]] = None,
    exclude_waiting: bool = True,
    from_time: Optional[datetime] = None,
) -> datetime:
    config = SLA_CONFIG[ticket.priority]
    return _calculate_deadline(
        ticket,
        config["resolution_minutes"],
        db=db,
        holidays=holidays,
        exclude_waiting=exclude_waiting,
        from_time=from_time,
    )


def remaining_resolution_minutes(
    ticket: Ticket,
    now: datetime,
    db: Optional[Session] = None,
) -> int:
    """Return SLA allowance remaining after completed working time and waits."""
    total = SLA_CONFIG[ticket.priority]["resolution_minutes"]
    return _remaining_allowance(ticket, now, total, db=db)


def remaining_response_minutes(
    ticket: Ticket,
    now: datetime,
    db: Optional[Session] = None,
) -> int:
    """Return response allowance remaining after elapsed working time and waits."""
    total = SLA_CONFIG[ticket.priority]["response_minutes"]
    return _remaining_allowance(ticket, now, total, db=db)


def _remaining_allowance(
    ticket: Ticket,
    now: datetime,
    total: int,
    *,
    db: Optional[Session],
) -> int:
    elapsed = working_minutes_between(ticket.created_at, now, db=db)
    excluded = 0
    for period in getattr(ticket, "wait_periods", []) or []:
        end = period.ended_at or now
        start = max(_utc_datetime(period.started_at), _utc_datetime(ticket.created_at))
        end = min(_utc_datetime(end), _utc_datetime(now))
        if end > start:
            excluded += working_minutes_between(start, end, db=db)
    return max(0, total - max(0, elapsed - excluded))
