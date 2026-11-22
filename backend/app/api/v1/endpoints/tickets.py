from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_agent
from app.db.session import get_db
from app.models.agent import Agent
from app.models.enums import AgentRole, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.schemas.ticket import (
    CustomerReplyRequest,
    CustomerTicketOut,
    InternalNoteRequest,
    PaginatedTickets,
    PaginatedTicketList,
    TicketListItem,
    TicketEventOut,
    PriorityPatchRequest,
    ReplyRequest,
    StatusPatchRequest,
    TicketCreateRequest,
    TicketOut,
)
from app.services.ticket_service import (
    add_internal_note as add_internal_note_service,
    change_priority,
    change_status,
    claim_ticket,
    create_ticket,
    get_customer_facing_ticket,
    get_ticket_or_404,
    list_tickets,
    mark_missed_response_slas,
    reopen_ticket,
    reply_to_customer,
    simulate_customer_reply,
)

router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"],
)


def _managed_ticket(ticket_id: int, db: Session, agent: Agent) -> Ticket:
    ticket = db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    if (
        agent.role != AgentRole.ADMIN
        and ticket.assigned_agent_id != agent.id
    ):
        raise HTTPException(status_code=403, detail="Only the assigned agent or an admin can manage this ticket")
    return ticket


def _ticket_out(ticket: Ticket) -> TicketOut:
    data = {
        key: value
        for key, value in ticket.__dict__.items()
        if not key.startswith("_")
    }
    data["customer"] = ticket.customer
    data["assigned_agent"] = ticket.assigned_agent
    data["events"] = list(ticket.events)
    return TicketOut.model_validate(data)


@router.post(
    "",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a ticket",
)
def create(
    body: TicketCreateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    if (
        body.assigned_agent_id is not None
        and current_agent.role != AgentRole.ADMIN
        and body.assigned_agent_id != current_agent.id
    ):
        raise HTTPException(status_code=403, detail="Agents may only assign tickets to themselves")
    agent_id = current_agent.id
    db.rollback()
    ticket = create_ticket(
        db,
        customer_id=body.customer_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assigned_agent_id=body.assigned_agent_id,
        created_by_agent_id=agent_id,
    )
    out = _ticket_out(ticket)
    return out


@router.get(
    "",
    response_model=PaginatedTicketList,
    summary="List tickets",
)
def list_all(
    status_filter: Optional[TicketStatus] = Query(default=None, alias="status"),
    priority_filter: Optional[TicketPriority] = Query(default=None, alias="priority"),
    mine: bool = Query(default=False),
    assigned_to_me: bool = Query(default=False),
    unassigned: bool = Query(default=False),
    late_only: bool = Query(default=False),
    late: bool = Query(default=False),
    waiting_on_customer: bool = Query(default=False),
    search: Optional[str] = Query(default=None, max_length=255),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> PaginatedTicketList:
    mark_missed_response_slas(db)
    items, total = list_tickets(
        db,
        status_filter=status_filter,
        priority=priority_filter,
        assigned_to_me=mine or assigned_to_me,
        unassigned=unassigned,
        late_only=late or late_only,
        waiting_on_customer=waiting_on_customer,
        search=search,
        current_agent_id=current_agent.id,
        skip=skip,
        limit=limit,
    )
    list_items = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for ticket in items:
        is_response_late = (
            ticket.first_response_at is None
            and ticket.response_deadline is not None
            and ticket.response_deadline < now
            and ticket.status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}
        )
        is_resolution_late = (
            ticket.resolved_at is None
            and ticket.resolution_deadline is not None
            and ticket.resolution_deadline < now
            and ticket.status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}
        )
        if is_response_late or is_resolution_late:
            sla_state = "LATE"
        elif ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
            sla_state = "NOT_APPLICABLE"
        elif ticket.response_deadline or ticket.resolution_deadline:
            nearest = min(
                value for value in (ticket.response_deadline, ticket.resolution_deadline)
                if value is not None
            )
            due_in = nearest - now
            sla_state = "DUE_SOON" if due_in.total_seconds() <= 8 * 60 * 60 else "ON_TRACK"
        else:
            sla_state = "NOT_APPLICABLE"
        list_items.append(TicketListItem(
            id=ticket.id,
            public_ref=ticket.public_ref,
            title=ticket.title,
            priority=ticket.priority,
            status=ticket.status,
            customer_id=ticket.customer_id,
            assigned_agent_id=ticket.assigned_agent_id,
            customer_name=ticket.customer.name,
            assigned_agent_name=ticket.assigned_agent.name if ticket.assigned_agent else None,
            created_at=ticket.created_at,
            response_deadline=ticket.response_deadline,
            resolution_deadline=ticket.resolution_deadline,
            first_response_at=ticket.first_response_at,
            resolved_at=ticket.resolved_at,
            is_response_late=is_response_late,
            is_resolution_late=is_resolution_late,
            is_waiting_on_customer=ticket.status == TicketStatus.WAITING_CUSTOMER,
            sla_state=sla_state,
        ))
    return PaginatedTicketList(
        total=total,
        skip=skip,
        limit=limit,
        items=list_items,
    )


