import enum


class TicketPriority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    # Backward-compatible aliases used by the existing partial implementation.
    urgent = "CRITICAL"
    high = "MEDIUM"
    medium = "MEDIUM"
    low = "LOW"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return {
                "urgent": cls.CRITICAL,
                "high": cls.MEDIUM,
                "medium": cls.MEDIUM,
                "low": cls.LOW,
            }.get(normalized)
        return None


class TicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    # Backward-compatible aliases used by the existing partial implementation.
    open = "OPEN"
    new = "OPEN"
    pending = "WAITING_CUSTOMER"
    on_hold = "WAITING_CUSTOMER"
    resolved = "RESOLVED"
    closed = "CLOSED"
    reopened = "OPEN"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return {
                "new": cls.OPEN,
                "open": cls.OPEN,
                "pending": cls.WAITING_CUSTOMER,
                "on_hold": cls.WAITING_CUSTOMER,
                "waiting_customer": cls.WAITING_CUSTOMER,
                "resolved": cls.RESOLVED,
                "closed": cls.CLOSED,
                "reopened": cls.OPEN,
            }.get(normalized)
        return None


class AgentRole(str, enum.Enum):
    AGENT = "AGENT"
    ADMIN = "ADMIN"

    admin = "ADMIN"
    agent = "AGENT"


class ActorType(str, enum.Enum):
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    CUSTOMER = "CUSTOMER"

    agent = "AGENT"
    system = "SYSTEM"
    customer = "CUSTOMER"


class EventType(str, enum.Enum):
    TICKET_CREATED = "TICKET_CREATED"
    TICKET_ASSIGNED = "TICKET_ASSIGNED"
    AGENT_REPLY = "AGENT_REPLY"
    INTERNAL_NOTE_ADDED = "INTERNAL_NOTE_ADDED"
    CUSTOMER_REPLY = "CUSTOMER_REPLY"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    TICKET_RESOLVED = "TICKET_RESOLVED"
    TICKET_CLOSED = "TICKET_CLOSED"
    TICKET_REOPENED = "TICKET_REOPENED"
    NEW_TICKET_CREATED_FROM_CLOSED_TICKET = "NEW_TICKET_CREATED_FROM_CLOSED_TICKET"
    AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY = "AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY"
    SLA_DEADLINE_RECALCULATED = "SLA_DEADLINE_RECALCULATED"

    # Backward-compatible aliases used by the existing partial implementation.
    created = "TICKET_CREATED"
    assigned = "TICKET_ASSIGNED"
    replied = "AGENT_REPLY"
    noted = "INTERNAL_NOTE_ADDED"
    status_changed = "STATUS_CHANGED"
    priority_changed = "PRIORITY_CHANGED"
    resolved = "TICKET_RESOLVED"
    closed = "TICKET_CLOSED"
    reopened = "TICKET_REOPENED"
