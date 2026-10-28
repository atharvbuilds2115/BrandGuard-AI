from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin.exceptions import FirebaseError

bearer_scheme = HTTPBearer(auto_error=False)
_app_lock = Lock()


def _firebase_admin_app() -> firebase_admin.App:
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    with _app_lock:
        try:
            return firebase_admin.get_app()
        except ValueError:
            service_account_path = (
                os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
                or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            )
            options: dict[str, str] = {}
            project_id = os.getenv('FIREBASE_PROJECT_ID')
            if project_id:
                options['projectId'] = project_id

            try:
                if service_account_path:
                    path = Path(service_account_path).expanduser()
                    if not path.is_file():
                        raise RuntimeError('The configured Firebase service-account file does not exist.')
                    credential = credentials.Certificate(str(path))
                    return firebase_admin.initialize_app(credential, options=options)
                return firebase_admin.initialize_app(options=options)
            except RuntimeError:
                raise
            except Exception as error:
                raise RuntimeError(
                    'Firebase Admin credentials are not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH '
                    'or configure Application Default Credentials.'
                ) from error


def require_firebase_user(
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if authorization is None or authorization.scheme.lower() != 'bearer':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='A valid Firebase ID token is required.',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    try:
        app = _firebase_admin_app()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    try:
        decoded_token: dict[str, Any] = firebase_auth.verify_id_token(
            authorization.credentials,
            app=app,
            check_revoked=True,
        )
    except (FirebaseError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token is invalid, expired, or revoked.',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error

    user_id = decoded_token.get('uid')
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token did not contain a valid user ID.',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return user_id
