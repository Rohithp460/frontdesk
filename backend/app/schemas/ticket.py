from datetime import datetime
import re
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ActorType, EventType, TicketPriority, TicketStatus


# ---------------------------------------------------------------------------
# Shared sub-schemas (embedded in responses)
# ---------------------------------------------------------------------------

class CustomerBrief(BaseModel):
    id: int
    name: str
    email: str
    model_config = {"from_attributes": True}


class AgentBrief(BaseModel):
    id: int
    name: str
    email: str
    model_config = {"from_attributes": True}


class TicketEventOut(BaseModel):
    id: int
    ticket_id: int
    actor_type: ActorType
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    event_type: EventType
    payload: Optional[Any] = None
    occurred_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class TicketCreateRequest(BaseModel):
    customer_id: int = Field(gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=10_000)
    priority: TicketPriority = TicketPriority.MEDIUM
    assigned_agent_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("title", "description")
    @classmethod
    def validate_plain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be empty")
        if re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value):
            raise ValueError("HTML markup is not allowed")
        return value


class PriorityPatchRequest(BaseModel):
    priority: TicketPriority


class StatusPatchRequest(BaseModel):
    status: TicketStatus


class ReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        if re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value):
            raise ValueError("HTML markup is not allowed")
        return value


class InternalNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=10_000)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Note must not be empty")
        if re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value):
            raise ValueError("HTML markup is not allowed")
        return value


class CustomerReplyRequest(BaseModel):
    message: Optional[str] = Field(
        default="Customer responded with requested details.", max_length=10_000
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        if re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value):
            raise ValueError("HTML markup is not allowed")
        return value


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class TicketOut(BaseModel):
    id: int
    public_ref: str
    title: str
    description: Optional[str]
    priority: TicketPriority
    status: TicketStatus
    customer_id: int
    assigned_agent_id: Optional[int]
    first_response_at: Optional[datetime]
    resolved_at: Optional[datetime]
    closed_at: Optional[datetime]
    response_deadline: Optional[datetime]
    resolution_deadline: Optional[datetime]
    reopened_until: Optional[datetime] = None
    reopened_from_ticket_id: Optional[int] = None
    response_sla_met: Optional[bool] = None
    resolution_sla_met: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

    # Nested relations (populated lazily when present)
    customer: Optional[CustomerBrief] = None
    assigned_agent: Optional[AgentBrief] = None
    events: Optional[List[TicketEventOut]] = None

    model_config = {"from_attributes": True}


class TicketListItem(BaseModel):
    id: int
    public_ref: str
    title: str
    priority: TicketPriority
    status: TicketStatus
    customer_id: Optional[int] = None
    assigned_agent_id: Optional[int] = None
    customer_name: str
    assigned_agent_name: Optional[str] = None
    created_at: datetime
    response_deadline: Optional[datetime] = None
    resolution_deadline: Optional[datetime] = None
    first_response_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    is_response_late: bool = False
    is_resolution_late: bool = False
    is_waiting_on_customer: bool = False
    sla_state: str


class PaginatedTicketList(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[TicketListItem]


class CustomerTimelineEventOut(BaseModel):
    id: int
    ticket_id: int
    actor_type: ActorType
    event_type: EventType
    message: Optional[str] = None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class CustomerTicketOut(BaseModel):
    """Customer-facing view of a ticket: internal notes and staff notes are strictly excluded."""
    id: int
    public_ref: str
    title: str
    description: Optional[str]
    status: TicketStatus
    created_at: datetime
    timeline: List[CustomerTimelineEventOut] = []

    model_config = {"from_attributes": True}


class PaginatedTickets(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[TicketOut]
