"""add github_app_registrations table

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-06-29 00:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: str | None = 'a6b7c8d9e0f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One GitHub App per browser host (github.com / a GHEC tenant / a GHES instance),
    # provisioned via the manifest flow. Secrets are Fernet ciphertext (FR-032).
    op.create_table(
        'github_app_registrations',
        sa.Column('base_url', sa.String(length=255), primary_key=True),
        sa.Column('app_id', sa.String(length=32), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('client_id', sa.String(length=128), nullable=True),
        sa.Column('private_key_ciphertext', sa.LargeBinary(), nullable=False),
        sa.Column('webhook_secret_ciphertext', sa.LargeBinary(), nullable=True),
        sa.Column('client_secret_ciphertext', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('github_app_registrations')
