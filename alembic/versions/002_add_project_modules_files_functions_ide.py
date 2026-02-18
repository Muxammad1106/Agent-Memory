"""Add project modules, files, functions, IDE sessions, change logs

Revision ID: 002
Revises: 001
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create project_modules table
    op.create_table(
        'project_modules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('module_type', sa.String(50), nullable=False),
        sa.Column('path', sa.String(1000), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('tech_stack', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('frameworks', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('languages', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('entry_points', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('config_files', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('total_files', sa.Integer, nullable=False, default=0),
        sa.Column('total_lines', sa.Integer, nullable=False, default=0),
        sa.Column('metadata', postgresql.JSONB, nullable=True, default={}),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_project_modules_project', 'project_modules', ['project_id'])
    op.create_index('ix_project_modules_type', 'project_modules', ['module_type'])

    # Create project_files table
    op.create_table(
        'project_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('module_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_modules.id', ondelete='SET NULL'), nullable=True),
        sa.Column('component_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('components.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('path', sa.String(1000), nullable=False),
        sa.Column('relative_path', sa.String(1000), nullable=False),
        sa.Column('language', sa.String(50), nullable=True),
        sa.Column('file_extension', sa.String(20), nullable=True),
        sa.Column('content', sa.Text, nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('size_bytes', sa.Integer, nullable=False, default=0),
        sa.Column('line_count', sa.Integer, nullable=False, default=0),
        sa.Column('imports', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('exports', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('dependencies', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('purpose', sa.Text, nullable=True),
        sa.Column('embedding', postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True, default={}),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('last_indexed', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_project_files_project', 'project_files', ['project_id'])
    op.create_index('ix_project_files_module', 'project_files', ['module_id'])
    op.create_index('ix_project_files_path', 'project_files', ['path'])
    op.create_index('ix_project_files_hash', 'project_files', ['content_hash'])

    # Create project_functions table
    op.create_table(
        'project_functions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('signature', sa.Text, nullable=True),
        sa.Column('docstring', sa.Text, nullable=True),
        sa.Column('body', sa.Text, nullable=True),
        sa.Column('line_start', sa.Integer, nullable=False),
        sa.Column('line_end', sa.Integer, nullable=False),
        sa.Column('parameters', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('return_type', sa.String(255), nullable=True),
        sa.Column('decorators', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('calls', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('called_by', postgresql.JSONB, nullable=True, default=[]),
        sa.Column('complexity', sa.Integer, nullable=False, default=1),
        sa.Column('is_async', sa.Boolean, nullable=False, default=False),
        sa.Column('is_exported', sa.Boolean, nullable=False, default=False),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('embedding', postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True, default={}),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_project_functions_file', 'project_functions', ['file_id'])
    op.create_index('ix_project_functions_project', 'project_functions', ['project_id'])
    op.create_index('ix_project_functions_name', 'project_functions', ['name'])
    op.create_index('ix_project_functions_type', 'project_functions', ['type'])

    # Create ide_sessions table
    op.create_table(
        'ide_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('ide_name', sa.String(100), nullable=False),
        sa.Column('ide_version', sa.String(50), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('model_provider', sa.String(100), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('machine_id', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_ide_sessions_project', 'ide_sessions', ['project_id'])
    op.create_index('ix_ide_sessions_ide', 'ide_sessions', ['ide_name'])
    op.create_index('ix_ide_sessions_model', 'ide_sessions', ['model_name'])
    op.create_index('ix_ide_sessions_active', 'ide_sessions', ['is_active'])

    # Create change_logs table
    op.create_table(
        'change_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ide_session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ide_sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_files.id', ondelete='SET NULL'), nullable=True),
        sa.Column('change_type', sa.String(50), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('old_content', sa.Text, nullable=True),
        sa.Column('new_content', sa.Text, nullable=True),
        sa.Column('diff', sa.Text, nullable=True),
        sa.Column('lines_added', sa.Integer, nullable=False, default=0),
        sa.Column('lines_removed', sa.Integer, nullable=False, default=0),
        sa.Column('commit_hash', sa.String(64), nullable=True),
        sa.Column('commit_message', sa.Text, nullable=True),
        sa.Column('branch_name', sa.String(255), nullable=True),
        sa.Column('ide_name', sa.String(100), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('model_provider', sa.String(100), nullable=True),
        sa.Column('prompt_used', sa.Text, nullable=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_change_logs_project', 'change_logs', ['project_id'])
    op.create_index('ix_change_logs_session', 'change_logs', ['ide_session_id'])
    op.create_index('ix_change_logs_file', 'change_logs', ['file_id'])
    op.create_index('ix_change_logs_type', 'change_logs', ['change_type'])
    op.create_index('ix_change_logs_created', 'change_logs', ['created_at'])
    op.create_index('ix_change_logs_commit', 'change_logs', ['commit_hash'])


def downgrade() -> None:
    op.drop_table('change_logs')
    op.drop_table('ide_sessions')
    op.drop_table('project_functions')
    op.drop_table('project_files')
    op.drop_table('project_modules')
