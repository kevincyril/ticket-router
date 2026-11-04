"""Persist abstention evidence without changing historical predictions."""
from alembic import op
import sqlalchemy as sa
revision='002'
down_revision='001'


def upgrade():
    op.add_column('tickets',sa.Column('routing_evidence',sa.JSON(),nullable=True))


def downgrade():
    op.drop_column('tickets','routing_evidence')
