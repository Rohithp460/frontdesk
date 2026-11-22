from app.main import app
from app.models.enums import EventType
from app.models.ticket_wait_period import TicketWaitPeriod
from app.services.ticket_service import get_customer_facing_ticket


def test_workflow_route_names_exist():
    paths = {route.path for route in app.routes}
    required = {
        "/tickets/{ticket_id}/claim",
        "/tickets/{ticket_id}/replies",
        "/tickets/{ticket_id}/internal-notes",
        "/tickets/{ticket_id}/customer-reply",
        "/tickets/{ticket_id}/resolve",
        "/tickets/{ticket_id}/close",
        "/tickets/{ticket_id}/reopen",
        "/tickets/{ticket_id}/timeline",
        "/tickets/{ticket_id}/customer-view",
    }
    assert required.issubset(paths)


def test_internal_note_event_is_an_excluded_event_type():
    assert EventType.INTERNAL_NOTE_ADDED.value == "INTERNAL_NOTE_ADDED"
