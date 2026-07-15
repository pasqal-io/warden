"""add QPU capacity and session lifecycle fields

Revision ID: 8ad0f6a4b2c1
Revises: 6c4fad0bfc30
Create Date: 2026-07-14 12:10:00.000000

"""

from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ad0f6a4b2c1"
down_revision: Union[str, Sequence[str], None] = "6c4fad0bfc30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column(
            "slurm_job_id",
            new_column_name="scheduler_job_id",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
    op.add_column(
        "sessions",
        sa.Column("qpu_slots", sa.Integer(), server_default="1", nullable=False),
    )
    if bind.dialect.name != "sqlite":
        op.alter_column("sessions", "qpu_slots", server_default=None)

    table = op.create_table(
        "qpu_capacity_lock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(table, [{"id": 1, "revision": 0}])

    op.add_column(
        "sessions",
        sa.Column(
            "scheduler_vruntime",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    if bind.dialect.name != "sqlite":
        op.alter_column("sessions", "scheduler_vruntime", server_default=None)

    op.add_column(
        "sessions",
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("revocation_reason", sa.String(length=50), nullable=True),
    )
    sessions = sa.table(
        "sessions",
        sa.column("idle_expires_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.execute(
        sessions.update().values(
            idle_expires_at=now + timedelta(hours=1),
            expires_at=now + timedelta(days=30),
        )
    )
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column(
            "idle_expires_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.create_index(
            "ix_sessions_scheduler_job_id", ["scheduler_job_id"], unique=False
        )
        batch_op.create_index(
            "ix_sessions_idle_expires_at", ["idle_expires_at"], unique=False
        )
        batch_op.create_index("ix_sessions_expires_at", ["expires_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_expires_at")
        batch_op.drop_index("ix_sessions_idle_expires_at")
        batch_op.drop_index("ix_sessions_scheduler_job_id")
        batch_op.drop_column("revocation_reason")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("idle_expires_at")
        batch_op.drop_column("scheduler_vruntime")
    op.drop_table("qpu_capacity_lock")
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("qpu_slots")
        batch_op.alter_column(
            "scheduler_job_id",
            new_column_name="slurm_job_id",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
