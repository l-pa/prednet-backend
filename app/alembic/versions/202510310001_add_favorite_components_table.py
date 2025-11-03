"""Add favorite components table

Revision ID: 202510310001
Revises: d98dd8ec85a3
Create Date: 2025-10-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '202510310001'
down_revision = '1a31ce608336'
branch_labels = None
depends_on = None


def upgrade():
    # Ensure uuid-ossp extension is available (PostgreSQL)
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    except Exception:
        # Ignore on non-Postgres or if not supported
        pass

    op.create_table(
        'favorite_component',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('network_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('filename', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('component_id', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fav_owner', 'favorite_component', ['owner_id'], unique=False)
    op.create_index('ix_fav_network', 'favorite_component', ['network_name'], unique=False)


def downgrade():
    op.drop_index('ix_fav_network', table_name='favorite_component')
    op.drop_index('ix_fav_owner', table_name='favorite_component')
    op.drop_table('favorite_component')