@router.get(
    "/customer-view/{ticket_id}",
    response_model=CustomerTicketOut,
    summary="Customer-facing ticket view (Internal notes strictly excluded)",
)
def customer_view(
    ticket_id: int,
    customer_id: int = Query(...),
    db: Session = Depends(get_db),
    _: Agent = Depends(get_current_agent),
) -> CustomerTicketOut:
    data = get_customer_facing_ticket(db, ticket_id=ticket_id, customer_id=customer_id)
    return CustomerTicketOut(**data)


@router.get(
    "/{ticket_id}/customer-view",
    response_model=CustomerTicketOut,
    summary="Customer-facing ticket view",
)
def customer_view_exact(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: Agent = Depends(get_current_agent),
) -> CustomerTicketOut:
    ticket = get_ticket_or_404(db, ticket_id)
    data = get_customer_facing_ticket(db, ticket_id=ticket_id, customer_id=ticket.customer_id)
    return CustomerTicketOut(**data)


@router.get(
    "/{ticket_id}",
    response_model=TicketOut,
    summary="Get a single ticket",
)
def get_one(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: Agent = Depends(get_current_agent),
) -> TicketOut:
    mark_missed_response_slas(db)
    ticket = get_ticket_or_404(db, ticket_id)
    return _ticket_out(ticket)


@router.patch(
    "/{ticket_id}/claim",
    response_model=TicketOut,
    summary="Claim ticket by current agent",
)
def claim(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    agent_id = current_agent.id
    db.rollback()
    ticket = claim_ticket(db, ticket_id=ticket_id, agent_id=agent_id)
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/claim",
    response_model=TicketOut,
    summary="Claim ticket by current agent",
)
def claim_post(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    agent_id = current_agent.id
    db.rollback()
    ticket = claim_ticket(db, ticket_id=ticket_id, agent_id=agent_id)
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketOut,
    summary="Update ticket status (Resolve, Close, Reopen, etc.)",
)
def patch_status(
    ticket_id: int,
    body: StatusPatchRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = change_status(
        db, ticket=ticket, new_status=body.status, agent_id=current_agent.id
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/reopen",
    response_model=TicketOut,
    summary="Demo-only agent reopen; reopens within 5 working days or creates a linked ticket",
)
def reopen(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    result_ticket, _ = reopen_ticket(db, ticket=ticket, agent_id=current_agent.id)
    out = _ticket_out(result_ticket)
    out.events = list(result_ticket.events)
    return out


@router.patch(
    "/{ticket_id}/priority",
    response_model=TicketOut,
    summary="Change ticket priority",
)
def patch_priority(
    ticket_id: int,
    body: PriorityPatchRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = change_priority(
        db,
        ticket=ticket,
        new_priority=body.priority,
        agent_id=current_agent.id,
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/reply",
    response_model=TicketOut,
    summary="Reply to customer",
)
def reply(
    ticket_id: int,
    body: ReplyRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = reply_to_customer(
        db, ticket=ticket, message=body.message, agent_id=current_agent.id
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/replies",
    response_model=TicketOut,
    summary="Reply to customer",
)
def replies(
    ticket_id: int,
    body: ReplyRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = reply_to_customer(db, ticket=ticket, message=body.message, agent_id=current_agent.id)
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/resolve",
    response_model=TicketOut,
)
def resolve_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = change_status(
        db, ticket=ticket, new_status=TicketStatus.RESOLVED, agent_id=current_agent.id
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/close",
    response_model=TicketOut,
)
def close_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = change_status(
        db, ticket=ticket, new_status=TicketStatus.CLOSED, agent_id=current_agent.id
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.get(
    "/{ticket_id}/timeline",
)
def timeline(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: Agent = Depends(get_current_agent),
):
    ticket = get_ticket_or_404(db, ticket_id)
    return [
        TicketEventOut.model_validate(event)
        for event in ticket.events
    ]


@router.post(
    "/{ticket_id}/customer-reply",
    response_model=TicketOut,
    summary="Simulate customer reply (demo-only)",
)
def customer_reply(
    ticket_id: int,
    body: Optional[CustomerReplyRequest] = None,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    msg = body.message if body and body.message else "Customer response (Demo simulation)"
    ticket = simulate_customer_reply(db, ticket=ticket, message=msg)
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/note",
    response_model=TicketOut,
    summary="Add internal note",
)
def add_note(
    ticket_id: int,
    body: InternalNoteRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = add_internal_note_service(
        db, ticket=ticket, note=body.note, agent_id=current_agent.id
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out


@router.post(
    "/{ticket_id}/internal-notes",
    response_model=TicketOut,
)
def add_internal_note_endpoint(
    ticket_id: int,
    body: InternalNoteRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
) -> TicketOut:
    ticket = _managed_ticket(ticket_id, db, current_agent)
    ticket = add_internal_note_service(
        db, ticket=ticket, note=body.note, agent_id=current_agent.id
    )
    out = _ticket_out(ticket)
    out.events = list(ticket.events)
    return out
