from datetime import datetime

from sqlalchemy import Boolean, Enum, Integer, String, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import AgentRole


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AgentRole] = mapped_column(
        Enum(AgentRole, name="agent_role", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AgentRole.AGENT,
        server_default=AgentRole.AGENT.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=text("UTC_TIMESTAMP(6)"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=text("UTC_TIMESTAMP(6)"),
        onupdate=text("UTC_TIMESTAMP(6)"),
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id} email={self.email!r} role={self.role}>"
