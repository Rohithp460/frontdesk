from typing import Generator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import verify_token
from app.db.session import get_db
from app.models.agent import Agent

bearer_scheme = HTTPBearer(auto_error=True)


def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Agent:
    """
    Decode the Bearer JWT, look up the agent, and return the ORM object.
    Raises HTTP 401 on any authentication failure.
    """
    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    agent_id: Optional[int] = None
    try:
        agent_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return agent


def require_admin(
    current_agent: Agent = Depends(get_current_agent),
) -> Agent:
    """Guard that restricts an endpoint to admin-role agents only."""
    from app.models.enums import AgentRole
    if current_agent.role not in {AgentRole.ADMIN, AgentRole.admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_agent


def require_supervisor_or_admin(
    current_agent: Agent = Depends(get_current_agent),
) -> Agent:
    """Guard retained for compatibility; only ADMIN is an elevated role."""
    from app.models.enums import AgentRole
    allowed = {AgentRole.ADMIN, AgentRole.admin}
    if current_agent.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor or admin role required",
        )
    return current_agent
