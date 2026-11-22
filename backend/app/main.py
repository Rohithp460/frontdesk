from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.endpoints.health import get_health
from app.api.v1.router import api_router
from app.schemas.health import HealthCheckResponse


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Set up CORS
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Health check route directly at GET /health
    app.add_api_route(
        "/health",
        get_health,
        methods=["GET"],
        response_model=HealthCheckResponse,
        summary="Service health check",
        tags=["Health"],
    )

    # Versioned API routes under /api/v1
    app.include_router(api_router, prefix=settings.API_V1_STR)
    # Root routes are part of the documented API in this project.
    app.include_router(api_router)

    return app


app = create_application()
