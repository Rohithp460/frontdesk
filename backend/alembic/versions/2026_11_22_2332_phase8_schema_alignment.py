"""align existing local schema with required Frontdesk schema

Revision ID: 20261122_phase8
Revises: b48277d7a7ac
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261122_phase8"
down_revision: Union[str, None] = "b48277d7a7ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    columns = {
        column_info["name"]
        for column_info in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    if column.name not in columns:
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing(
        "agents",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    _add_column_if_missing(
        "agents",
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("UTC_TIMESTAMP(6)"),
        ),
    )
    op.execute("ALTER TABLE agents MODIFY role VARCHAR(20) NOT NULL DEFAULT 'AGENT'")
    op.execute("UPDATE agents SET role = 'ADMIN' WHERE role = 'admin'")
    op.execute("UPDATE agents SET role = 'AGENT' WHERE role = 'agent'")
    op.execute(
        "ALTER TABLE agents MODIFY role ENUM('AGENT','ADMIN') "
        "NOT NULL DEFAULT 'AGENT'"
    )

    op.execute("ALTER TABLE tickets MODIFY priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM'")
    op.execute("UPDATE tickets SET priority = 'CRITICAL' WHERE priority IN ('urgent','critical','URGENT')")
    op.execute("UPDATE tickets SET priority = 'MEDIUM' WHERE priority IN ('high','medium','HIGH','MEDIUM')")
    op.execute("UPDATE tickets SET priority = 'LOW' WHERE priority IN ('low','LOW')")
    op.execute(
        "ALTER TABLE tickets MODIFY priority ENUM('CRITICAL','MEDIUM','LOW') "
        "NOT NULL DEFAULT 'MEDIUM'"
    )
    op.execute("ALTER TABLE tickets MODIFY status VARCHAR(30) NOT NULL DEFAULT 'OPEN'")
    op.execute(
        "UPDATE tickets SET status = 'WAITING_CUSTOMER' "
        "WHERE status IN ('pending','on_hold','PENDING','ON_HOLD')"
    )
    op.execute("UPDATE tickets SET status = 'OPEN' WHERE status IN ('new','open','reopened','NEW','OPEN','REOPENED')")
    op.execute("UPDATE tickets SET status = 'RESOLVED' WHERE status IN ('resolved','RESOLVED')")
    op.execute("UPDATE tickets SET status = 'CLOSED' WHERE status IN ('closed','CLOSED')")
    op.execute(
        "ALTER TABLE tickets MODIFY status "
        "ENUM('OPEN','WAITING_CUSTOMER','RESOLVED','CLOSED') "
        "NOT NULL DEFAULT 'OPEN'"
    )
    _add_column_if_missing(
        "tickets", sa.Column("response_sla_met", sa.Boolean(), nullable=True)
    )
    _add_column_if_missing(
        "tickets", sa.Column("resolution_sla_met", sa.Boolean(), nullable=True)
    )
    _add_column_if_missing(
        "tickets", sa.Column("reopened_from_ticket_id", sa.Integer(), nullable=True)
    )
    op.execute(
        "UPDATE tickets SET reopened_from_ticket_id = NULL "
        "WHERE reopened_from_ticket_id IS NULL"
    )

    _add_column_if_missing(
        "ticket_events", sa.Column("actor_name", sa.String(length=255), nullable=True)
    )
    op.execute("ALTER TABLE ticket_events MODIFY actor_type VARCHAR(20) NOT NULL")
    op.execute("UPDATE ticket_events SET actor_type = 'AGENT' WHERE actor_type = 'agent'")
    op.execute("UPDATE ticket_events SET actor_type = 'CUSTOMER' WHERE actor_type = 'customer'")
    op.execute("UPDATE ticket_events SET actor_type = 'SYSTEM' WHERE actor_type = 'system'")
    op.execute(
        "ALTER TABLE ticket_events MODIFY actor_type "
        "ENUM('AGENT','SYSTEM','CUSTOMER') NOT NULL"
    )

    op.execute("ALTER TABLE ticket_events MODIFY event_type VARCHAR(64) NOT NULL")
    op.execute("UPDATE ticket_events SET event_type = 'TICKET_CREATED' WHERE event_type = 'created'")
    op.execute("UPDATE ticket_events SET event_type = 'TICKET_ASSIGNED' WHERE event_type = 'assigned'")
    op.execute("UPDATE ticket_events SET event_type = 'AGENT_REPLY' WHERE event_type IN ('replied','AGENT_REPLY')")
    op.execute("UPDATE ticket_events SET event_type = 'INTERNAL_NOTE_ADDED' WHERE event_type IN ('noted','INTERNAL_NOTE_ADDED')")
    op.execute("UPDATE ticket_events SET event_type = 'CUSTOMER_REPLY' WHERE event_type = 'CUSTOMER_REPLY'")
    op.execute("UPDATE ticket_events SET event_type = 'STATUS_CHANGED' WHERE event_type = 'status_changed'")
    op.execute("UPDATE ticket_events SET event_type = 'PRIORITY_CHANGED' WHERE event_type = 'priority_changed'")
    op.execute("UPDATE ticket_events SET event_type = 'TICKET_RESOLVED' WHERE event_type = 'resolved'")
    op.execute("UPDATE ticket_events SET event_type = 'TICKET_CLOSED' WHERE event_type = 'closed'")
    op.execute("UPDATE ticket_events SET event_type = 'TICKET_REOPENED' WHERE event_type = 'reopened'")
    op.execute(
        "ALTER TABLE ticket_events MODIFY event_type ENUM("
        "'TICKET_CREATED','TICKET_ASSIGNED','AGENT_REPLY','INTERNAL_NOTE_ADDED',"
        "'CUSTOMER_REPLY','STATUS_CHANGED','PRIORITY_CHANGED','TICKET_RESOLVED',"
        "'TICKET_CLOSED','TICKET_REOPENED','NEW_TICKET_CREATED_FROM_CLOSED_TICKET',"
        "'AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY','SLA_DEADLINE_RECALCULATED'"
        ") NOT NULL"
    )
    _add_column_if_missing(
        "ticket_wait_periods",
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("UTC_TIMESTAMP(6)"),
        ),
    )

    op.execute(
        "ALTER TABLE agents MODIFY created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6), "
        "MODIFY updated_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6)"
    )
    op.execute(
        "ALTER TABLE ticket_events "
        "MODIFY occurred_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6), "
        "MODIFY created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6)"
    )
