from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, Approval, Audit
from ..schemas import ApprovalCreate, ApprovalOut, ApprovalUpdate, ApprovalWorkspaceOut
from ..services.workspace_service import WorkspaceAccess
from ..workspace_auth import require_workspace_access

router = APIRouter(prefix='/api', tags=['approvals'], dependencies=[Depends(require_workspace_access)])


def _apply_decision(
    approval: Approval,
    decision: str,
    comment: str | None,
    user_id: str,
    access: WorkspaceAccess,
    db: Session,
) -> Approval:
    audit = db.query(Audit).filter(
        Audit.id == approval.audit_id,
        Audit.workspace_id == access.workspace_id,
    ).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    action_labels = {
        'approved': ('Campaign approved', 'approved'),
        'rejected': ('Campaign rejected', 'rejected'),
        'changes_requested': ('Changes requested', 'changes requested'),
    }
    event_type, action = action_labels[decision]

    try:
        changed = db.query(Approval).filter(
            Approval.id == approval.id,
            Approval.workspace_id == access.workspace_id,
            Approval.decision == 'pending',
        ).update(
            {
                Approval.decision: decision,
                Approval.comment: comment,
                Approval.decision_timestamp: datetime.now(timezone.utc).replace(tzinfo=None),
            },
            synchronize_session=False,
        )
        if changed != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='This approval has already been decided.',
            )

        audit.audit_status = decision
        db.add(ActivityEvent(
            event_type=event_type,
            description=f'Audit {audit.id} {action}',
            related_entity_id=str(audit.id),
            user_id=user_id,
            workspace_id=access.workspace_id,
        ))
        db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Approval update could not be saved.',
        ) from error

    db.refresh(approval)
    return approval


@router.get('/approvals', response_model=list[ApprovalOut])
def list_approvals(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    return (
        db.query(Approval)
        .filter(Approval.workspace_id == access.workspace_id)
        .order_by(Approval.decision_timestamp.desc())
        .all()
    )


@router.get('/approvals/workspace', response_model=list[ApprovalWorkspaceOut])
def list_workspace_approvals(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    records = (
        db.query(Approval, Audit)
        .join(Audit, Audit.id == Approval.audit_id)
        .filter(Approval.workspace_id == access.workspace_id, Audit.workspace_id == access.workspace_id)
        .order_by(Approval.decision_timestamp.desc())
        .all()
    )
    return [
        {
            'id': approval.id,
            'audit_id': approval.audit_id,
            'decision': approval.decision,
            'reviewer': approval.reviewer,
            'comment': approval.comment,
            'decision_timestamp': approval.decision_timestamp,
            'campaign_name': audit.campaign_name,
            'risk_level': audit.risk_category,
            'asset_count': 0,
        }
        for approval, audit in records
    ]


@router.patch('/approvals/{approval_id}', response_model=ApprovalOut)
def update_approval(
    approval_id: int,
    payload: ApprovalUpdate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    approval = db.query(Approval).filter(
        Approval.id == approval_id,
        Approval.workspace_id == access.workspace_id,
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail='Approval not found')

    return _apply_decision(approval, payload.decision, payload.comment, user_id, access, db)


@router.post('/audits/{audit_id}/approve', response_model=ApprovalOut)
def approve_audit(
    audit_id: int,
    payload: ApprovalCreate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.workspace_id == access.workspace_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    approval = db.query(Approval).filter(
        Approval.audit_id == audit.id,
        Approval.workspace_id == access.workspace_id,
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail='Approval not found')
    return _apply_decision(approval, 'approved', payload.comment, user_id, access, db)


@router.post('/audits/{audit_id}/reject', response_model=ApprovalOut)
def reject_audit(
    audit_id: int,
    payload: ApprovalCreate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.workspace_id == access.workspace_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    approval = db.query(Approval).filter(
        Approval.audit_id == audit.id,
        Approval.workspace_id == access.workspace_id,
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail='Approval not found')
    return _apply_decision(approval, 'rejected', payload.comment, user_id, access, db)


@router.post('/audits/{audit_id}/request-changes', response_model=ApprovalOut)
def request_changes(
    audit_id: int,
    payload: ApprovalCreate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.workspace_id == access.workspace_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail='Audit not found')

    approval = db.query(Approval).filter(
        Approval.audit_id == audit.id,
        Approval.workspace_id == access.workspace_id,
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail='Approval not found')
    return _apply_decision(approval, 'changes_requested', payload.comment, user_id, access, db)
