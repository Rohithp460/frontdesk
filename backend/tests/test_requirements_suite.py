"""
Pytest suite covering the 9 business, SLA, and lifecycle requirements:

1. Two agents cannot claim the same ticket.
2. Internal notes never appear in customer-facing API responses.
3. Friday 18:00 critical ticket is not late on Sunday.
4. Customer waiting time is excluded from resolution SLA.
5. Priority change after first response recalculates resolution deadline.
6. Ticket auto-closes after 5 working days without customer reply.
7. Resolved ticket can be reopened within 5 working days.
8. After 5 working days, reopening creates a new ticket.
9. Every major action creates an immutable ticket event.
"""
from datetime import datetime, timedelta, timezone
import uuid
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.customer import Customer
from app.models.enums import ActorType, EventType, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.ticket_wait_period import TicketWaitPeriod
from app.services.sla_service import (
    add_working_minutes,
    calculate_resolution_deadline,
    calculate_response_deadline,
    is_working_moment,
    WORK_MINUTES_PER_DAY,
)
from app.services.ticket_service import (
    auto_close_inactive_tickets,
    change_priority,
    change_status,
    claim_ticket,
    create_ticket,
    get_customer_facing_ticket,
    reopen_ticket,
    reply_to_customer,
)


ADMIN_EMAIL = "admin@frontdesk.local"
ADMIN_PASSWORD = "Admin@1234"
ALICE_EMAIL = "alice@frontdesk.local"
ALICE_PASSWORD = "Agent@1234"
BOB_EMAIL = "bob@frontdesk.local"
BOB_PASSWORD = "Agent@1234"
KOLKATA = ZoneInfo("Asia/Kolkata")


def kolkata_utc(day: int, hour: int, minute: int = 0, *, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=KOLKATA).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


def unique_ref(prefix: str = "INC") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture(scope="module")
def admin_headers(client: TestClient) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def alice_headers(client: TestClient) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": ALICE_EMAIL, "password": ALICE_PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def bob_headers(client: TestClient) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": BOB_EMAIL, "password": BOB_PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def shared_customer_id() -> int:
    db = SessionLocal()
    try:
        c = db.query(Customer).filter(Customer.email == "sla.test.customer@example.com").first()
        if not c:
            c = Customer(name="SLA Customer", email="sla.test.customer@example.com")
            db.add(c)
            db.commit()
            db.refresh(c)
        return c.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Requirement 1: Two agents cannot claim the same ticket
# ---------------------------------------------------------------------------
def test_1_two_agents_cannot_claim_same_ticket(
    client: TestClient, alice_headers: dict, bob_headers: dict, shared_customer_id: int
):
    # Create ticket
    t = client.post(
        "/api/v1/tickets",
        json={"customer_id": shared_customer_id, "title": "Claim contention test", "description": "Claim contention test.", "priority": "MEDIUM"},
        headers=alice_headers,
    ).json()
    tid = t["id"]

    # Agent Alice claims ticket -> succeeds
    resp1 = client.patch(f"/api/v1/tickets/{tid}/claim", headers=alice_headers)
    assert resp1.status_code == 200
    assert resp1.json()["assigned_agent_id"] is not None

    # Agent Bob attempts to claim the already claimed ticket -> 409 Conflict
    resp2 = client.patch(f"/api/v1/tickets/{tid}/claim", headers=bob_headers)
    assert resp2.status_code == 409
    assert "already been claimed" in resp2.json()["detail"]


