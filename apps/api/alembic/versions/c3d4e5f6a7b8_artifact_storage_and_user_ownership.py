"""artifact_storage_and_user_ownership

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-24 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('artifacts')]

    with op.batch_alter_table('artifacts', schema=None) as batch_op:
        if 'user_id' not in cols:
            batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))
            batch_op.create_foreign_key('fk_artifacts_user_id', 'users', ['user_id'], ['id'], ondelete='CASCADE')
            batch_op.create_index(batch_op.f('ix_artifacts_user_id'), ['user_id'], unique=False)
        if 'test_id' not in cols:
            batch_op.add_column(sa.Column('test_id', sa.String(length=64), nullable=True))
            batch_op.create_index(batch_op.f('ix_artifacts_test_id'), ['test_id'], unique=False)
        if 'type' not in cols:
            batch_op.add_column(sa.Column('type', sa.String(length=32), nullable=False, server_default='other'))
        if 'relative_path' not in cols:
            batch_op.add_column(sa.Column('relative_path', sa.String(length=1024), nullable=False, server_default=''))
        if 'size' not in cols:
            batch_op.add_column(sa.Column('size', sa.Integer(), nullable=False, server_default='0'))
        if 'mime_type' not in cols:
            batch_op.add_column(sa.Column('mime_type', sa.String(length=128), nullable=True))
        batch_op.alter_column('project_id', existing_type=sa.String(length=36), nullable=True)
        if 'user_id' not in cols or 'type' not in cols:
            batch_op.create_index('ix_artifacts_user_type', ['user_id', 'type'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('artifacts', schema=None) as batch_op:
        batch_op.drop_index('ix_artifacts_user_type')
        batch_op.drop_index(batch_op.f('ix_artifacts_test_id'))
        batch_op.drop_index(batch_op.f('ix_artifacts_user_id'))
        batch_op.drop_constraint('fk_artifacts_user_id', type_='foreignkey')
        batch_op.drop_column('mime_type')
        batch_op.drop_column('size')
        batch_op.drop_column('relative_path')
        batch_op.drop_column('type')
        batch_op.drop_column('test_id')
        batch_op.drop_column('user_id')
