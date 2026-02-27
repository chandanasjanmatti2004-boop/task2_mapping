"""Recover missing revision reference.

Revision ID: 0295b84f9ca6
Revises:
Create Date: 2026-02-27 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "0295b84f9ca6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This revision is a placeholder to recover a missing migration file.
    pass


def downgrade() -> None:
    pass
