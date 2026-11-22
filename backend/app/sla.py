from app.services.sla_service import (
    KOLKATA,
    SLA_CONFIG,
    WORK_MINUTES_PER_DAY,
    calculate_resolution_deadline,
    calculate_response_deadline,
)

__all__ = [
    "SLA_CONFIG",
    "KOLKATA",
    "WORK_MINUTES_PER_DAY",
    "calculate_response_deadline",
    "calculate_resolution_deadline",
]
