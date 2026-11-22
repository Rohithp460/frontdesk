from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.main import app
from app.models.agent import Agent
from app.models.customer import Customer
from app.models.enums import EventType, TicketStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.ticket_wait_period import TicketWaitPeriod
from app.schemas.ticket import InternalNoteRequest, ReplyRequest, TicketCreateRequest
from app.services.ticket_service import auto_close_inactive_tickets


ADMIN = ("meera@arvo.example", "Admin@1234")
AGENT_A = ("priya@arvo.example", "Agent@1234")
AGENT_B = ("arjun@arvo.example", "Agent@1234")


def _headers(client: TestClient, credentials: tuple[str, str]) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": credentials[0], "password": credentials[1]},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _customer_id() -> int:
    db = SessionLocal()
    try:
        customer = Customer(
            name="Hardening Customer",
            email=f"hardening-{uuid.uuid4().hex}@example.test",
        )
        db.add(customer)
        db.commit()
        return customer.id
    finally:
        db.close()


def _create_ticket(
    client: TestClient, headers: dict[str, str], *, assigned_agent_id: Optional[int] = None
) -> dict:
    payload = {
        "customer_id": _customer_id(),
        "title": f"Regression {uuid.uuid4().hex[:8]}",
        "description": "Reproducible hardening test",
        "priority": "MEDIUM",
    }
    if assigned_agent_id is not None:
        payload["assigned_agent_id"] = assigned_agent_id
    response = client.post("/api/v1/tickets", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_http_concurrent_ticket_creation_generates_unique_references():
    with TestClient(app) as login_client:
        headers = _headers(login_client, ADMIN)

    def create_one(_: int) -> dict:
        with TestClient(app) as request_client:
            response = request_client.post(
                "/api/v1/tickets",
                json={
                    "customer_id": _customer_id(),
                    "title": f"Concurrent {uuid.uuid4().hex[:8]}",
                    "description": "Concurrent ticket reference test",
                    "priority": "LOW",
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text
            return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        tickets = list(pool.map(create_one, range(2)))
    assert len({ticket["public_ref"] for ticket in tickets}) == 2


def test_http_concurrent_claim_has_one_winner_and_one_conflict():
    with TestClient(app) as client:
        agent_a = _headers(client, AGENT_A)
        agent_b = _headers(client, AGENT_B)
        ticket = _create_ticket(client, agent_a)

    def claim(headers: dict[str, str]) -> int:
        with TestClient(app) as client:
            return client.post(
                f"/api/v1/tickets/{ticket['id']}/claim", headers=headers
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (agent_a, agent_b)))
    assert sorted(results) == [200, 409]


def test_claim_audit_records_claiming_agent():
    with TestClient(app) as client:
        headers = _headers(client, AGENT_A)
        ticket = _create_ticket(client, headers)
        response = client.post(
            f"/api/v1/tickets/{ticket['id']}/claim", headers=headers
        )
        assert response.status_code == 200

    db = SessionLocal()
    try:
        assigned_event = db.execute(
            select(TicketEvent).where(
                TicketEvent.ticket_id == ticket["id"],
                TicketEvent.event_type == EventType.TICKET_ASSIGNED,
            )
        ).scalar_one()
        agent = db.execute(select(Agent).where(Agent.email == AGENT_A[0])).scalar_one()
        assert assigned_event.actor_id == agent.id
        assert assigned_event.actor_name == agent.name
    finally:
        db.close()


def test_cross_agent_mutation_is_forbidden_but_admin_can_manage():
    with TestClient(app) as client:
        agent_a = _headers(client, AGENT_A)
        agent_b = _headers(client, AGENT_B)
        admin = _headers(client, ADMIN)
        ticket = _create_ticket(client, agent_a)
        assert client.get(
            f"/api/v1/tickets/{ticket['id']}", headers=agent_b
        ).status_code == 200
        assert client.post(
            f"/api/v1/tickets/{ticket['id']}/claim", headers=agent_a
        ).status_code == 200
        assert client.post(
            f"/api/v1/tickets/{ticket['id']}/resolve", headers=agent_b
        ).status_code == 403
        assert client.post(
            f"/api/v1/tickets/{ticket['id']}/resolve", headers=admin
        ).status_code == 200


def test_admin_maintenance_endpoints_require_admin(client: TestClient):
    agent = _headers(client, AGENT_A)
    admin = _headers(client, ADMIN)
    assert client.post("/api/v1/admin/sla-check", headers=agent).status_code == 403
    assert client.post("/api/v1/admin/auto-close-check", headers=agent).status_code == 403
    assert client.post("/api/v1/admin/sla-check", headers=admin).status_code == 200


@pytest.mark.parametrize("terminal_action", ["resolve", "close"])
def test_wait_period_ends_before_resolve_or_close(client: TestClient, terminal_action: str):
    agent = _headers(client, AGENT_A)
    ticket = _create_ticket(client, agent)
    ticket_id = ticket["id"]
    assert client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=agent).status_code == 200
    assert client.post(
        f"/api/v1/tickets/{ticket_id}/reply",
        json={"message": "Please review these details."},
        headers=agent,
    ).status_code == 200
    assert client.post(
        f"/api/v1/tickets/{ticket_id}/reply",
        json={"message": "One more customer-visible update."},
        headers=agent,
    ).status_code == 200
    db = SessionLocal()
    try:
        active_before_transition = db.execute(
            select(TicketWaitPeriod).where(
                TicketWaitPeriod.ticket_id == ticket_id,
                TicketWaitPeriod.ended_at.is_(None),
            )
        ).scalars().all()
        assert len(active_before_transition) == 1
    finally:
        db.close()
    response = client.post(
        f"/api/v1/tickets/{ticket_id}/{terminal_action}", headers=agent
    )
    assert response.status_code == 200

    db = SessionLocal()
    try:
        active = db.execute(
            select(TicketWaitPeriod).where(
                TicketWaitPeriod.ticket_id == ticket_id,
                TicketWaitPeriod.ended_at.is_(None),
            )
        ).scalars().all()
        assert active == []
        assert any(
            event["event_type"] == EventType.SLA_DEADLINE_RECALCULATED.value
            for event in response.json()["events"]
        )
    finally:
        db.close()


def test_customer_reply_ends_wait_and_returns_ticket_to_open(client: TestClient):
    headers = _headers(client, AGENT_A)
    ticket = _create_ticket(client, headers)
    ticket_id = ticket["id"]
    client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=headers)
    assert client.post(
        f"/api/v1/tickets/{ticket_id}/reply",
        json={"message": "Waiting for customer."},
        headers=headers,
    ).status_code == 200
    response = client.post(
        f"/api/v1/tickets/{ticket_id}/customer-reply",
        json={"message": "Customer sent details."},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "OPEN"
    assert any(
        event["event_type"] == EventType.SLA_DEADLINE_RECALCULATED.value
        for event in response.json()["events"]
    )
    db = SessionLocal()
    try:
        active = db.execute(
            select(TicketWaitPeriod).where(
                TicketWaitPeriod.ticket_id == ticket_id,
                TicketWaitPeriod.ended_at.is_(None),
            )
        ).scalars().all()
        assert not active
    finally:
        db.close()


def test_repeated_resolve_and_close_return_409_without_duplicate_events(client: TestClient):
    agent = _headers(client, AGENT_A)
    resolved_ticket = _create_ticket(client, agent)
    closed_ticket = _create_ticket(client, agent)
    resolved_id, closed_id = resolved_ticket["id"], closed_ticket["id"]
    client.post(f"/api/v1/tickets/{resolved_id}/claim", headers=agent)
    client.post(f"/api/v1/tickets/{closed_id}/claim", headers=agent)
    assert client.post(f"/api/v1/tickets/{resolved_id}/resolve", headers=agent).status_code == 200
    assert client.post(f"/api/v1/tickets/{resolved_id}/resolve", headers=agent).status_code == 409
    assert client.post(f"/api/v1/tickets/{closed_id}/close", headers=agent).status_code == 200
    assert client.post(f"/api/v1/tickets/{closed_id}/close", headers=agent).status_code == 409

    db = SessionLocal()
    try:
        events = db.execute(
            select(TicketEvent).where(
                TicketEvent.ticket_id.in_([resolved_id, closed_id])
            )
        ).scalars().all()
        assert sum(event.event_type == EventType.TICKET_RESOLVED for event in events) == 1
        assert sum(event.event_type == EventType.TICKET_CLOSED for event in events) == 1
    finally:
        db.close()


def test_customer_reply_reopens_within_window_and_after_window_creates_linked_ticket(client: TestClient):
    agent = _headers(client, AGENT_A)
    ticket = _create_ticket(client, agent)
    ticket_id = ticket["id"]
    client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=agent)
    assert client.post(f"/api/v1/tickets/{ticket_id}/resolve", headers=agent).status_code == 200

    reopened = client.post(
        f"/api/v1/tickets/{ticket_id}/customer-reply",
        json={"message": "Customer replied in the window."},
        headers=agent,
    )
    assert reopened.status_code == 200
    assert reopened.json()["id"] == ticket_id
    assert reopened.json()["status"] == "OPEN"

    assert client.post(f"/api/v1/tickets/{ticket_id}/resolve", headers=agent).status_code == 200
    db = SessionLocal()
    try:
        original = db.get(Ticket, ticket_id)
        original.reopened_until = datetime.now(timezone.utc).replace(tzinfo=None)
        original.reopened_until = original.reopened_until.replace(year=original.reopened_until.year - 1)
        db.commit()
    finally:
        db.close()
    followup = client.post(
        f"/api/v1/tickets/{ticket_id}/customer-reply",
        json={"message": "Customer replied after the reopen window."},
        headers=agent,
    )
    assert followup.status_code == 200
    assert followup.json()["id"] != ticket_id
    assert followup.json()["reopened_from_ticket_id"] == ticket_id


