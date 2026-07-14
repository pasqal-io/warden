"""add QPU capacity and scheduler fields

Revision ID: 8ad0f6a4b2c1
Revises: 6c4fad0bfc30
Create Date: 2026-07-14 12:10:00.000000

"""

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


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("scheduler_vruntime")
    op.drop_table("qpu_capacity_lock")
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("qpu_slots")
