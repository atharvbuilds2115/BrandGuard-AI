from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationSettings(BaseModel):
    approvals: bool = True
    guidelineChanges: bool = True
    auditResults: bool = True


class ReviewPreferenceSettings(BaseModel):
    defaultRiskThreshold: str = 'Medium'
    requireManualReview: bool = True
    autoSaveResults: bool = True


class WorkspaceSettingsPayload(BaseModel):
    workspaceName: str = 'BrandGuard AI Workspace'
    brandName: str = 'BrandGuard AI'
    logoUrl: str = ''
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    reviewPreferences: ReviewPreferenceSettings = Field(default_factory=ReviewPreferenceSettings)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    email: str
    display_name: str
    settings: WorkspaceSettingsPayload
    created_at: datetime
    updated_at: datetime


class ProfileSettingsUpdate(BaseModel):
    settings: WorkspaceSettingsPayload


class GuidelineCreate(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = None
    rule_value: str = Field(..., min_length=1)
    severity: str = 'medium'
    active: bool = True
    requirement_type: Literal['required', 'prohibited', 'guidance'] = 'guidance'


class GuidelineUpdate(BaseModel):
    rule_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = None
    rule_value: Optional[str] = Field(default=None, min_length=1)
    severity: Optional[str] = None
    active: Optional[bool] = None
    requirement_type: Optional[Literal['required', 'prohibited', 'guidance']] = None


class GuidelineImportRule(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1, max_length=2000)
    rule_value: str = Field(..., min_length=1, max_length=2000)
    requirement_type: Literal['required', 'prohibited', 'guidance']
    severity: Literal['low', 'medium', 'high'] = 'medium'
    source_reference: str = Field(..., min_length=1, max_length=120)
    source_excerpt: str = Field(..., min_length=1, max_length=1000)


class GuidelineImportSave(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    original_filename: str = Field(..., min_length=1, max_length=255)
    provider: Literal['gemini', 'groq']
    model_used: str = Field(..., min_length=1, max_length=120)
    document_id: Optional[int] = None
    rules: list[GuidelineImportRule] = Field(..., min_length=1, max_length=40)


class GuidelineImportDocumentOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    original_filename: str
    provider: str
    model_used: str
    created_at: datetime
    rules_saved: int


class GuidelineImportSaveOut(GuidelineImportDocumentOut):
    guidelines: list[GuidelineOut]


class GuidelineExtractionRule(GuidelineImportRule):
    manual_review: bool = False
    potential_duplicate: bool = False


class GuidelineExtractionOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    original_filename: str
    provider: Literal['gemini', 'groq']
    model_used: str
    document_id: int
    rules: list[GuidelineExtractionRule]


class GuidelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_name: str
    category: str
    description: Optional[str]
    rule_value: str
    severity: str
    active: bool
    source_document_id: Optional[int] = None
    source_reference: Optional[str] = None
    source_excerpt: Optional[str] = None
    requirement_type: Literal['required', 'prohibited', 'guidance'] = 'guidance'
    created_at: datetime
    updated_at: datetime


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    stored_filename: str
    mime_type: str
    file_size: int
    campaign_name: Optional[str]
    tags: str
    extracted_text: Optional[str]
    uploaded_at: datetime
    review_status: str
    file_path: str


class AssetUpdate(BaseModel):
    campaign_name: Optional[str] = None
    tags: Optional[str] = None
    review_status: Optional[str] = None


class AuditFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: int
    finding_title: str
    severity: str
    evidence_text: str
    explanation: str
    related_guideline_id: Optional[int]
    suggested_correction: str
    finding_status: str
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_name: str
    campaign_type: str
    submitted_content: str
    risk_score: int
    risk_category: str
    audit_status: str
    analysis_mode: Literal['rules_only', 'gemini_assisted', 'groq_assisted'] = 'rules_only'
    created_at: datetime
    findings: list[AuditFindingOut] = []
    approval_id: Optional[int] = None


class AuditCreate(BaseModel):
    campaign_name: str = Field(..., min_length=1, max_length=120)
    campaign_type: str = Field(..., min_length=1, max_length=40)
    submitted_content: str = Field(..., min_length=1, max_length=50000)
    asset_ids: list[int] = []


class VideoReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    original_filename: str
    duration_seconds: float
    frame_count: int
    risk_score: int
    risk_category: Literal['low', 'medium', 'high']
    compliance_score: int
    model_used: Optional[str] = None
    fallback_used: bool = False
    analysis_mode: Literal['gemini_assisted', 'groq_assisted', 'demo_sample']
    findings: list[dict]
    created_at: datetime


class ConsistencyReportCreate(BaseModel):
    audit_ids: list[int] = Field(..., min_length=2, max_length=50)


class ConsistencyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_ids: list[int]
    campaign_count: int
    report_data: dict
    created_at: datetime


class ApprovalCreate(BaseModel):
    reviewer: str = Field(..., min_length=1)
    comment: Optional[str] = None


class ApprovalUpdate(BaseModel):
    decision: Literal['approved', 'rejected', 'changes_requested']
    comment: Optional[str] = None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: int
    decision: str
    reviewer: str
    comment: Optional[str]
    decision_timestamp: datetime


class ApprovalWorkspaceOut(ApprovalOut):
    campaign_name: str
    risk_level: str
    asset_count: int = 0


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    description: str
    related_entity_id: Optional[str]
    timestamp: datetime


class ActivityCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1)
    related_entity_id: Optional[str] = None


class DashboardStatOut(BaseModel):
    total_assets: int
    total_audits: int
    pending_approvals: int
    high_risk_findings: int
    total_guidelines: int


class RiskDistributionOut(BaseModel):
    low: int
    medium: int
    high: int


class HealthOut(BaseModel):
    status: str
    database: str
    timestamp: datetime


class GlobalSearchResultOut(BaseModel):
    category: Literal['Campaign', 'Asset', 'Guideline']
    id: int
    name: str
    description: str
