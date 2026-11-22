"""
Ticket service layer.

All business logic lives here — endpoints stay thin.
Every mutating operation appends a TicketEvent record in the same transaction.
"""
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.agent import Agent
from app.models.enums import ActorType, EventType, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.ticket_wait_period import TicketWaitPeriod
from app.models.ticket_counter import TicketCounter
from app.services.sla_service import (
    calculate_response_deadline,
    calculate_resolution_deadline,
    WORK_MINUTES_PER_DAY,
    add_working_minutes,
    remaining_resolution_minutes,
    remaining_response_minutes,
)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Reference generation
# ---------------------------------------------------------------------------

def _next_public_ref(db: Session) -> str:
    db.execute(
        mysql_insert(TicketCounter)
        .values(name="ticket", last_value=func.last_insert_id(1))
        .on_duplicate_key_update(
            last_value=func.last_insert_id(TicketCounter.last_value + 1)
        )
    )
    next_value = db.execute(select(func.last_insert_id())).scalar_one()
    return f"INC-{next_value:04d}"


def _lock_ticket(db: Session, ticket_id: int) -> Ticket:
    ticket = db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket


def _active_wait_period(db: Session, ticket_id: int) -> Optional[TicketWaitPeriod]:
    return db.execute(
        select(TicketWaitPeriod)
        .where(
            TicketWaitPeriod.ticket_id == ticket_id,
            TicketWaitPeriod.ended_at.is_(None),
        )
        .order_by(TicketWaitPeriod.id.desc())
        .with_for_update()
    ).scalars().first()


def _recalculate_resolution_deadline(
    db: Session,
    ticket: Ticket,
    now: datetime,
    *,
    actor_type: ActorType,
    actor_id: Optional[int],
    reason: str,
) -> None:
    old_deadline = ticket.resolution_deadline
    remaining = remaining_resolution_minutes(ticket, now, db=db)
    ticket.resolution_deadline = add_working_minutes(now, remaining, db=db)
    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=EventType.SLA_DEADLINE_RECALCULATED,
        payload={
            "reason": reason,
            "field": "resolution_deadline",
            "old_deadline": old_deadline.isoformat() if old_deadline else None,
            "new_deadline": ticket.resolution_deadline.isoformat(),
            "remaining_working_minutes": remaining,
        },
    )


def _recalculate_response_deadline(
    db: Session,
    ticket: Ticket,
    now: datetime,
    *,
    actor_type: ActorType,
    actor_id: Optional[int],
    reason: str,
) -> None:
    old_deadline = ticket.response_deadline
    remaining = remaining_response_minutes(ticket, now, db=db)
    ticket.response_deadline = add_working_minutes(now, remaining, db=db)
    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=EventType.SLA_DEADLINE_RECALCULATED,
        payload={
            "reason": reason,
            "field": "response_deadline",
            "old_deadline": old_deadline.isoformat() if old_deadline else None,
            "new_deadline": ticket.response_deadline.isoformat(),
            "remaining_working_minutes": remaining,
        },
    )


def _end_active_wait(
    db: Session,
    ticket: Ticket,
    now: datetime,
    *,
    actor_type: ActorType,
    actor_id: Optional[int],
    reason: str,
) -> bool:
    active_waits = db.execute(
        select(TicketWaitPeriod)
        .where(
            TicketWaitPeriod.ticket_id == ticket.id,
            TicketWaitPeriod.ended_at.is_(None),
        )
        .order_by(TicketWaitPeriod.id)
        .with_for_update()
    ).scalars().all()
    if not active_waits:
        return False
    for active_wait in active_waits:
        active_wait.ended_at = now
    db.flush()
    if ticket.first_response_at is None:
        _recalculate_response_deadline(
            db,
            ticket,
            now,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )
    _recalculate_resolution_deadline(
        db,
        ticket,
        now,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
    )
    return True


