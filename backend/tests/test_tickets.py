"""
Ticket API tests: POST /tickets, GET /tickets, GET /tickets/{id},
PATCH /tickets/{id}/priority
"""
import pytest
from fastapi.testclient import TestClient


ADMIN_EMAIL = "admin@frontdesk.local"
ADMIN_PASSWORD = "Admin@1234"
AGENT_EMAIL = "alice@frontdesk.local"
AGENT_PASSWORD = "Agent@1234"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def alice_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": AGENT_EMAIL, "password": AGENT_PASSWORD},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def alice_headers(alice_token: str) -> dict:
    return {"Authorization": f"Bearer {alice_token}"}


@pytest.fixture(scope="module")
def customer_id(client: TestClient, admin_headers: dict) -> int:
    """Create a customer directly via DB (no customer API yet), or reuse existing."""
    from app.db.session import SessionLocal
    from app.models.customer import Customer

    db = SessionLocal()
    try:
        c = db.query(Customer).filter(Customer.email == "test.customer@example.com").first()
        if not c:
            c = Customer(name="Test Customer", email="test.customer@example.com")
            db.add(c)
            db.commit()
            db.refresh(c)
        return c.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_tickets_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/tickets").status_code in (401, 403)
    assert client.post("/api/v1/tickets", json={}).status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /tickets — create
# ---------------------------------------------------------------------------

