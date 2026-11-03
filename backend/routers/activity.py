from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent
from ..schemas import ActivityCreate, ActivityOut
from ..services.workspace_service import WorkspaceAccess
from ..workspace_auth import require_workspace_access

router = APIRouter(prefix='/api', tags=['activity'], dependencies=[Depends(require_workspace_access)])


@router.post('/activity', response_model=ActivityOut, status_code=201)
def create_activity(
    payload: ActivityCreate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    event = ActivityEvent(
        event_type=payload.event_type,
        description=payload.description,
        related_entity_id=payload.related_entity_id,
        user_id=user_id,
        workspace_id=access.workspace_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get('/activity')
def list_activity(
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    events = (
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
        for event in events
    ]
