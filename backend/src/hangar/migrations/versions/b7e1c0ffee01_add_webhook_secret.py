"""add per-connection webhook secret

Revision ID: b7e1c0ffee01
Revises: 5c0cdbd880ff
Create Date: 2026-06-23 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e1c0ffee01'
down_revision: str | None = '5c0cdbd880ff'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'connections',
        sa.Column('webhook_secret_ciphertext', sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table('connections') as batch_op:
        batch_op.drop_column('webhook_secret_ciphertext')