def test_customer_reply_to_closed_ticket_creates_linked_ticket(client: TestClient):
    headers = _headers(client, AGENT_A)
    ticket = _create_ticket(client, headers)
    ticket_id = ticket["id"]
    client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=headers)
    assert client.post(f"/api/v1/tickets/{ticket_id}/close", headers=headers).status_code == 200
    response = client.post(
        f"/api/v1/tickets/{ticket_id}/customer-reply",
        json={"message": "Reply to a closed ticket."},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["id"] != ticket_id
    assert response.json()["reopened_from_ticket_id"] == ticket_id


def test_agent_demo_reopen_records_agent_actor(client: TestClient):
    headers = _headers(client, AGENT_A)
    ticket = _create_ticket(client, headers)
    ticket_id = ticket["id"]
    client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=headers)
    assert client.post(f"/api/v1/tickets/{ticket_id}/resolve", headers=headers).status_code == 200
    reopened = client.post(f"/api/v1/tickets/{ticket_id}/reopen", headers=headers)
    assert reopened.status_code == 200

    db = SessionLocal()
    try:
        event = db.execute(
            select(TicketEvent).where(
                TicketEvent.ticket_id == ticket_id,
                TicketEvent.event_type == EventType.TICKET_REOPENED,
            )
        ).scalar_one()
        assert event.actor_type.value == "AGENT"
    finally:
        db.close()


