"""align ticket schema and UTC customer timestamps

Revision ID: 20261123_schema
Revises: 20261123_counter
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261123_schema"
down_revision: Union[str, None] = "20261123_counter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    overlong_titles = connection.execute(
        sa.text("SELECT COUNT(*) FROM tickets WHERE CHAR_LENGTH(title) > 255")
    ).scalar_one()
    if overlong_titles:
        raise RuntimeError(
            "Cannot restrict tickets.title to 255 characters: "
            f"{overlong_titles} existing ticket(s) exceed the limit"
        )

    invalid_reopen_links = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM tickets t "
            "LEFT JOIN tickets parent ON parent.id = t.reopened_from_ticket_id "
            "WHERE t.reopened_from_ticket_id IS NOT NULL AND parent.id IS NULL"
        )
    ).scalar_one()
    if invalid_reopen_links:
        raise RuntimeError(
            "Cannot add the reopened-ticket foreign key: "
            f"{invalid_reopen_links} invalid reference(s) exist"
        )

    connection.execute(
        sa.text(
            "UPDATE tickets SET description = 'Legacy ticket description unavailable' "
            "WHERE description IS NULL"
        )
    )
    op.execute(
        "ALTER TABLE tickets "
        "MODIFY title VARCHAR(255) NOT NULL, "
        "MODIFY description TEXT NOT NULL"
    )
    op.execute(
        "ALTER TABLE customers "
        "MODIFY created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6))"
    )

    indexes = {index["name"] for index in inspector.get_indexes("tickets")}
    if "ix_tickets_reopened_from_ticket_id" not in indexes:
        op.create_index(
            "ix_tickets_reopened_from_ticket_id",
            "tickets",
            ["reopened_from_ticket_id"],
            unique=False,
        )

    foreign_keys = inspector.get_foreign_keys("tickets")
    has_reopen_fk = any(
        fk.get("constrained_columns") == ["reopened_from_ticket_id"]
        and fk.get("referred_table") == "tickets"
        for fk in foreign_keys
    )
    if not has_reopen_fk:
        op.create_foreign_key(
            "fk_tickets_reopened_from_ticket_id_tickets",
            "tickets",
            "tickets",
            ["reopened_from_ticket_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    foreign_keys = inspector.get_foreign_keys("tickets")
    for foreign_key in foreign_keys:
        if foreign_key.get("constrained_columns") == ["reopened_from_ticket_id"]:
            op.drop_constraint(foreign_key["name"], "tickets", type_="foreignkey")

    indexes = {index["name"] for index in inspector.get_indexes("tickets")}
    if "ix_tickets_reopened_from_ticket_id" in indexes:
        op.drop_index("ix_tickets_reopened_from_ticket_id", table_name="tickets")

    op.execute(
        "ALTER TABLE tickets "
        "MODIFY title VARCHAR(512) NOT NULL, "
        "MODIFY description TEXT NULL"
    )
    op.execute(
        "ALTER TABLE customers "
        "MODIFY created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
