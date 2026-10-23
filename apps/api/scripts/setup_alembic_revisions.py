"""Generate Alembic revisions:
1. 08426f7bebcb_initial_schema.py (Baseline tables without api_tokens and without audit_logs.client_type)
2. b2c3d4e5f6a7_add_api_tokens_and_client_type.py (Adds api_tokens table and audit_logs.client_type)
"""

from pathlib import Path
from sqlalchemy import create_engine
from alembic.migration import MigrationContext
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.operations import ops
from kawach.db.base import Base
import kawach.db.models

REPO_ROOT = Path(__file__).resolve().parents[3]
VERSIONS_DIR = REPO_ROOT / "apps" / "api" / "alembic" / "versions"
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


def build_revisions():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        migration_script = produce_migrations(ctx, Base.metadata)

    # Separate ops into baseline vs A1
    baseline_upgrade_ops = []
    a1_upgrade_ops = []

    for op in migration_script.upgrade_ops.ops:
        if isinstance(op, ops.CreateTableOp) and op.table_name == "api_tokens":
            a1_upgrade_ops.append(op)
        elif isinstance(op, ops.CreateIndexOp) and op.table_name == "api_tokens":
            a1_upgrade_ops.append(op)
        elif isinstance(op, ops.CreateTableOp) and op.table_name == "audit_logs":
            # Remove client_type from baseline audit_logs creation
            op.columns = [c for c in op.columns if c.name != "client_type"]
            baseline_upgrade_ops.append(op)
        else:
            baseline_upgrade_ops.append(op)

    # Render baseline migration code
    baseline_context = MigrationContext.configure(engine.connect())
    baseline_migration = ops.MigrationScript(
        rev_id="08426f7bebcb",
        upgrade_ops=ops.UpgradeOps(ops=baseline_upgrade_ops),
        downgrade_ops=ops.DowngradeOps(ops=list(reversed(baseline_upgrade_ops))),
    )

    baseline_code = render_python_code(baseline_migration.upgrade_ops)
    baseline_down_code = render_python_code(baseline_migration.downgrade_ops)

    rev1_content = f'''"""initial_schema

Revision ID: 08426f7bebcb
Revises: 
Create Date: 2026-10-23 01:04:40.524407

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '08426f7bebcb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
{baseline_code}


def downgrade() -> None:
{baseline_down_code}
'''

    rev1_path = VERSIONS_DIR / "08426f7bebcb_initial_schema.py"
    with open(rev1_path, "w", encoding="utf-8") as f:
        f.write(rev1_content)
    print(f"Wrote {rev1_path}")

    # Revision 2: A1 schema additions
    rev2_content = '''"""add_api_tokens_and_client_type

Revision ID: b2c3d4e5f6a7
Revises: 08426f7bebcb
Create Date: 2026-10-23 09:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '08426f7bebcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create api_tokens table
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('token_prefix', sa.String(length=16), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('scopes', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_tokens_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_api_tokens_user_id'), ['user_id'], unique=False)

    # 2. Add client_type to audit_logs
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_type', sa.String(length=20), nullable=False, server_default='web'))


def downgrade() -> None:
    # 1. Remove client_type from audit_logs
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_column('client_type')

    # 2. Drop api_tokens table
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_tokens_user_id'))
        batch_op.drop_index(batch_op.f('ix_api_tokens_token_hash'))

    op.drop_table('api_tokens')
'''

    rev2_path = VERSIONS_DIR / "b2c3d4e5f6a7_add_api_tokens_and_client_type.py"
    with open(rev2_path, "w", encoding="utf-8") as f:
        f.write(rev2_content)
    print(f"Wrote {rev2_path}")


if __name__ == "__main__":
    build_revisions()
