"""add repo suppressions column

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-03 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: str | None = 'c8d9e0f1a2b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # {check_id: reason} opt-outs from the repo's committed .hangar.json; NULL = none.
    op.add_column('repos', sa.Column('suppressions', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('repos') as batch_op:
        batch_op.drop_column('suppressions')
