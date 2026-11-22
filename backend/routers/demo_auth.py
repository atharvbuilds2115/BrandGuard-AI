from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..auth import (
    FirebaseIdentity,
    create_demo_custom_token,
    is_demo_identity,
    require_firebase_identity,
)
from ..database import get_db
from ..services.demo_workspace import reset_demo_workspace, seed_demo_workspace
from ..workspace_auth import require_workspace_access
from ..services.workspace_service import WorkspaceAccess

router = APIRouter(prefix='/api/auth', tags=['authentication'])

_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_REQUESTS = 5
_request_timestamps: dict[str, deque[float]] = {}
_rate_limit_lock = Lock()


def _check_rate_limit(client_key: str, now: float) -> None:
    with _rate_limit_lock:
        cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
        for key, timestamps in list(_request_timestamps.items()):
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if not timestamps:
                del _request_timestamps[key]

        requests = _request_timestamps.setdefault(client_key, deque())
        if len(requests) >= _RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail='Too many demo sign-in requests. Please try again shortly.',
            )
        requests.append(now)


@router.post('/demo-token')
async def issue_demo_token(request: Request, response: Response) -> dict[str, str]:
    async for chunk in request.stream():
        if chunk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='This endpoint does not accept a request body.',
            )

    client_key = request.client.host if request.client else 'unknown'
    _check_rate_limit(client_key, monotonic())
    response.headers['Cache-Control'] = 'no-store'
    return {'custom_token': create_demo_custom_token()}


@router.post('/demo-token/{role}')
async def issue_role_demo_token(
    role: str,
    request: Request,
    response: Response,
) -> dict[str, str]:
    async for chunk in request.stream():
        if chunk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='This endpoint does not accept a request body.',
            )

    client_key = request.client.host if request.client else 'unknown'
    _check_rate_limit(client_key, monotonic())
    response.headers['Cache-Control'] = 'no-store'
    return {'custom_token': create_demo_custom_token(role)}


@router.post('/demo-reset')
def reset_demo(
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not is_demo_identity(identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only demo accounts can reset demo data.',
        )
    reset_demo_workspace(db, access.workspace_id)
    seed_demo_workspace(db, identity.uid, identity.email, access.app_role)
    return {'status': 'Demo workspace reset'}
