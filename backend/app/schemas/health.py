from typing import Optional
from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
    app: str = Field(default="Frontdesk", json_schema_extra={"example": "Frontdesk"})
    version: str = Field(default="0.1.0", json_schema_extra={"example": "0.1.0"})
    database: Optional[str] = Field(default="connected", json_schema_extra={"example": "connected"})
