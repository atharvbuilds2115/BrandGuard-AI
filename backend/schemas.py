from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GuidelineCreate(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = None
    rule_value: str = Field(..., min_length=1)
    severity: str = 'medium'
    active: bool = True


class GuidelineUpdate(BaseModel):
    rule_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = None
    rule_value: Optional[str] = Field(default=None, min_length=1)
    severity: Optional[str] = None
    active: Optional[bool] = None


class GuidelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_name: str
    category: str
    description: Optional[str]
    rule_value: str
    severity: str
    active: bool
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
    created_at: datetime
    findings: list[AuditFindingOut] = []


class AuditCreate(BaseModel):
    campaign_name: str = Field(..., min_length=1)
    campaign_type: str = Field(..., min_length=1)
    submitted_content: str = Field(..., min_length=1)
    asset_ids: list[int] = []


class ApprovalCreate(BaseModel):
    reviewer: str = Field(..., min_length=1)
    comment: Optional[str] = None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: int
    decision: str
    reviewer: str
    comment: Optional[str]
    decision_timestamp: datetime


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    description: str
    related_entity_id: Optional[str]
    timestamp: datetime


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
