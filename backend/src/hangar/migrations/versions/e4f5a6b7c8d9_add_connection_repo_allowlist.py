"""add connection repo allowlist column

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-28 00:45:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: str | None = 'd3e4f5a6b7c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = watch every repo the credential can see (prior behavior); a JSON list scopes
    # the connection's fleet to exactly those repo names.
    op.add_column('connections', sa.Column('repo_allowlist', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('connections') as batch_op:
        batch_op.drop_column('repo_allowlist')