def _create_followup_ticket(
    db: Session,
    ticket: Ticket,
    now: datetime,
    *,
    actor_type: ActorType,
    actor_id: Optional[int],
) -> Ticket:
    new_ticket = Ticket(
        public_ref=_next_public_ref(db),
        title=f"Re: {ticket.title}",
        description=ticket.description,
        customer_id=ticket.customer_id,
        assigned_agent_id=ticket.assigned_agent_id,
        priority=ticket.priority,
        status=TicketStatus.OPEN,
        created_at=now,
        reopened_from_ticket_id=ticket.id,
    )
    new_ticket.response_deadline = calculate_response_deadline(new_ticket, db=db)
    new_ticket.resolution_deadline = calculate_resolution_deadline(new_ticket, db=db)
    db.add(new_ticket)
    db.flush()
    for field, deadline in (
        ("response_deadline", new_ticket.response_deadline),
        ("resolution_deadline", new_ticket.resolution_deadline),
    ):
        _append_event(
            db,
            ticket_id=new_ticket.id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=EventType.SLA_DEADLINE_RECALCULATED,
            payload={
                "reason": "followup_ticket_created",
                "field": field,
                "old_deadline": None,
                "new_deadline": deadline.isoformat(),
            },
        )
    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=EventType.NEW_TICKET_CREATED_FROM_CLOSED_TICKET,
        payload={
            "reopened_as_new_ticket_id": new_ticket.id,
            "reason": "reopen_window_expired_or_ticket_closed",
        },
    )
    _append_event(
        db,
        ticket_id=new_ticket.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=EventType.TICKET_CREATED,
        payload={
            "created_from_ticket_id": ticket.id,
            "created_from_ref": ticket.public_ref,
            "priority": new_ticket.priority.value,
            "response_deadline": new_ticket.response_deadline.isoformat(),
            "resolution_deadline": new_ticket.resolution_deadline.isoformat(),
        },
    )
    return new_ticket


# ---------------------------------------------------------------------------
# Shared helper: append a TicketEvent without flushing
# ---------------------------------------------------------------------------

def _append_event(
    db: Session,
    *,
    ticket_id: int,
    actor_type: ActorType,
    actor_id: Optional[int],
    event_type: EventType,
    payload: Optional[dict],
    actor_name: Optional[str] = None,
) -> TicketEvent:
    if actor_name is None and actor_type == ActorType.AGENT and actor_id is not None:
        actor = db.get(Agent, actor_id)
        if actor is not None:
            actor_name = actor.name
    evt = TicketEvent(
        ticket_id=ticket_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload,
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
        actor_name=actor_name,
    )
    db.add(evt)
    return evt


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

def create_ticket(
    db: Session,
    *,
    customer_id: int,
    title: str,
    description: str,
    priority: TicketPriority,
    assigned_agent_id: Optional[int],
    created_by_agent_id: int,
) -> Ticket:
    public_ref = _next_public_ref(db)
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    ticket = Ticket(
        public_ref=public_ref,
        title=title,
        description=description,
        customer_id=customer_id,
        assigned_agent_id=assigned_agent_id,
        priority=priority,
        status=TicketStatus.OPEN,
        created_at=now,
    )

    ticket.response_deadline = calculate_response_deadline(ticket, db=db)
    ticket.resolution_deadline = calculate_resolution_deadline(ticket, db=db)

    db.add(ticket)
    db.flush()

    for field, deadline in (
        ("response_deadline", ticket.response_deadline),
        ("resolution_deadline", ticket.resolution_deadline),
    ):
        _append_event(
            db,
            ticket_id=ticket.id,
            actor_type=ActorType.AGENT,
            actor_id=created_by_agent_id,
            event_type=EventType.SLA_DEADLINE_RECALCULATED,
            payload={
                "reason": "ticket_created",
                "field": field,
                "old_deadline": None,
                "new_deadline": deadline.isoformat(),
            },
        )

    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=ActorType.AGENT,
        actor_id=created_by_agent_id,
        event_type=EventType.TICKET_CREATED,
        payload={
            "priority": priority.value,
            "status": TicketStatus.OPEN.value,
            "assigned_agent_id": assigned_agent_id,
            "response_deadline": ticket.response_deadline.isoformat() if ticket.response_deadline else None,
            "resolution_deadline": ticket.resolution_deadline.isoformat() if ticket.resolution_deadline else None,
        },
    )

    db.commit()
    db.refresh(ticket)
    return ticket