def test_create_ticket_minimal(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    resp = client.post(
        "/api/v1/tickets",
        json={
            "customer_id": customer_id,
            "title": "Login page broken",
            "description": "Users cannot log in after the update.",
            "priority": "MEDIUM",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["public_ref"].startswith("INC-")
    assert data["priority"] == "MEDIUM"
    assert data["status"] == "OPEN"
    assert data["customer_id"] == customer_id
    assert data["assigned_agent_id"] is None


def test_create_ticket_bad_customer(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.post(
        "/api/v1/tickets",
        json={
            "customer_id": 999999,
            "title": "Should fail",
            "description": "A valid description for the missing customer.",
            "priority": "LOW",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_create_ticket_missing_title(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    resp = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "priority": "medium"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_public_ref_increments(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    def make():
        return client.post(
            "/api/v1/tickets",
            json={"customer_id": customer_id, "title": "Ref test", "description": "Reference test.", "priority": "LOW"},
            headers=admin_headers,
        ).json()["public_ref"]

    r1, r2 = make(), make()
    n1 = int(r1.split("-")[1])
    n2 = int(r2.split("-")[1])
    assert n2 == n1 + 1


# ---------------------------------------------------------------------------
# GET /tickets — list + filters
# ---------------------------------------------------------------------------

def test_list_tickets_returns_items(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.get("/api/v1/tickets", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


def test_list_filter_by_status(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.get("/api/v1/tickets?status=OPEN", headers=admin_headers)
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["status"] == "OPEN"


def test_list_filter_by_priority(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.get("/api/v1/tickets?priority=MEDIUM", headers=admin_headers)
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["priority"] == "MEDIUM"


def test_list_filter_unassigned(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.get("/api/v1/tickets?unassigned=true", headers=admin_headers)
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["assigned_agent_id"] is None


def test_list_filter_assigned_to_me(
    client: TestClient, alice_headers: dict, admin_headers: dict, customer_id: int
) -> None:
    # get alice's agent id
    alice_id = client.get("/api/v1/auth/me", headers=alice_headers).json()["id"]

    # create ticket assigned to alice
    client.post(
        "/api/v1/tickets",
        json={
            "customer_id": customer_id,
            "title": "Assigned to alice",
            "description": "Assigned-agent listing test.",
            "priority": "MEDIUM",
            "assigned_agent_id": alice_id,
        },
        headers=admin_headers,
    )

    resp = client.get("/api/v1/tickets?assigned_to_me=true", headers=alice_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["assigned_agent_id"] == alice_id


def test_list_pagination(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.get("/api/v1/tickets?skip=0&limit=2", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2


# ---------------------------------------------------------------------------
# GET /tickets/{id}
# ---------------------------------------------------------------------------

def test_get_ticket_by_id(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    created = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Get by ID", "description": "Get by ID test.", "priority": "CRITICAL"},
        headers=admin_headers,
    ).json()

    resp = client.get(f"/api/v1/tickets/{created['id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["public_ref"] == created["public_ref"]


def test_get_ticket_not_found(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.get("/api/v1/tickets/999999", headers=admin_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /tickets/{id}/priority
# ---------------------------------------------------------------------------

def test_patch_priority(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    ticket = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Priority patch test", "description": "Priority test.", "priority": "LOW"},
        headers=admin_headers,
    ).json()

    resp = client.patch(
        f"/api/v1/tickets/{ticket['id']}/priority",
        json={"priority": "CRITICAL"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["priority"] == "CRITICAL"


def test_patch_priority_idempotent(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    """Patching to the same priority should succeed and not change anything."""
    ticket = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Idempotent priority", "description": "Idempotent priority test.", "priority": "MEDIUM"},
        headers=admin_headers,
    ).json()

    resp = client.patch(
        f"/api/v1/tickets/{ticket['id']}/priority",
        json={"priority": "MEDIUM"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["priority"] == "MEDIUM"


def test_patch_priority_invalid_value(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    ticket = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Bad priority", "description": "Invalid priority test.", "priority": "LOW"},
        headers=admin_headers,
    ).json()

    resp = client.patch(
        f"/api/v1/tickets/{ticket['id']}/priority",
        json={"priority": "NOT_A_PRIORITY"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_patch_priority_not_found(
    client: TestClient, admin_headers: dict
) -> None:
    resp = client.patch(
        "/api/v1/tickets/999999/priority",
        json={"priority": "MEDIUM"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Ticket events are created
# ---------------------------------------------------------------------------

def test_ticket_event_created_on_create(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    from app.db.session import SessionLocal
    from app.models.ticket_event import TicketEvent
    from app.models.enums import EventType

    ticket = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Event audit test", "description": "Audit test.", "priority": "MEDIUM"},
        headers=admin_headers,
    ).json()

    db = SessionLocal()
    try:
        events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket["id"]).all()
        assert any(event.event_type == EventType.TICKET_CREATED for event in events)
    finally:
        db.close()


def test_ticket_event_created_on_priority_change(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    from app.db.session import SessionLocal
    from app.models.ticket_event import TicketEvent
    from app.models.enums import EventType

    ticket = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Priority event test", "description": "Priority event test.", "priority": "LOW"},
        headers=admin_headers,
    ).json()

    client.patch(
        f"/api/v1/tickets/{ticket['id']}/priority",
        json={"priority": "MEDIUM"},
        headers=admin_headers,
    )

    db = SessionLocal()
    try:
        events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket["id"]).all()
        types = [e.event_type for e in events]
        assert EventType.TICKET_CREATED in types
        assert EventType.PRIORITY_CHANGED in types

        pc = next(e for e in events if e.event_type == EventType.PRIORITY_CHANGED)
        assert pc.payload["from"] == "LOW"
        assert pc.payload["to"] == "MEDIUM"
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Demo: POST /tickets/{id}/customer-reply
# ---------------------------------------------------------------------------

def test_simulate_customer_reply(
    client: TestClient, admin_headers: dict, customer_id: int
) -> None:
    # 1. Create a ticket
    ticket = client.post(
        "/api/v1/tickets",
        json={"customer_id": customer_id, "title": "Customer reply simulation test", "description": "Customer reply test.", "priority": "MEDIUM"},
        headers=admin_headers,
    ).json()

    # 2. Agent replies -> enters pending state and starts wait period
    client.post(
        f"/api/v1/tickets/{ticket['id']}/reply",
        json={"message": "Please send the error screenshot."},
        headers=admin_headers,
    )

    t_pending = client.get(f"/api/v1/tickets/{ticket['id']}", headers=admin_headers).json()
    assert t_pending["status"] == "WAITING_CUSTOMER"

    # 3. Simulate customer reply
    resp = client.post(
        f"/api/v1/tickets/{ticket['id']}/customer-reply",
        json={"message": "Here is the screenshot attached."},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] == "OPEN"

    # Check events
    types = [e["event_type"] for e in updated["events"]]
    actors = [e["actor_type"] for e in updated["events"]]
    assert "AGENT_REPLY" in types
    assert "CUSTOMER" in actors

    # Verify wait period ended in DB
    from app.db.session import SessionLocal
    from app.models.ticket_wait_period import TicketWaitPeriod
    db = SessionLocal()
    try:
        wps = db.query(TicketWaitPeriod).filter(TicketWaitPeriod.ticket_id == ticket["id"]).all()
        assert len(wps) >= 1
        for wp in wps:
            assert wp.ended_at is not None
    finally:
        db.close()
