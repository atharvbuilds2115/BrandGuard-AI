from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class BrandGuideline(Base):
    __tablename__ = 'brand_guidelines'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    rule_value: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default='medium')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    findings: Mapped[list['AuditFinding']] = relationship(back_populates='guideline')


class Asset(Base):
    __tablename__ = 'assets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    campaign_name: Mapped[str] = mapped_column(String(120), nullable=True)
    tags: Mapped[str] = mapped_column(Text, default='[]')
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    review_status: Mapped[str] = mapped_column(String(30), default='pending')
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)


class Audit(Base):
    __tablename__ = 'audits'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_name: Mapped[str] = mapped_column(String(120), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_content: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_category: Mapped[str] = mapped_column(String(30), default='low')
    audit_status: Mapped[str] = mapped_column(String(30), default='draft')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    findings: Mapped[list['AuditFinding']] = relationship(back_populates='audit', cascade='all, delete-orphan')
    approvals: Mapped[list['Approval']] = relationship(back_populates='audit', cascade='all, delete-orphan')


class AuditFinding(Base):
    __tablename__ = 'audit_findings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey('audits.id'), nullable=False)
    finding_title: Mapped[str] = mapped_column(String(180), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    related_guideline_id: Mapped[Optional[int]] = mapped_column(ForeignKey('brand_guidelines.id'), nullable=True)
    suggested_correction: Mapped[str] = mapped_column(Text, nullable=False)
    finding_status: Mapped[str] = mapped_column(String(30), default='confirmed')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    audit: Mapped['Audit'] = relationship(back_populates='findings')
    guideline: Mapped[Optional['BrandGuideline']] = relationship(back_populates='findings')


class Approval(Base):
    __tablename__ = 'approvals'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey('audits.id'), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(80), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    audit: Mapped['Audit'] = relationship(back_populates='approvals')


class ActivityEvent(Base):
    __tablename__ = 'activity_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
