from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv(Path(__file__).resolve().parent / '.env')

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./brandguard.db')
engine = create_engine(
    DATABASE_URL,
    connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    from . import models

    models.Base.metadata.create_all(bind=engine)
    _migrate_workspace_roles(engine)
    user_owned_tables = (
        'brand_guidelines',
        'guideline_documents',
        'assets',
        'audits',
        'audit_findings',
        'approvals',
        'activity_events',
        'video_reviews',
        'consistency_reports',
    )
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name in user_owned_tables:
            columns = {column['name'] for column in inspector.get_columns(table_name)}
            if 'user_id' not in columns:
                connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN user_id VARCHAR(128)'))
            if 'workspace_id' not in columns:
                connection.execute(
                    text(f'ALTER TABLE {table_name} ADD COLUMN workspace_id VARCHAR(36) REFERENCES company_workspaces(id)')
                )
            if table_name == 'audits' and 'analysis_mode' not in columns:
                connection.execute(
                    text("ALTER TABLE audits ADD COLUMN analysis_mode VARCHAR(32) NOT NULL DEFAULT 'rules_only'")
                )
            if table_name == 'approvals' and 'assigned_reviewer_uid' not in columns:
                connection.execute(
                    text('ALTER TABLE approvals ADD COLUMN assigned_reviewer_uid VARCHAR(128)')
                )
                connection.execute(
                    text(
                        'CREATE INDEX IF NOT EXISTS ix_approvals_assigned_reviewer_uid '
                        'ON approvals (assigned_reviewer_uid)'
                    )
                )
            if table_name == 'video_reviews':
                if 'risk_score' not in columns:
                    connection.execute(text('ALTER TABLE video_reviews ADD COLUMN risk_score INTEGER NOT NULL DEFAULT 0'))
                if 'risk_category' not in columns:
                    connection.execute(text("ALTER TABLE video_reviews ADD COLUMN risk_category VARCHAR(30) NOT NULL DEFAULT 'low'"))
                if 'compliance_score' not in columns:
                    connection.execute(text('ALTER TABLE video_reviews ADD COLUMN compliance_score INTEGER NOT NULL DEFAULT 100'))
                if 'model_used' not in columns:
                    connection.execute(text('ALTER TABLE video_reviews ADD COLUMN model_used VARCHAR(100)'))
                if 'fallback_used' not in columns:
                    connection.execute(text('ALTER TABLE video_reviews ADD COLUMN fallback_used BOOLEAN NOT NULL DEFAULT 0'))
            if table_name == 'brand_guidelines':
                if 'source_document_id' not in columns:
                    connection.execute(
                        text('ALTER TABLE brand_guidelines ADD COLUMN source_document_id INTEGER REFERENCES guideline_documents(id)')
                    )
                if 'source_reference' not in columns:
                    connection.execute(text('ALTER TABLE brand_guidelines ADD COLUMN source_reference VARCHAR(120)'))
                if 'source_excerpt' not in columns:
                    connection.execute(text('ALTER TABLE brand_guidelines ADD COLUMN source_excerpt TEXT'))
                if 'requirement_type' not in columns:
                    connection.execute(
                        text("ALTER TABLE brand_guidelines ADD COLUMN requirement_type VARCHAR(16) NOT NULL DEFAULT 'guidance'")
                    )
            if table_name == 'guideline_documents' and 'status' not in columns:
                connection.execute(
                    text("ALTER TABLE guideline_documents ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'approved'")
                )
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS ix_{table_name}_user_id ON {table_name} (user_id)')
            )
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS ix_{table_name}_workspace_id ON {table_name} (workspace_id)')
            )

    _backfill_personal_workspaces(user_owned_tables, engine)


def _migrate_workspace_roles(target_engine) -> None:
    inspector = inspect(target_engine)
    membership_columns = {column['name'] for column in inspector.get_columns('workspace_memberships')}
    invitation_columns = {column['name'] for column in inspector.get_columns('workspace_invitations')}
    with target_engine.begin() as connection:
        if 'app_role' not in membership_columns:
            connection.execute(
                text("ALTER TABLE workspace_memberships ADD COLUMN app_role VARCHAR(24) NOT NULL DEFAULT 'creator'")
            )
            connection.execute(
                text("UPDATE workspace_memberships SET app_role = 'brand_admin' WHERE role IN ('owner', 'admin')")
            )
        if 'app_role' not in invitation_columns:
            connection.execute(
                text("ALTER TABLE workspace_invitations ADD COLUMN app_role VARCHAR(24) NOT NULL DEFAULT 'creator'")
            )
            connection.execute(
                text("UPDATE workspace_invitations SET app_role = 'brand_admin' WHERE role = 'admin'")
            )


def _backfill_personal_workspaces(user_owned_tables: tuple[str, ...], target_engine) -> None:
    from uuid import uuid4

    from .models import CompanyWorkspace, UserProfile, WorkspaceMembership

    migration_session = sessionmaker(autocommit=False, autoflush=False, bind=target_engine)
    db = migration_session()
    try:
        user_ids = {row[0] for row in db.query(UserProfile.uid).all() if row[0]}
        for table_name in user_owned_tables:
            rows = db.execute(
                text(f'SELECT DISTINCT user_id FROM {table_name} WHERE user_id IS NOT NULL')
            ).all()
            user_ids.update(row[0] for row in rows if row[0])

        for user_id in user_ids:
            workspace = db.query(CompanyWorkspace).filter(
                CompanyWorkspace.personal_owner_uid == user_id,
            ).first()
            if workspace is None:
                workspace = CompanyWorkspace(
                    id=str(uuid4()),
                    name='Personal workspace',
                    personal_owner_uid=user_id,
                )
                db.add(workspace)
                db.flush()
            membership = db.query(WorkspaceMembership).filter(
                WorkspaceMembership.workspace_id == workspace.id,
                WorkspaceMembership.user_id == user_id,
            ).first()
            if membership is None:
                db.add(WorkspaceMembership(
                    workspace_id=workspace.id,
                    user_id=user_id,
                    role='member',
                    app_role='creator',
                ))
            for table_name in user_owned_tables:
                db.execute(
                    text(
                        f'UPDATE {table_name} SET workspace_id = :workspace_id '
                        'WHERE user_id = :user_id AND workspace_id IS NULL'
                    ),
                    {'workspace_id': workspace.id, 'user_id': user_id},
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