# ---------------------------------------------------------------------------
# LIST (with filters)
# ---------------------------------------------------------------------------

def list_tickets(
    db: Session,
    *,
    status_filter: Optional[TicketStatus] = None,
    priority: Optional[TicketPriority] = None,
    assigned_to_me: bool = False,
    unassigned: bool = False,
    late_only: bool = False,
    waiting_on_customer: bool = False,
    search: Optional[str] = None,
    current_agent_id: int,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Ticket], int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    q = select(Ticket)

    if status_filter is not None:
        q = q.where(Ticket.status == status_filter)
    if priority is not None:
        q = q.where(Ticket.priority == priority)
    if assigned_to_me:
        q = q.where(Ticket.assigned_agent_id == current_agent_id)
    elif unassigned:
        q = q.where(Ticket.assigned_agent_id.is_(None))
    if waiting_on_customer:
        q = q.where(Ticket.status == TicketStatus.WAITING_CUSTOMER)
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        q = q.where(
            (Ticket.title.ilike(pattern, escape="\\"))
            | (Ticket.public_ref.ilike(pattern, escape="\\"))
        )

    if late_only:
        q = q.where(
            (
                (Ticket.first_response_at.is_(None)) &
                (Ticket.response_deadline.is_not(None)) &
                (Ticket.response_deadline < now) &
                (Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]))
            ) |
            (
                (Ticket.resolved_at.is_(None)) &
                (Ticket.resolution_deadline.is_not(None)) &
                (Ticket.resolution_deadline < now) &
                (Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]))
            )
        )

    q = q.order_by(Ticket.created_at.desc())

    total: int = db.execute(
        select(func.count()).select_from(q.subquery())
    ).scalar_one()

    rows = db.execute(q.offset(skip).limit(limit)).scalars().all()
    return list(rows), total


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    return ticket


def mark_missed_response_slas(
    db: Session, *, current_time: Optional[datetime] = None
) -> int:
    now = _utc_naive(current_time or datetime.now(timezone.utc))
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.first_response_at.is_(None),
            Ticket.response_sla_met.is_(None),
            Ticket.response_deadline.is_not(None),
            Ticket.response_deadline < now,
        )
        .values(response_sla_met=False)
    )
    if result.rowcount:
        db.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# ACTIONS
# ---------------------------------------------------------------------------

def claim_ticket(db: Session, *, ticket_id: int, agent_id: int) -> Ticket:
    """Claim an unassigned ticket with one conditional database update."""
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.assigned_agent_id.is_(None))
        .values(assigned_agent_id=agent_id)
    )
    if result.rowcount != 1:
        db.rollback()
        if db.get(Ticket, ticket_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket has already been claimed by another agent.",
        )

    db.flush()
    _append_event(
        db,
        ticket_id=ticket_id,
        actor_type=ActorType.AGENT,
        actor_id=agent_id,
        event_type=EventType.TICKET_ASSIGNED,
        payload={"from_agent_id": None, "to_agent_id": agent_id},
    )
    db.commit()
    ticket = db.get(Ticket, ticket_id)
    db.refresh(ticket)
    return ticket


