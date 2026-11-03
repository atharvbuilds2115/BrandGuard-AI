from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, ConsistencyReport
from ..schemas import ConsistencyReportCreate, ConsistencyReportOut
from ..services.consistency_service import build_consistency_report
from ..services.workspace_service import WorkspaceAccess
from ..workspace_auth import require_workspace_access

router = APIRouter(
    prefix='/api/consistency-reports',
    tags=['consistency reports'],
    dependencies=[Depends(require_workspace_access)],
)


@router.post('', response_model=ConsistencyReportOut, status_code=status.HTTP_201_CREATED)
def create_consistency_report(
    payload: ConsistencyReportCreate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    try:
        report_data = build_consistency_report(db, user_id, payload.audit_ids, access.workspace_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    report = ConsistencyReport(
        audit_ids=payload.audit_ids,
        campaign_count=len(payload.audit_ids),
        report_data=report_data,
        user_id=user_id,
        workspace_id=access.workspace_id,
    )
    db.add(report)
    db.flush()
    db.add(ActivityEvent(
        event_type='Consistency report generated',
        description=f'Consistency report generated from {len(payload.audit_ids)} completed campaign audits',
        related_entity_id=str(report.id),
        user_id=user_id,
        workspace_id=access.workspace_id,
    ))
    db.commit()
    db.refresh(report)
    return report


@router.get('', response_model=list[ConsistencyReportOut])
def list_consistency_reports(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    return db.query(ConsistencyReport).filter(
        ConsistencyReport.workspace_id == access.workspace_id,
    ).order_by(ConsistencyReport.created_at.desc()).limit(100).all()


@router.get('/{report_id}', response_model=ConsistencyReportOut)
def get_consistency_report(
    report_id: int,
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    report = db.query(ConsistencyReport).filter(
        ConsistencyReport.id == report_id,
        ConsistencyReport.workspace_id == access.workspace_id,
    ).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Consistency report not found.')
    return report