def test_agent_demo_reopen_after_window_returns_linked_new_ticket(client: TestClient):
    headers = _headers(client, AGENT_A)
    ticket = _create_ticket(client, headers)
    ticket_id = ticket["id"]
    client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=headers)
    assert client.post(f"/api/v1/tickets/{ticket_id}/resolve", headers=headers).status_code == 200
    db = SessionLocal()
    try:
        original = db.get(Ticket, ticket_id)
        original.reopened_until = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    followup = client.post(f"/api/v1/tickets/{ticket_id}/reopen", headers=headers)
    assert followup.status_code == 200, followup.text
    assert followup.json()["id"] != ticket_id
    assert followup.json()["reopened_from_ticket_id"] == ticket_id


def test_auto_close_threshold_uses_working_time_and_system_actor():
    db = SessionLocal()
    ticket_id = None
    try:
        ticket = Ticket(
            public_ref=f"INC-AUTO-{uuid.uuid4().hex[:8].upper()}",
            title="Auto close threshold",
            description="Wait threshold test",
            customer_id=_customer_id(),
            status=TicketStatus.WAITING_CUSTOMER,
            created_at=datetime(2026, 11, 23, 4, 0),  # Monday 09:30 IST
            updated_at=datetime(2026, 11, 23, 4, 0),
        )
        db.add(ticket)
        db.flush()
        ticket_id = ticket.id
        db.add(
            TicketWaitPeriod(
                ticket_id=ticket.id,
                started_at=datetime(2026, 11, 23, 4, 0),
            )
        )
        db.commit()

        before_threshold = auto_close_inactive_tickets(
            db, current_time=datetime(2026, 11, 27, 12, 59)
        )
        assert ticket_id not in [item.id for item in before_threshold]
        at_threshold = auto_close_inactive_tickets(
            db, current_time=datetime(2026, 11, 27, 13, 0)
        )
        assert ticket_id in [item.id for item in at_threshold]
        db.refresh(ticket)
        assert ticket.status == TicketStatus.CLOSED
        event = db.execute(
            select(TicketEvent).where(
                TicketEvent.ticket_id == ticket_id,
                TicketEvent.event_type == EventType.AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY,
            )
        ).scalar_one()
        assert event.actor_type.value == "SYSTEM"
    finally:
        db.close()