# ---------------------------------------------------------------------------
# Requirement 2: Internal notes never appear in customer-facing API responses
# ---------------------------------------------------------------------------
def test_2_internal_notes_never_appear_in_customer_facing_response(
    client: TestClient, alice_headers: dict, shared_customer_id: int
):
    # Create ticket
    t = client.post(
        "/api/v1/tickets",
        json={"customer_id": shared_customer_id, "title": "Internal note privacy", "description": "Internal note privacy test.", "priority": "MEDIUM"},
        headers=alice_headers,
    ).json()
    tid = t["id"]
    claim = client.patch(f"/api/v1/tickets/{tid}/claim", headers=alice_headers)
    assert claim.status_code == 200

    # Agent adds an internal note
    client.post(
        f"/api/v1/tickets/{tid}/note",
        json={"note": "SECRET_ARVO_INTERNAL_NOTE: Database credentials reset required."},
        headers=alice_headers,
    )

    # Agent adds a public customer reply
    client.post(
        f"/api/v1/tickets/{tid}/reply",
        json={"message": "PUBLIC_MESSAGE: We are looking into your request."},
        headers=alice_headers,
    )

    # Fetch customer-facing view
    cust_resp = client.get(
        f"/api/v1/tickets/customer-view/{tid}?customer_id={shared_customer_id}",
        headers=alice_headers,
    )
    assert cust_resp.status_code == 200
    data = cust_resp.json()

    # Verify internal note is completely absent
    content_str = str(data)
    assert "SECRET_ARVO_INTERNAL_NOTE" not in content_str
    assert "noted" not in [evt["event_type"] for evt in data["timeline"]]

    # Verify public reply is present
    assert any("PUBLIC_MESSAGE" in (evt.get("message") or "") for evt in data["timeline"])


# ---------------------------------------------------------------------------
# Requirement 3: Friday 18:00 critical ticket is not late on Sunday
# ---------------------------------------------------------------------------
def test_3_friday_1800_critical_ticket_not_late_on_sunday(shared_customer_id: int):
    # Friday 2026-11-27 at 18:00 (work ends at 18:30)
    friday_1800 = kolkata_utc(27, 18, 0)
    ticket = Ticket(
        id=101,
        public_ref="INC-TEST-01",
        title="Critical Friday Outage",
        customer_id=shared_customer_id,
        priority=TicketPriority.CRITICAL,
        status=TicketStatus.OPEN,
        created_at=friday_1800,
    )
    response_deadline = calculate_response_deadline(ticket)
    # 30 mins used Friday (18:00-18:30); 90 mins carry over to Monday morning (09:30 + 1.5h = 11:00)
    assert response_deadline == kolkata_utc(30, 11, 0)

    # Sunday 2026-11-29 at 14:00
    sunday_check = kolkata_utc(29, 14, 0)
    is_late_on_sunday = (sunday_check > response_deadline)
    assert not is_late_on_sunday, "Ticket must NOT be considered late on Sunday!"


# ---------------------------------------------------------------------------
# Requirement 4: Customer waiting time is excluded from resolution SLA
# ---------------------------------------------------------------------------
def test_4_customer_waiting_time_excluded_from_resolution_sla(shared_customer_id: int):
    # Created Tuesday 2026-11-24 at 10:00, Low priority (5 working days resolution SLA)
    created = kolkata_utc(24, 10, 0)
    ticket = Ticket(
        id=102,
        public_ref="INC-TEST-02",
        title="Resolution SLA wait test",
        customer_id=shared_customer_id,
        priority=TicketPriority.LOW,
        status=TicketStatus.OPEN,
        created_at=created,
    )

    base_resolution = calculate_resolution_deadline(ticket)
    # 5 working days from Tuesday 10:00 -> Tuesday next week 10:00
    assert base_resolution == kolkata_utc(1, 10, 0, month=12)

    # Customer waited for 2 full working days (Wednesday + Thursday = 2 * 540 mins)
    wp = TicketWaitPeriod(
        id=201,
        ticket_id=102,
        started_at=kolkata_utc(25, 9, 30),
        ended_at=kolkata_utc(26, 18, 30),
    )
    ticket.wait_periods = [wp]

    extended_resolution = calculate_resolution_deadline(ticket)
    # Must be shifted forward by exactly 2 working days -> Thursday next week 10:00
    assert extended_resolution == kolkata_utc(3, 10, 0, month=12)


