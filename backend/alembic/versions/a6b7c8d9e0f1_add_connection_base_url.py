"""add connection base_url column

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-29 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6b7c8d9e0f1'
down_revision: str | None = 'f5a6b7c8d9e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-connection provider browser host. A server_default backfills existing rows to
    # github.com (the only host before multi-host support), so the column is NOT NULL.
    op.add_column(
        'connections',
        sa.Column(
            'base_url',
            sa.String(length=255),
            nullable=False,
            server_default='https://github.com',
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table('connections') as batch_op:
        batch_op.drop_column('base_url')
