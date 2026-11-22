from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import AgentRole


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """
    Uses plain str for email so internal .local addresses are accepted.
    Real-world validation is enforced at the DB layer (unique index) and
    at registration time (which is out of scope for this service).
    """
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class AgentOut(BaseModel):
    id: int
    name: str
    email: str
    role: AgentRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    agent: AgentOut
