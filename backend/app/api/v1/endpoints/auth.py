from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_agent
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.agent import Agent
from app.schemas.agent import AgentOut, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Agent login",
    description=(
        "Authenticate with email and password. "
        "Returns a Bearer access token and the agent's profile."
    ),
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    agent = db.query(Agent).filter(Agent.email == payload.email).first()

    if agent is None or not agent.is_active or not verify_password(payload.password, agent.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=agent.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        agent=AgentOut.model_validate(agent),
    )


@router.get(
    "/me",
    response_model=AgentOut,
    summary="Get current agent",
    description="Returns the profile of the currently authenticated agent.",
)
def me(current_agent: Agent = Depends(get_current_agent)) -> AgentOut:
    return AgentOut.model_validate(current_agent)