def change_status(
    db: Session,
    *,
    ticket: Ticket,
    new_status: TicketStatus,
    agent_id: int,
) -> Ticket:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket = _lock_ticket(db, ticket.id)
    old_status = ticket.status
    allowed = {
        TicketStatus.OPEN: {TicketStatus.WAITING_CUSTOMER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
        TicketStatus.WAITING_CUSTOMER: {TicketStatus.OPEN, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    }
    if ticket.status == new_status:
        raise HTTPException(status_code=409, detail=f"Ticket is already {new_status.value}")
    if new_status not in allowed.get(ticket.status, set()):
        raise HTTPException(status_code=409, detail="Invalid ticket status transition")

    if new_status == TicketStatus.WAITING_CUSTOMER:
        ticket.status = new_status
        if _active_wait_period(db, ticket.id) is None:
            db.add(TicketWaitPeriod(ticket_id=ticket.id, started_at=now))
        event_type = EventType.STATUS_CHANGED
    else:
        if old_status == TicketStatus.WAITING_CUSTOMER:
            _end_active_wait(
                db,
                ticket,
                now,
                actor_type=ActorType.AGENT,
                actor_id=agent_id,
                reason=f"ticket_{new_status.value.lower()}",
            )
        ticket.status = new_status
        if new_status == TicketStatus.RESOLVED:
            ticket.resolved_at = now
            ticket.reopened_until = add_working_minutes(
                now, 5 * WORK_MINUTES_PER_DAY, db=db
            )
            ticket.resolution_sla_met = (
                ticket.resolution_deadline is None or now <= ticket.resolution_deadline
            )
            event_type = EventType.TICKET_RESOLVED
        else:
            ticket.closed_at = now
            event_type = EventType.TICKET_CLOSED

    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=ActorType.AGENT,
        actor_id=agent_id,
        event_type=event_type,
        payload={"from": old_status.value, "to": new_status.value},
    )

    db.commit()
    db.refresh(ticket)
    return ticket


def reopen_ticket(
    db: Session,
    *,
    ticket: Ticket,
    agent_id: int,
    current_time: Optional[datetime] = None,
) -> Tuple[Ticket, bool]:
    """
    Reopens a resolved/closed ticket.
    Rules:
    - Resolved ticket can be reopened within 5 working days (ticket.reopened_until).
    - After 5 working days, reopening creates a NEW ticket referencing the original.
    Returns (ticket, is_new_ticket).
    """
    ticket = _lock_ticket(db, ticket.id)
    now = _utc_naive(current_time or datetime.now(timezone.utc))

    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Closed tickets cannot be reopened directly")
    if ticket.status != TicketStatus.RESOLVED:
        raise HTTPException(status_code=409, detail="Only resolved tickets can be reopened")

    window = ticket.reopened_until
    if window is None and ticket.resolved_at is not None:
        window = add_working_minutes(ticket.resolved_at, 5 * WORK_MINUTES_PER_DAY, db=db)

    can_reopen_directly = (window is not None and now <= window)

    if can_reopen_directly:
        old_response_deadline = ticket.response_deadline
        old_resolution_deadline = ticket.resolution_deadline
        ticket.status = TicketStatus.OPEN
        ticket.resolved_at = None
        ticket.closed_at = None
        if ticket.first_response_at is None:
            ticket.response_deadline = calculate_response_deadline(
                ticket, db=db, from_time=now
            )
            _append_event(
                db,
                ticket_id=ticket.id,
                actor_type=ActorType.AGENT,
                actor_id=agent_id,
                event_type=EventType.SLA_DEADLINE_RECALCULATED,
                payload={
                    "reason": "demo_reopen",
                    "field": "response_deadline",
                    "old_deadline": old_response_deadline.isoformat() if old_response_deadline else None,
                    "new_deadline": ticket.response_deadline.isoformat(),
                },
            )
        ticket.resolution_deadline = calculate_resolution_deadline(
            ticket, db=db, from_time=now
        )
        _append_event(
            db,
            ticket_id=ticket.id,
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
            event_type=EventType.SLA_DEADLINE_RECALCULATED,
            payload={
                "reason": "demo_reopen",
                "field": "resolution_deadline",
                "old_deadline": old_resolution_deadline.isoformat() if old_resolution_deadline else None,
                "new_deadline": ticket.resolution_deadline.isoformat(),
            },
        )
        _append_event(
            db,
            ticket_id=ticket.id,
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
            event_type=EventType.TICKET_REOPENED,
            payload={
                "reopened_from_ticket_id": ticket.id,
                "within_window": True,
                "demo_agent_initiated": True,
            },
        )
        db.commit()
        db.refresh(ticket)
        return ticket, False
    else:
        # Window expired -> create new ticket
        new_ticket = _create_followup_ticket(
            db,
            ticket,
            now,
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
        )

        db.commit()
        db.refresh(new_ticket)
        return new_ticket, True


def reply_to_customer(
    db: Session,
    *,
    ticket: Ticket,
    message: str,
    agent_id: int,
) -> Ticket:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket = _lock_ticket(db, ticket.id)
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise HTTPException(status_code=409, detail="Cannot reply to a resolved or closed ticket")
    if ticket.first_response_at is None:
        ticket.first_response_at = now
        if ticket.response_deadline is not None:
            ticket.response_sla_met = now <= ticket.response_deadline

    old_status = ticket.status
    ticket.status = TicketStatus.WAITING_CUSTOMER
    if _active_wait_period(db, ticket.id) is None:
        db.add(TicketWaitPeriod(ticket_id=ticket.id, started_at=now))
    if old_status != TicketStatus.WAITING_CUSTOMER:
        _append_event(
            db,
            ticket_id=ticket.id,
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
            event_type=EventType.STATUS_CHANGED,
            payload={"from": old_status.value, "to": TicketStatus.WAITING_CUSTOMER.value},
        )

    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=ActorType.AGENT,
        actor_id=agent_id,
        event_type=EventType.AGENT_REPLY,
        payload={"message": message, "target": "customer"},
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def simulate_customer_reply(
    db: Session,
    *,
    ticket: Ticket,
    message: str,
) -> Ticket:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket = _lock_ticket(db, ticket.id)
    old_status = ticket.status
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        window = ticket.reopened_until
        if window is None and ticket.resolved_at is not None:
            window = add_working_minutes(
                ticket.resolved_at, 5 * WORK_MINUTES_PER_DAY, db=db
            )
        if (
            ticket.status == TicketStatus.RESOLVED
            and window is not None
            and now <= window
        ):
            old_resolution_deadline = ticket.resolution_deadline
            ticket.status = TicketStatus.OPEN
            ticket.resolved_at = None
            ticket.resolution_deadline = calculate_resolution_deadline(
                ticket, db=db, from_time=now
            )
            _append_event(
                db,
                ticket_id=ticket.id,
                actor_type=ActorType.CUSTOMER,
                actor_id=ticket.customer_id,
                event_type=EventType.SLA_DEADLINE_RECALCULATED,
                payload={
                    "reason": "customer_reopen",
                    "field": "resolution_deadline",
                    "old_deadline": old_resolution_deadline.isoformat() if old_resolution_deadline else None,
                    "new_deadline": ticket.resolution_deadline.isoformat(),
                },
            )
            _append_event(
                db,
                ticket_id=ticket.id,
                actor_type=ActorType.CUSTOMER,
                actor_id=ticket.customer_id,
                event_type=EventType.TICKET_REOPENED,
                payload={"within_window": True, "demo_simulation": True},
            )
        else:
            followup = _create_followup_ticket(
                db,
                ticket,
                now,
                actor_type=ActorType.CUSTOMER,
                actor_id=ticket.customer_id,
            )
            _append_event(
                db,
                ticket_id=followup.id,
                actor_type=ActorType.CUSTOMER,
                actor_id=ticket.customer_id,
                event_type=EventType.CUSTOMER_REPLY,
                payload={"message": message, "demo_simulation": True},
            )
            db.commit()
            db.refresh(followup)
            return followup

    ended_wait = _end_active_wait(
        db,
        ticket,
        now,
        actor_type=ActorType.CUSTOMER,
        actor_id=ticket.customer_id,
        reason="customer_reply",
    )
    if ticket.status == TicketStatus.WAITING_CUSTOMER or ended_wait:
        ticket.status = TicketStatus.OPEN
        _append_event(
            db,
            ticket_id=ticket.id,
            actor_type=ActorType.CUSTOMER,
            actor_id=ticket.customer_id,
            event_type=EventType.STATUS_CHANGED,
            payload={
                "from": old_status.value,
                "to": TicketStatus.OPEN.value,
                "trigger": "customer_reply",
            },
        )
    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=ActorType.CUSTOMER,
        actor_id=ticket.customer_id,
        event_type=EventType.CUSTOMER_REPLY,
        payload={
            "action": "CUSTOMER_REPLY",
            "message": message,
            "previous_status": old_status.value,
            "demo_simulation": True,
        },
    )

    db.commit()
    db.refresh(ticket)
    return ticket


