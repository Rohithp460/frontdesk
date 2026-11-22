from fastapi import APIRouter
from sqlalchemy import text

from app.schemas.health import HealthCheckResponse
from app.config import settings
from app.database import SessionLocal

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check endpoint",
    description="Returns the health status of the Frontdesk service.",
    tags=["Health"],
)
def get_health() -> HealthCheckResponse:
    db_status = "disconnected"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthCheckResponse(
        status="ok",
        app=settings.PROJECT_NAME,
        version="0.1.0",
        database=db_status,
    )
