"""rename repos.dependabot_prs to bot_prs

Hangar now recognizes Renovate PRs alongside Dependabot, so the count is for any
dependency-update bot, not Dependabot specifically. Plain column rename — data preserved.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-06-29 02:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: str | None = 'b7c8d9e0f1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table so SQLite (which lacks ALTER COLUMN RENAME) recreates the table;
    # Postgres emits a native ALTER ... RENAME COLUMN. Existing counts are carried over.
    with op.batch_alter_table('repos') as batch_op:
        batch_op.alter_column('dependabot_prs', new_column_name='bot_prs',
                              existing_type=sa.Integer(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('repos') as batch_op:
        batch_op.alter_column('bot_prs', new_column_name='dependabot_prs',
                              existing_type=sa.Integer(), existing_nullable=False)
