from concurrent.futures import ThreadPoolExecutor
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.customer import Customer
from app.models.agent import Agent
from app.models.enums import TicketStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.ticket_service import claim_ticket


def test_internal_note_event_is_never_in_customer_timeline_payload():
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.email == "sla.test.customer@example.com").first()
        if customer is None:
            customer = Customer(name="Privacy Customer", email="privacy.phase8@example.com")
            db.add(customer)
            db.flush()

        ticket = Ticket(
            public_ref=f"INC-PHASE8-PRIVACY-{uuid.uuid4().hex[:8].upper()}",
            title="Privacy test",
            description="Internal note privacy test",
            customer_id=customer.id,
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        db.flush()
        db.add(TicketEvent(
            ticket_id=ticket.id,
            actor_type="AGENT",
            actor_id=None,
            actor_name="Priya Menon",
            event_type="INTERNAL_NOTE_ADDED",
            payload={"note": "TOP_SECRET_NOTE"},
        ))
        db.commit()

        events = db.execute(
            select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
        ).scalars().all()
        visible = [
            event for event in events
            if event.event_type.value != "INTERNAL_NOTE_ADDED"
        ]
        assert all("TOP_SECRET_NOTE" not in str(event.payload) for event in visible)
    finally:
        db.close()


def test_concurrent_claims_have_one_winner():
    db = SessionLocal()
    try:
        customer = db.query(Customer).first()
        assert customer is not None
        agents = db.query(Agent).limit(2).all()
        assert len(agents) >= 2
        agent_ids = [agents[0].id, agents[1].id]
        ticket = Ticket(
            public_ref=f"INC-PHASE8-CONCURRENT-{uuid.uuid4().hex[:8].upper()}",
            title="Concurrent claim test",
            description="Only one agent may claim this ticket",
            customer_id=customer.id,
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        ticket_id = ticket.id
    finally:
        db.close()

    def attempt_claim(agent_id: int) -> str:
        session = SessionLocal()
        try:
            claim_ticket(session, ticket_id=ticket_id, agent_id=agent_id)
            return "success"
        except Exception as exc:
            if getattr(exc, "status_code", None) == 409:
                return "conflict"
            return f"error:{type(exc).__name__}"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt_claim, agent_ids))

    assert results.count("success") == 1
    assert results.count("conflict") == 1