def add_internal_note(
    db: Session,
    *,
    ticket: Ticket,
    note: str,
    agent_id: int,
) -> Ticket:
    ticket = _lock_ticket(db, ticket.id)
    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=ActorType.AGENT,
        actor_id=agent_id,
        event_type=EventType.INTERNAL_NOTE_ADDED,
        payload={"note": note, "visibility": "internal"},
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def change_priority(
    db: Session,
    *,
    ticket: Ticket,
    new_priority: TicketPriority,
    agent_id: int,
) -> Ticket:
    ticket = _lock_ticket(db, ticket.id)
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Priority cannot be changed after resolution or closure",
        )
    if ticket.priority == new_priority:
        return ticket

    old_priority = ticket.priority
    ticket.priority = new_priority

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if ticket.first_response_at is None:
        _recalculate_response_deadline(
            db,
            ticket,
            now,
            actor_type=ActorType.AGENT,
            actor_id=agent_id,
            reason="priority_changed",
        )
        ticket.response_sla_met = None
    _recalculate_resolution_deadline(
        db,
        ticket,
        now,
        actor_type=ActorType.AGENT,
        actor_id=agent_id,
        reason="priority_changed",
    )
    ticket.resolution_sla_met = None

    _append_event(
        db,
        ticket_id=ticket.id,
        actor_type=ActorType.AGENT,
        actor_id=agent_id,
        event_type=EventType.PRIORITY_CHANGED,
        payload={
            "from": old_priority.value,
            "to": new_priority.value,
            "new_response_deadline": ticket.response_deadline.isoformat() if ticket.response_deadline else None,
            "new_resolution_deadline": ticket.resolution_deadline.isoformat() if ticket.resolution_deadline else None,
        },
    )

    db.commit()
    db.refresh(ticket)
    return ticket


