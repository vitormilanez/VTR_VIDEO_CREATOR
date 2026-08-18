"""content cutover compatibility

Revision ID: 20260817_0002
Revises: 20260814_0001
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260817_0002"
down_revision: str | None = "20260814_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calendar_posts", sa.Column("legacy_job_id", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_posts", "legacy_job_id")
