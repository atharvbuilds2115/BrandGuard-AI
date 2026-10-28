from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(prefix='/api', tags=['health'])


@router.get('/health')
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        db_status = 'connected'
    except Exception:
        db_status = 'disconnected'

    return {
        'status': 'ok',
        'database': db_status,
        'timestamp': datetime.utcnow().isoformat(),
    }
