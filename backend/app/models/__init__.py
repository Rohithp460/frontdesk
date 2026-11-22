from app.db.session import Base  # noqa: F401

# Import every model so Alembic's autogenerate and app imports can discover
# all table metadata via Base.metadata.
from app.models.agent import Agent  # noqa: F401
from app.models.business_calendar import BusinessCalendar  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401
from app.models.ticket_event import TicketEvent  # noqa: F401
from app.models.ticket_wait_period import TicketWaitPeriod  # noqa: F401
from app.models.ticket_counter import TicketCounter  # noqa: F401

__all__ = [
    "Base",
    "Agent",
    "BusinessCalendar",
    "Customer",
    "Ticket",
    "TicketEvent",
    "TicketWaitPeriod",
    "TicketCounter",
]