# ---------------------------------------------------------------------------
# Requirement 5: Priority change after first response recalculates resolution deadline
# ---------------------------------------------------------------------------
def test_5_priority_change_after_first_response_recalculates_resolution_deadline(
    client: TestClient, alice_headers: dict, shared_customer_id: int
):
    # Create ticket as LOW priority (5 working days resolution)
    t = client.post(
        "/api/v1/tickets",
        json={"customer_id": shared_customer_id, "title": "Priority Escalation SLA", "description": "Priority escalation test.", "priority": "LOW"},
        headers=alice_headers,
    ).json()
    tid = t["id"]
    claim = client.patch(f"/api/v1/tickets/{tid}/claim", headers=alice_headers)
    assert claim.status_code == 200
    initial_res_deadline = datetime.fromisoformat(t["resolution_deadline"])

    # Agent provides first response
    client.post(
        f"/api/v1/tickets/{tid}/reply",
        json={"message": "First response sent."},
        headers=alice_headers,
    )

    # Now escalate priority to URGENT (1 working day resolution)
    patch_resp = client.patch(
        f"/api/v1/tickets/{tid}/priority",
        json={"priority": "CRITICAL"},
        headers=alice_headers,
    )
    assert patch_resp.status_code == 200
    updated_ticket = patch_resp.json()
    new_res_deadline = datetime.fromisoformat(updated_ticket["resolution_deadline"])

    # Resolution deadline must be recalculated to be significantly earlier
    assert new_res_deadline < initial_res_deadline