def auto_close_inactive_tickets(
    db: Session,
    *,
    current_time: Optional[datetime] = None,
) -> list[Ticket]:
    """
    Auto-closes tickets in 'pending' (waiting on customer) status after 5 working days
    without customer reply.
    """
    now = _utc_naive(current_time or datetime.now(timezone.utc))
    closed_tickets = []

    pending_ids = db.execute(
        select(Ticket.id).where(Ticket.status == TicketStatus.WAITING_CUSTOMER)
    ).scalars().all()

    for ticket_id in pending_ids:
        ticket = _lock_ticket(db, ticket_id)
        if ticket.status != TicketStatus.WAITING_CUSTOMER:
            continue
        active_wp = _active_wait_period(db, ticket.id)

        wait_start = active_wp.started_at if active_wp else ticket.updated_at
        auto_close_threshold = add_working_minutes(wait_start, 5 * WORK_MINUTES_PER_DAY, db=db)

        if now >= auto_close_threshold:
            _end_active_wait(
                db,
                ticket,
                now,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                reason="auto_close",
            )
            ticket.status = TicketStatus.CLOSED
            ticket.closed_at = now

            _append_event(
                db,
                ticket_id=ticket.id,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type=EventType.AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY,
                payload={"reason": "auto_close_no_customer_reply_5_working_days"},
            )
            db.flush()
            closed_tickets.append(ticket)

    if closed_tickets:
        db.commit()
        for t in closed_tickets:
            db.refresh(t)

    return closed_tickets


def get_customer_facing_ticket(
    db: Session,
    ticket_id: int,
    customer_id: int,
) -> dict:
    """
    Returns customer-facing ticket view.
    CRITICAL: Internal notes ('noted' event_type) and internal payloads
    MUST NEVER appear in this response.
    """
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.customer_id != customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found for customer",
        )

    # Filter out internal events (noted, internal notes)
    filtered_timeline = []
    for evt in ticket.events:
        if evt.event_type == EventType.INTERNAL_NOTE_ADDED:
            continue  # strictly exclude internal notes!

        # Public messages
        msg = None
        if evt.payload and isinstance(evt.payload, dict):
            msg = evt.payload.get("message")

        filtered_timeline.append({
            "id": evt.id,
            "ticket_id": evt.ticket_id,
            "actor_type": evt.actor_type.value,
            "event_type": evt.event_type.value,
            "message": msg,
            "occurred_at": evt.occurred_at,
        })

    return {
        "id": ticket.id,
        "public_ref": ticket.public_ref,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status.value,
        "created_at": ticket.created_at,
        "timeline": filtered_timeline,
    }
