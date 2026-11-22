from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, Approval, Asset, Audit, AuditFinding, BrandGuideline
from ..services.workspace_service import WorkspaceAccess, require_app_role
from ..workspace_auth import require_workspace_access

router = APIRouter(prefix='/api', tags=['dashboard'], dependencies=[Depends(require_workspace_access)])


@router.get('/dashboard/stats')
def dashboard_stats(
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    total_assets = db.query(Asset).filter(Asset.workspace_id == access.workspace_id).count()
    audit_query = db.query(Audit).filter(Audit.workspace_id == access.workspace_id)
    if access.app_role == 'reviewer':
        assigned_audit_ids = db.query(Approval.audit_id).filter(
            Approval.workspace_id == access.workspace_id,
            Approval.assigned_reviewer_uid == access.user_id,
        )
        audit_query = audit_query.filter(Audit.id.in_(assigned_audit_ids))
    total_audits = audit_query.count()
    approvals_query = db.query(Approval).filter(
        Approval.workspace_id == access.workspace_id,
        Approval.decision.ilike('pending'),
    )
    if access.app_role == 'reviewer':
        approvals_query = approvals_query.filter(Approval.assigned_reviewer_uid == access.user_id)
    pending_approvals = approvals_query.count()
    findings_query = db.query(AuditFinding).join(
        Audit,
        Audit.id == AuditFinding.audit_id,
    ).filter(
        AuditFinding.workspace_id == access.workspace_id,
        AuditFinding.severity.ilike('high'),
    )
    if access.app_role == 'reviewer':
        findings_query = findings_query.filter(Audit.id.in_(assigned_audit_ids))
    high_risk_findings = findings_query.count()
    total_guidelines = db.query(BrandGuideline).filter(BrandGuideline.workspace_id == access.workspace_id).count()

    return {
        'total_assets': total_assets,
        'total_audits': total_audits,
        'pending_approvals': pending_approvals,
        'high_risk_findings': high_risk_findings,
        'total_guidelines': total_guidelines,
    }


@router.get('/dashboard/recent-activity')
def recent_activity(
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
    limit: int = 5,
):
    require_app_role(access, 'brand_admin')
    activity = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.workspace_id == access.workspace_id)
        .order_by(ActivityEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            'id': event.id,
            'event_type': event.event_type,
            'description': event.description,
            'related_entity_id': event.related_entity_id,
            'timestamp': event.timestamp.isoformat(),
        }
        for event in activity
    ]


@router.get('/dashboard/risk-distribution')
def risk_distribution(
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Audit.risk_category, func.count(Audit.id))
        .filter(Audit.workspace_id == access.workspace_id)
    )
    if access.app_role == 'reviewer':
        assigned_audit_ids = db.query(Approval.audit_id).filter(
            Approval.workspace_id == access.workspace_id,
            Approval.assigned_reviewer_uid == access.user_id,
        )
        query = query.filter(Audit.id.in_(assigned_audit_ids))
    counts = query.group_by(Audit.risk_category).all()
    result = {'low': 0, 'medium': 0, 'high': 0}
    for key, value in counts:
        if key in result:
            result[key] = value
    return result
