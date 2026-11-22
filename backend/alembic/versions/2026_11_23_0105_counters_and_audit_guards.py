"""add atomic reference counter and protect audit/wait rows

Revision ID: 20261123_counter
Revises: 20261122_phase8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261123_counter"
down_revision: Union[str, None] = "20261122_phase8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_fk(table: str, column: str, target: str) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
            "AND COLUMN_NAME = :column AND REFERENCED_TABLE_NAME = :target"
        ),
        {"table": table, "column": column, "target": target},
    ).fetchall()
    for row in rows:
        op.drop_constraint(row[0], table, type_="foreignkey")
    op.create_foreign_key(
        f"fk_{table}_{column}_{target}",
        table,
        target,
        [column],
        ["id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("ticket_counters"):
        op.create_table(
            "ticket_counters",
            sa.Column("name", sa.String(length=32), nullable=False),
            sa.Column("last_value", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("name"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
    op.execute(
            "INSERT INTO ticket_counters (`name`, `last_value`) "
        "SELECT 'ticket', COALESCE(MAX(CAST(SUBSTRING(public_ref, 5) AS UNSIGNED)), 0) "
        "FROM tickets WHERE public_ref REGEXP '^INC-[0-9]+$' "
            "ON DUPLICATE KEY UPDATE `last_value` = "
            "GREATEST(`last_value`, VALUES(`last_value`))"
    )
    _replace_fk("ticket_events", "ticket_id", "tickets")
    _replace_fk("ticket_wait_periods", "ticket_id", "tickets")

    op.execute(
        "ALTER TABLE tickets "
        "MODIFY first_response_at DATETIME(6) NULL, "
        "MODIFY resolved_at DATETIME(6) NULL, "
        "MODIFY closed_at DATETIME(6) NULL, "
        "MODIFY response_deadline DATETIME(6) NULL, "
        "MODIFY resolution_deadline DATETIME(6) NULL, "
        "MODIFY reopened_until DATETIME(6) NULL, "
        "MODIFY created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)), "
        "MODIFY updated_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6))"
    )
    op.execute(
        "ALTER TABLE ticket_wait_periods "
        "MODIFY started_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)), "
        "MODIFY ended_at DATETIME(6) NULL, "
        "MODIFY created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6))"
    )


def downgrade() -> None:
    op.drop_table("ticket_counters")
