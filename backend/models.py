from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserProfile(Base):
    __tablename__ = 'user_profiles'

    uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), default='', nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default='', nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class CompanyWorkspace(Base):
    __tablename__ = 'company_workspaces'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    personal_owner_uid: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class WorkspaceMembership(Base):
    __tablename__ = 'workspace_memberships'

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey('company_workspaces.id'),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default='member')
    app_role: Mapped[str] = mapped_column(String(24), nullable=False, default='creator')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class WorkspaceInvitation(Base):
    __tablename__ = 'workspace_invitations'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('company_workspaces.id'), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default='member')
    app_role: Mapped[str] = mapped_column(String(24), nullable=False, default='creator')
    invited_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='pending')
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class GuidelineHistory(Base):
    __tablename__ = 'guideline_history'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('company_workspaces.id'), nullable=False, index=True)
    guideline_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    document_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class GuidelineDocument(Base):
    __tablename__ = 'guideline_documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    model_used: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='pending_review')


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
    source_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('guideline_documents.id'),
        nullable=True,
    )
    source_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requirement_type: Mapped[str] = mapped_column(String(16), default='guidance', nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )
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
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )


class Audit(Base):
    __tablename__ = 'audits'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_name: Mapped[str] = mapped_column(String(120), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_content: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_category: Mapped[str] = mapped_column(String(30), default='low')
    audit_status: Mapped[str] = mapped_column(String(30), default='draft')
    analysis_mode: Mapped[str] = mapped_column(String(32), default='rules_only', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )

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
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )

    audit: Mapped['Audit'] = relationship(back_populates='findings')
    guideline: Mapped[Optional['BrandGuideline']] = relationship(back_populates='findings')


class VideoReview(Base):
    __tablename__ = 'video_reviews'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_category: Mapped[str] = mapped_column(String(30), default='low', nullable=False)
    compliance_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    analysis_mode: Mapped[str] = mapped_column(String(32), default='gemini_assisted', nullable=False)
    findings: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )


class ConsistencyReport(Base):
    __tablename__ = 'consistency_reports'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    audit_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    campaign_count: Mapped[int] = mapped_column(Integer, nullable=False)
    report_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )


class Approval(Base):
    __tablename__ = 'approvals'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey('audits.id'), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(80), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_reviewer_uid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    decision_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )

    audit: Mapped['Audit'] = relationship(back_populates='approvals')


class ActivityEvent(Base):
    __tablename__ = 'activity_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('company_workspaces.id'),
        nullable=True,
        index=True,
    )
