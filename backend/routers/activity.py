from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent

router = APIRouter(prefix='/api', tags=['activity'])


@router.get('/activity')
def list_activity(
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    events = (
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
        for event in events
    ]
