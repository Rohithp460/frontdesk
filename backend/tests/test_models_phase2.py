from app.models.agent import Agent
from app.models.business_calendar import BusinessCalendar
from app.models.customer import Customer
from app.models.enums import (
    ActorType,
    AgentRole,
    EventType,
    TicketPriority,
    TicketStatus,
)
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.ticket_wait_period import TicketWaitPeriod


def test_required_database_enums():
    assert {member.value for member in TicketPriority} == {"CRITICAL", "MEDIUM", "LOW"}
    assert {member.value for member in TicketStatus} == {
        "OPEN",
        "WAITING_CUSTOMER",
        "RESOLVED",
        "CLOSED",
    }
    assert {member.value for member in AgentRole} == {"AGENT", "ADMIN"}
    assert {member.value for member in ActorType} == {"AGENT", "SYSTEM", "CUSTOMER"}


def test_required_event_types():
    assert {member.value for member in EventType} == {
        "TICKET_CREATED",
        "TICKET_ASSIGNED",
        "AGENT_REPLY",
        "INTERNAL_NOTE_ADDED",
        "CUSTOMER_REPLY",
        "STATUS_CHANGED",
        "PRIORITY_CHANGED",
        "TICKET_RESOLVED",
        "TICKET_CLOSED",
        "TICKET_REOPENED",
        "NEW_TICKET_CREATED_FROM_CLOSED_TICKET",
        "AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY",
        "SLA_DEADLINE_RECALCULATED",
    }


def test_phase2_tables_and_required_columns():
    assert Agent.__table__.name == "agents"
    assert "is_active" in Agent.__table__.columns
    assert "updated_at" in Agent.__table__.columns

    assert Customer.__table__.name == "customers"
    assert Ticket.__table__.name == "tickets"
    for column in (
        "public_ref",
        "title",
        "description",
        "customer_id",
        "assigned_agent_id",
        "priority",
        "status",
        "response_deadline",
        "resolution_deadline",
        "response_sla_met",
        "resolution_sla_met",
        "reopened_from_ticket_id",
    ):
        assert column in Ticket.__table__.columns

    assert TicketEvent.__table__.name == "ticket_events"
    assert "actor_name" in TicketEvent.__table__.columns
    assert "occurred_at" in TicketEvent.__table__.columns
    assert "created_at" in TicketEvent.__table__.columns
    assert "updated_at" not in TicketEvent.__table__.columns

    assert BusinessCalendar.__table__.name == "business_calendar"
    assert "date" in BusinessCalendar.__table__.primary_key.columns

    assert TicketWaitPeriod.__table__.name == "ticket_wait_periods"
    assert "created_at" in TicketWaitPeriod.__table__.columns
