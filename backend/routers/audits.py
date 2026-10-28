from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, Audit, AuditFinding
from ..schemas import AuditCreate, AuditOut
from ..services.audit_service import run_audit_engine

router = APIRouter(prefix='/api', tags=['audits'])


@router.post('/audits', response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(
    payload: AuditCreate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    score, risk_category, findings = run_audit_engine(
        payload.campaign_name,
        payload.campaign_type,
        payload.submitted_content,
        db,
        user_id,
    )

    audit = Audit(
        campaign_name=payload.campaign_name,
        campaign_type=payload.campaign_type,
        submitted_content=payload.submitted_content,
        risk_score=score,
        risk_category=risk_category,
        audit_status='completed',
        user_id=user_id,
    )
    db.add(audit)
    db.commit(); db.refresh(audit)

    for finding in findings:
        record = AuditFinding(
            audit_id=audit.id,
            finding_title=finding['title'],
            severity=finding['severity'],
            evidence_text=finding['evidence'],
            explanation=finding['explanation'],
            related_guideline_id=finding['guideline_id'],
            suggested_correction=finding['suggestion'],
            finding_status=finding['status'],
            user_id=user_id,
        )
        db.add(record)

    db.add(ActivityEvent(
        event_type='Campaign audit completed',
        description=f'Audit completed for {payload.campaign_name}',
        related_entity_id=str(audit.id),
        user_id=user_id,
    ))
    db.commit(); db.refresh(audit)
    return audit


@router.get('/audits', response_model=list[AuditOut])
def list_audits(
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
    risk_category: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    query = db.query(Audit).filter(Audit.user_id == user_id)
    if risk_category:
        query = query.filter(Audit.risk_category.ilike(risk_category))
    if status:
        query = query.filter(Audit.audit_status.ilike(status))
    return query.order_by(Audit.created_at.desc()).all()


@router.get('/audits/{audit_id}', response_model=AuditOut)
def get_audit(
    audit_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')
    return audit


@router.post('/audits/{audit_id}/rerun', response_model=AuditOut)
def rerun_audit(
    audit_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    score, risk_category, findings = run_audit_engine(
        audit.campaign_name,
        audit.campaign_type,
        audit.submitted_content,
        db,
        user_id,
    )
    audit.risk_score = score
    audit.risk_category = risk_category
    audit.audit_status = 'completed'

    for record in audit.findings:
        db.delete(record)

    for finding in findings:
        db.add(AuditFinding(
            audit_id=audit.id,
            finding_title=finding['title'],
            severity=finding['severity'],
            evidence_text=finding['evidence'],
            explanation=finding['explanation'],
            related_guideline_id=finding['guideline_id'],
            suggested_correction=finding['suggestion'],
            finding_status=finding['status'],
            user_id=user_id,
        ))

    db.add(ActivityEvent(
        event_type='Campaign audit rerun',
        description=f'Audit rerun for {audit.campaign_name}',
        related_entity_id=str(audit.id),
        user_id=user_id,
    ))
    db.commit(); db.refresh(audit)
    return audit


@router.patch('/audits/{audit_id}/findings/{finding_id}', response_model=AuditOut)
def update_finding_status(
    audit_id: int,
    finding_id: int,
    status_value: str,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    finding = db.query(AuditFinding).filter(
        AuditFinding.id == finding_id,
        AuditFinding.audit_id == audit_id,
        AuditFinding.user_id == user_id,
    ).first()
    if not finding:
        raise HTTPException(status_code=404, detail='Finding not found')

    finding.finding_status = status_value
    db.add(ActivityEvent(
        event_type='Finding updated',
        description=f'Finding status updated to {status_value}',
        related_entity_id=str(finding.id),
        user_id=user_id,
    ))
    db.commit(); db.refresh(audit)
    return audit
