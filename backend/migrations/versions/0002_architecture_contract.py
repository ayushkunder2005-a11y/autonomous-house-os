"""Align runtime schema with Anti Gravity's authoritative contracts.

Revision ID: 0002_architecture_contract
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op
from app.models.operations import ConflictLog

revision = "0002_architecture_contract"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def column_names(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in column_names(table):
        with op.batch_alter_table(table) as batch:
            batch.add_column(column)


def upgrade() -> None:
    add_column_if_missing(
        "houses", sa.Column("security_mode", sa.String(20), nullable=False, server_default="HOME")
    )
    add_column_if_missing(
        "houses", sa.Column("latitude", sa.Float(), nullable=False, server_default="0")
    )
    add_column_if_missing(
        "houses", sa.Column("longitude", sa.Float(), nullable=False, server_default="0")
    )
    add_column_if_missing("users", sa.Column("pin_code_hash", sa.String(255), nullable=True))
    add_column_if_missing("sensors", sa.Column("device_id", sa.String(36), nullable=True))
    add_column_if_missing(
        "commands", sa.Column("endpoint", sa.String(80), nullable=False, server_default="default")
    )
    add_column_if_missing(
        "commands", sa.Column("priority_tier", sa.Integer(), nullable=False, server_default="3")
    )
    add_column_if_missing("commands", sa.Column("reason", sa.Text(), nullable=True))
    if not sa.inspect(op.get_bind()).has_table("conflict_logs"):
        ConflictLog.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    # 0001 creates the current metadata for fresh installations, so removing
    # these columns independently would invalidate its indexes on SQLite.
    # Full rollback remains available through the 0001 downgrade.
    pass
