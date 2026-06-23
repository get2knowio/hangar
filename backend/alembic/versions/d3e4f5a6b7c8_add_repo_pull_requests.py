"""add captured pull_requests to repo snapshot

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-23 00:20:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: str | None = 'c2d3e4f5a6b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('repos', sa.Column('pull_requests', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('repos') as batch_op:
        batch_op.drop_column('pull_requests')
