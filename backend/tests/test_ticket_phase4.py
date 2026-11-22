from app.schemas.ticket import TicketCreateRequest
from app.models.enums import TicketPriority, TicketStatus
from app.main import app


def test_root_and_versioned_ticket_routes_exist():
    paths = {route.path for route in app.routes}
    assert "/tickets" in paths
    assert "/tickets/{ticket_id}" in paths
    assert "/api/v1/tickets" in paths
    assert "/api/v1/tickets/{ticket_id}" in paths


def test_ticket_create_schema_requires_description_and_enforces_title_limit():
    try:
        TicketCreateRequest(customer_id=1, title="A", priority=TicketPriority.MEDIUM)
        assert False, "description should be required"
    except Exception:
        pass

    try:
        TicketCreateRequest(customer_id=1, title="x" * 256, description="problem")
        assert False, "title must be at most 255 characters"
    except Exception:
        pass


def test_required_ticket_priority_and_status_values():
    assert {item.value for item in TicketPriority} == {"CRITICAL", "MEDIUM", "LOW"}
    assert {item.value for item in TicketStatus} == {
        "OPEN",
        "WAITING_CUSTOMER",
        "RESOLVED",
        "CLOSED",
    }
