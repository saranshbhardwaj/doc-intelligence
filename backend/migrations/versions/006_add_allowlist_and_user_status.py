"""Add allowed_emails table and user status field for invite-only access control.

Revision ID: 006
Revises: 005
Create Date: 2026-02-21

Adds:
- allowed_emails table (pre-approved emails)
- status column on users table (active / pending_approval)
- Sets all existing users to 'active' so they aren't locked out
"""
from alembic import op
import sqlalchemy as sa


revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create allowed_emails table
    op.create_table(
        'allowed_emails',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('added_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # Add status column to users table (default pending_approval for new users)
    op.add_column('users', sa.Column('status', sa.String(20), nullable=True))

    # Set all existing users to 'active' so they aren't locked out
    op.execute("UPDATE users SET status = 'active' WHERE status IS NULL")

    # Now make it non-nullable with the default for future users
    op.alter_column('users', 'status', nullable=False, server_default='pending_approval')


def downgrade() -> None:
    op.drop_column('users', 'status')
    op.drop_table('allowed_emails')
