"""add repo license spdx column

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-28 02:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: str | None = 'e4f5a6b7c8d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SPDX id of a detected license (e.g. "MIT"); NULL when absent/unidentifiable.
    op.add_column('repos', sa.Column('license_spdx', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('repos') as batch_op:
        batch_op.drop_column('license_spdx')
