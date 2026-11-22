"""initial Frontdesk schema

Revision ID: b48277d7a7ac
Revises:
Create Date: 2026-11-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "b48277d7a7ac"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    utc_now = sa.text("UTC_TIMESTAMP(6)")

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("AGENT", "ADMIN", name="agent_role"), server_default="AGENT", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=utc_now, nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), server_default=utc_now, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_agents_email", "agents", ["email"], unique=True)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=utc_now, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_customers_email", "customers", ["email"], unique=True)

    op.create_table(
        "business_calendar",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_working_day", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("is_holiday", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("date"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_ref", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("assigned_agent_id", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Enum("CRITICAL", "MEDIUM", "LOW", name="ticket_priority"), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.Enum("OPEN", "WAITING_CUSTOMER", "RESOLVED", "CLOSED", name="ticket_status"), server_default="OPEN", nullable=False),
        sa.Column("first_response_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("resolved_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("response_deadline", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("resolution_deadline", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("response_sla_met", sa.Boolean(), nullable=True),
        sa.Column("resolution_sla_met", sa.Boolean(), nullable=True),
        sa.Column("reopened_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("reopened_from_ticket_id", sa.Integer(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=utc_now, nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), server_default=utc_now, nullable=False),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reopened_from_ticket_id"], ["tickets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_tickets_public_ref", "tickets", ["public_ref"], unique=True)
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"], unique=False)
    op.create_index("ix_tickets_assigned_agent_id", "tickets", ["assigned_agent_id"], unique=False)
    op.create_index("ix_tickets_status", "tickets", ["status"], unique=False)
    op.create_index("ix_tickets_priority", "tickets", ["priority"], unique=False)
    op.create_index("ix_tickets_reopened_from_ticket_id", "tickets", ["reopened_from_ticket_id"], unique=False)

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("actor_type", sa.Enum("AGENT", "SYSTEM", "CUSTOMER", name="actor_type"), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.Enum(
            "TICKET_CREATED",
            "TICKET_ASSIGNED",
            "AGENT_REPLY",
            "INTERNAL_NOTE_ADDED",
            "CUSTOMER_REPLY",
            "STATUS_CHANGED",
            "PRIORITY_CHANGED",
            "TICKET_RESOLVED",
            "TICKET_CLOSED",
            "TICKET_REOPENED",
            "NEW_TICKET_CREATED_FROM_CLOSED_TICKET",
            "AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY",
            "SLA_DEADLINE_RECALCULATED",
            name="event_type",
        ), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False, server_default=utc_now),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=utc_now),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"], unique=False)
    op.create_index("ix_ticket_events_event_type", "ticket_events", ["event_type"], unique=False)
    op.create_index("ix_ticket_events_occurred_at", "ticket_events", ["occurred_at"], unique=False)

    op.create_table(
        "ticket_wait_periods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False, server_default=utc_now),
        sa.Column("ended_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=utc_now),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_ticket_wait_periods_ticket_id", "ticket_wait_periods", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ticket_wait_periods_ticket_id", table_name="ticket_wait_periods")
    op.drop_table("ticket_wait_periods")
    op.drop_index("ix_ticket_events_occurred_at", table_name="ticket_events")
    op.drop_index("ix_ticket_events_event_type", table_name="ticket_events")
    op.drop_index("ix_ticket_events_ticket_id", table_name="ticket_events")
    op.drop_table("ticket_events")
    op.drop_index("ix_tickets_reopened_from_ticket_id", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_assigned_agent_id", table_name="tickets")
    op.drop_index("ix_tickets_customer_id", table_name="tickets")
    op.drop_index("ix_tickets_public_ref", table_name="tickets")
    op.drop_table("tickets")
    op.drop_table("business_calendar")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_agents_email", table_name="agents")
    op.drop_table("agents")