def test_missed_response_sla_is_persisted_after_deadline(client: TestClient):
    headers = _headers(client, AGENT_A)
    ticket = _create_ticket(client, headers)
    db = SessionLocal()
    try:
        stored = db.get(Ticket, ticket["id"])
        stored.response_deadline = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/tickets/{ticket['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["response_sla_met"] is False


def test_timeline_order_is_deterministic_for_equal_timestamps(client: TestClient):
    headers = _headers(client, AGENT_A)
    ticket = _create_ticket(client, headers)
    db = SessionLocal()
    try:
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
        first = TicketEvent(
            ticket_id=ticket["id"],
            actor_type="SYSTEM",
            event_type="STATUS_CHANGED",
            payload={"order": 1},
            occurred_at=timestamp,
        )
        second = TicketEvent(
            ticket_id=ticket["id"],
            actor_type="SYSTEM",
            event_type="STATUS_CHANGED",
            payload={"order": 2},
            occurred_at=timestamp,
        )
        db.add_all([first, second])
        db.commit()
        ids = [first.id, second.id]
    finally:
        db.close()

    timeline = client.get(f"/api/v1/tickets/{ticket['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    ordered_ids = [item["id"] for item in timeline.json()]
    assert ordered_ids.index(ids[0]) < ordered_ids.index(ids[1])


def test_duplicate_customer_email_and_invalid_ticket_ids_are_rejected(client: TestClient):
    email = f"duplicate-{uuid.uuid4().hex}@example.test"
    db = SessionLocal()
    try:
        db.add(Customer(name="First", email=email))
        db.commit()
        db.add(Customer(name="Second", email=email))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()

    headers = _headers(client, AGENT_A)
    assert client.get("/api/v1/tickets/0", headers=headers).status_code == 404
    invalid = client.post(
        "/api/v1/tickets",
        json={"customer_id": -1, "title": "Invalid", "description": "Bad id"},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_ticket_search_treats_sql_syntax_as_plain_text(client: TestClient):
    headers = _headers(client, AGENT_A)
    response = client.get(
        "/api/v1/tickets",
        params={"search": "%' OR 1=1 --"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_event_rows_are_immutable_and_ticket_deletion_is_restricted(client: TestClient):
    agent = _headers(client, AGENT_A)
    ticket = _create_ticket(client, agent)
    db = SessionLocal()
    try:
        event = db.execute(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket["id"])
            .order_by(TicketEvent.id)
        ).scalars().first()
        event.payload = {"tampered": True}
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()

        with pytest.raises(ValueError, match="cannot be deleted"):
            db.delete(event)
            db.flush()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(delete(Ticket).where(Ticket.id == ticket["id"]))
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_ticket_text_validation_and_unicode_round_trip(client: TestClient):
    assert TicketCreateRequest(
        customer_id=1,
        title="  支援依頼 😊  ",
        description="  नमस्ते — नमस्कार 👋  ",
    ).title == "支援依頼 😊"
    with pytest.raises(ValueError):
        TicketCreateRequest(customer_id=1, title="XSS", description="<script>alert(1)</script>")
    with pytest.raises(ValueError):
        TicketCreateRequest(customer_id=1, title="Empty", description="  ")
    with pytest.raises(ValueError):
        TicketCreateRequest(customer_id=1, title="T" * 256, description="Details")
    with pytest.raises(ValueError):
        TicketCreateRequest(customer_id=1, title="Title", description="D" * 10_001)
    with pytest.raises(ValueError):
        ReplyRequest(message="x" * 10_001)
    with pytest.raises(ValueError):
        InternalNoteRequest(note="<img src=x onerror=alert(1)>")

    headers = _headers(client, AGENT_A)
    response = client.post(
        "/api/v1/tickets",
        json={
            "customer_id": _customer_id(),
            "title": "支援依頼 😊",
            "description": "नमस्ते — नमस्कार 👋",
            "priority": "LOW",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "支援依頼 😊"
    assert response.json()["description"] == "नमस्ते — नमस्कार 👋"