# ---------------------------------------------------------------------------
# Requirement 6: Ticket auto-closes after 5 working days without customer reply
# ---------------------------------------------------------------------------
def test_6_ticket_autocloses_after_5_working_days_without_customer_reply(
    client: TestClient, alice_headers: dict, shared_customer_id: int
):
    db = SessionLocal()
    try:
        # Create ticket and set to pending on Monday 2026-11-23 10:00
        start_time = datetime(2026, 11, 23, 10, 0)
        ticket = Ticket(
            public_ref=unique_ref("INC-AC"),
            title="Auto close test",
            customer_id=shared_customer_id,
            priority=TicketPriority.medium,
            status=TicketStatus.pending,
            created_at=start_time,
            updated_at=start_time,
        )
        db.add(ticket)
        db.flush()

        # Start wait period
        wp = TicketWaitPeriod(ticket_id=ticket.id, started_at=start_time)
        db.add(wp)
        db.commit()

        # At 3 working days (Thursday 10:00): should NOT close
        time_at_3_days = datetime(2026, 11, 26, 10, 0)
        closed_3d = auto_close_inactive_tickets(db, current_time=time_at_3_days)
        assert ticket.id not in [t.id for t in closed_3d]

        # At exactly 5 working days (Monday next week 2026-11-30 10:00): should AUTO-CLOSE
        time_at_5_days = datetime(2026, 11, 30, 10, 0)
        closed_5d = auto_close_inactive_tickets(db, current_time=time_at_5_days)
        assert ticket.id in [t.id for t in closed_5d]

        db.refresh(ticket)
        assert ticket.status == TicketStatus.closed
        assert ticket.closed_at == time_at_5_days
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Requirement 7: Resolved ticket can be reopened within 5 working days
# ---------------------------------------------------------------------------
def test_7_resolved_ticket_reopened_within_5_working_days(
    client: TestClient, alice_headers: dict, shared_customer_id: int
):
    db = SessionLocal()
    try:
        resolved_time = datetime(2026, 11, 23, 11, 0)  # Monday
        ticket = Ticket(
            public_ref=unique_ref("INC-RO7"),
            title="Reopen within window",
            customer_id=shared_customer_id,
            priority=TicketPriority.medium,
            status=TicketStatus.resolved,
            resolved_at=resolved_time,
            reopened_until=add_working_minutes(resolved_time, 5 * WORK_MINUTES_PER_DAY, db=db),
            created_at=resolved_time - timedelta(hours=2),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        # Reopen on Thursday (3 working days later -> within 5 working days window)
        reopen_time = datetime(2026, 11, 26, 11, 0)
        result_ticket, is_new = reopen_ticket(
            db, ticket=ticket, agent_id=1, current_time=reopen_time
        )

        assert not is_new, "Should reopen existing ticket directly"
        assert result_ticket.id == ticket.id
        assert result_ticket.status == TicketStatus.reopened
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Requirement 8: After 5 working days, reopening creates a new ticket
# ---------------------------------------------------------------------------
def test_8_reopening_after_5_working_days_creates_new_ticket(
    client: TestClient, alice_headers: dict, shared_customer_id: int
):
    db = SessionLocal()
    try:
        resolved_time = datetime(2026, 11, 23, 11, 0)  # Monday
        ticket = Ticket(
            public_ref=unique_ref("INC-RO8"),
            title="Reopen expired window",
            description="Original description",
            customer_id=shared_customer_id,
            priority=TicketPriority.medium,
            status=TicketStatus.resolved,
            resolved_at=resolved_time,
            reopened_until=add_working_minutes(resolved_time, 5 * WORK_MINUTES_PER_DAY, db=db),
            created_at=resolved_time - timedelta(hours=2),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        # Attempt reopen 7 working days later (Wednesday next week)
        reopen_time = datetime(2026, 12, 2, 11, 0)
        result_ticket, is_new = reopen_ticket(
            db, ticket=ticket, agent_id=1, current_time=reopen_time
        )

        assert is_new, "Must create a new ticket when reopened after 5 working days!"
        assert result_ticket.id != ticket.id
        assert result_ticket.public_ref != ticket.public_ref
        assert result_ticket.title == f"Re: {ticket.title}"
        assert result_ticket.status == TicketStatus.new
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Requirement 9: Every major action creates an immutable ticket event
# ---------------------------------------------------------------------------
def test_9_every_major_action_creates_immutable_ticket_event(
    client: TestClient, alice_headers: dict, shared_customer_id: int
):
    db = SessionLocal()
    try:
        # 1. Action: CREATE
        t = client.post(
            "/api/v1/tickets",
            json={"customer_id": shared_customer_id, "title": "Immutable audit test", "description": "Immutable audit test.", "priority": "LOW"},
            headers=alice_headers,
        ).json()
        tid = t["id"]

        # 2. Action: CLAIM
        claim = client.patch(f"/api/v1/tickets/{tid}/claim", headers=alice_headers)
        assert claim.status_code == 200

        # 3. Action: REPLY TO CUSTOMER
        client.post(f"/api/v1/tickets/{tid}/reply", json={"message": "First response."}, headers=alice_headers)

        # 4. Action: SIMULATE CUSTOMER REPLY
        client.post(f"/api/v1/tickets/{tid}/customer-reply", json={"message": "Customer replies."}, headers=alice_headers)

        # 5. Action: INTERNAL NOTE
        client.post(f"/api/v1/tickets/{tid}/note", json={"note": "Internal investigation note."}, headers=alice_headers)

        # 6. Action: CHANGE PRIORITY
        client.patch(f"/api/v1/tickets/{tid}/priority", json={"priority": "urgent"}, headers=alice_headers)

        # 7. Action: RESOLVE
        client.patch(f"/api/v1/tickets/{tid}/status", json={"status": "resolved"}, headers=alice_headers)

        # Query all events in DB
        events = db.execute(
            select(TicketEvent).where(TicketEvent.ticket_id == tid).order_by(TicketEvent.id.asc())
        ).scalars().all()

        event_types = [e.event_type for e in events]

        # Verify all major actions were captured as events
        assert EventType.TICKET_CREATED in event_types
        assert EventType.TICKET_ASSIGNED in event_types
        assert EventType.AGENT_REPLY in event_types
        assert EventType.INTERNAL_NOTE_ADDED in event_types
        assert EventType.PRIORITY_CHANGED in event_types
        assert EventType.TICKET_RESOLVED in event_types

        # Verify immutability constraints: rows have IDs and timestamps, no updated_at column
        for e in events:
            assert e.id is not None
            assert e.occurred_at is not None
            assert not hasattr(e, "updated_at"), "TicketEvent must have no updated_at column (append-only)"
    finally:
        db.close()
