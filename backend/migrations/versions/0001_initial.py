"""Initial House OS schema.

Revision ID: 0001_initial
Revises: None
"""

from alembic import op
from app.database.base import Base
from app.models import registry  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
