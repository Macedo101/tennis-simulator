"""make simulations.user_id nullable for anonymous simulations

Revision ID: 48be6179093b
Revises: 9b0821082666
Create Date: 2026-08-01 11:13:10.750288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48be6179093b'
down_revision: Union[str, Sequence[str], None] = '9b0821082666'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("simulations", schema=None) as batch_op:
        batch_op.alter_column(
            "user_id", existing_type=sa.CHAR(length=32), nullable=True
        )
        batch_op.drop_constraint(
            op.f("fk_simulations_user_id_users"), type_="foreignkey"
        )
        batch_op.create_foreign_key(
            op.f("fk_simulations_user_id_users"),
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("simulations", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_simulations_user_id_users"), type_="foreignkey"
        )
        batch_op.create_foreign_key(
            op.f("fk_simulations_user_id_users"),
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.alter_column(
            "user_id", existing_type=sa.CHAR(length=32), nullable=False
        )
