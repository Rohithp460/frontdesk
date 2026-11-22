from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.agent import Agent
from app.services.ticket_service import auto_close_inactive_tickets, mark_missed_response_slas

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/auto-close-check")
def run_auto_close_check(
    db: Session = Depends(get_db),
    _: Agent = Depends(require_admin),
) -> dict:
    closed = auto_close_inactive_tickets(db)
    return {"closed_count": len(closed), "ticket_ids": [ticket.id for ticket in closed]}


@router.post("/sla-check")
def run_sla_check(
    db: Session = Depends(get_db),
    _: Agent = Depends(require_admin),
) -> dict:
    marked = mark_missed_response_slas(db)
    return {"response_sla_missed_count": marked}