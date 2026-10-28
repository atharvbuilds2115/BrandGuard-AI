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
    from .models import ActivityEvent, Approval, Asset, Audit, AuditFinding, BrandGuideline

    Base.metadata.create_all(bind=engine)
    user_owned_tables = (
        'brand_guidelines',
        'assets',
        'audits',
        'audit_findings',
        'approvals',
        'activity_events',
    )
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name in user_owned_tables:
            columns = {column['name'] for column in inspector.get_columns(table_name)}
            if 'user_id' not in columns:
                connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN user_id VARCHAR(128)'))
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS ix_{table_name}_user_id ON {table_name} (user_id)')
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
