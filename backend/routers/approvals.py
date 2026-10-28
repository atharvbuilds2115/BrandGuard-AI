from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, Approval, Audit
from ..schemas import ApprovalCreate, ApprovalOut

router = APIRouter(prefix='/api', tags=['approvals'])


@router.get('/approvals', response_model=list[ApprovalOut])
def list_approvals(user_id: str = Depends(require_firebase_user), db: Session = Depends(get_db)):
    return (
        db.query(Approval)
        .filter(Approval.user_id == user_id)
        .order_by(Approval.decision_timestamp.desc())
        .all()
    )


@router.post('/audits/{audit_id}/approve', response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def approve_audit(
    audit_id: int,
    payload: ApprovalCreate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    approval = Approval(
        audit_id=audit.id,
        decision='approved',
        reviewer=payload.reviewer,
        comment=payload.comment,
        user_id=user_id,
    )
    audit.audit_status = 'approved'
    db.add(approval)
    db.add(ActivityEvent(
        event_type='Campaign approved',
        description=f'Audit {audit.id} approved by {payload.reviewer}',
        related_entity_id=str(audit.id),
        user_id=user_id,
    ))
    db.commit(); db.refresh(approval)
    return approval


@router.post('/audits/{audit_id}/reject', response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def reject_audit(
    audit_id: int,
    payload: ApprovalCreate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    approval = Approval(
        audit_id=audit.id,
        decision='rejected',
        reviewer=payload.reviewer,
        comment=payload.comment,
        user_id=user_id,
    )
    audit.audit_status = 'rejected'
    db.add(approval)
    db.add(ActivityEvent(
        event_type='Campaign rejected',
        description=f'Audit {audit.id} rejected by {payload.reviewer}',
        related_entity_id=str(audit.id),
        user_id=user_id,
    ))
    db.commit(); db.refresh(approval)
    return approval


@router.post('/audits/{audit_id}/request-changes', response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def request_changes(
    audit_id: int,
    payload: ApprovalCreate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    approval = Approval(
        audit_id=audit.id,
        decision='changes_requested',
        reviewer=payload.reviewer,
        comment=payload.comment,
        user_id=user_id,
    )
    audit.audit_status = 'changes_requested'
    db.add(approval)
    db.add(ActivityEvent(
        event_type='Changes requested',
        description=f'Changes requested for audit {audit.id}',
        related_entity_id=str(audit.id),
        user_id=user_id,
    ))
    db.commit(); db.refresh(approval)
    return approval
