from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, Approval, Asset, Audit, AuditFinding, BrandGuideline

router = APIRouter(prefix='/api', tags=['dashboard'])


@router.get('/dashboard/stats')
def dashboard_stats(
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    total_assets = db.query(Asset).filter(Asset.user_id == user_id).count()
    total_audits = db.query(Audit).filter(Audit.user_id == user_id).count()
    pending_approvals = db.query(Approval).filter(
        Approval.user_id == user_id,
        Approval.decision.ilike('pending'),
    ).count()
    high_risk_findings = db.query(AuditFinding).filter(
        AuditFinding.user_id == user_id,
        AuditFinding.severity.ilike('high'),
    ).count()
    total_guidelines = db.query(BrandGuideline).filter(BrandGuideline.user_id == user_id).count()

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
    db: Session = Depends(get_db),
    limit: int = 5,
):
    activity = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.user_id == user_id)
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
def risk_distribution(user_id: str = Depends(require_firebase_user), db: Session = Depends(get_db)):
    counts = (
        db.query(Audit.risk_category, func.count(Audit.id))
        .filter(Audit.user_id == user_id)
        .group_by(Audit.risk_category)
        .all()
    )
    result = {'low': 0, 'medium': 0, 'high': 0}
    for key, value in counts:
        if key in result:
            result[key] = value
    return result
