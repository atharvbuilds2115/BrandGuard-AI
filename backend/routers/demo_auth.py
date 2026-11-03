from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..auth import create_demo_custom_token

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
