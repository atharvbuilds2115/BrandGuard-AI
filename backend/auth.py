from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import firebase_admin
from google.auth.exceptions import DefaultCredentialsError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin.exceptions import FirebaseError

_LOGGER = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)
_app_lock = Lock()


def _validate_firebase_app(app: firebase_admin.App, expected_project_id: str) -> firebase_admin.App:
    if app.project_id != expected_project_id:
        raise RuntimeError(
            'Firebase Admin project ID does not match FIREBASE_PROJECT_ID. '
            'Use credentials and configuration for the same Firebase project as the web app.'
        )
    return app


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str | None
    display_name: str | None
    email_verified: bool = False
    brandguard_demo: bool = False
    demo_role: str | None = None
    app_role: str | None = None


DEMO_ROLE_EMAIL_ENV = {
    'creator': 'DEMO_CREATOR_EMAIL',
    'reviewer': 'DEMO_REVIEWER_EMAIL',
    'agency_partner': 'DEMO_AGENCY_EMAIL',
    'brand_admin': 'DEMO_ADMIN_EMAIL',
}
_APP_ROLES = set(DEMO_ROLE_EMAIL_ENV)


def is_demo_identity(identity: FirebaseIdentity) -> bool:
    if identity.brandguard_demo:
        return True
    if not identity.email:
        return False
    configured_demo_emails = {
        value.strip().casefold()
        for value in (
            os.getenv('DEMO_ACCOUNT_EMAIL', ''),
            *(os.getenv(name, '') for name in DEMO_ROLE_EMAIL_ENV.values()),
        )
        if value.strip()
    }
    return identity.email.strip().casefold() in configured_demo_emails


def demo_role_for_identity(identity: FirebaseIdentity) -> str:
    for role in (identity.demo_role, identity.app_role):
        if role in _APP_ROLES:
            return role
    if identity.email:
        normalized_email = identity.email.strip().casefold()
        for role, setting in DEMO_ROLE_EMAIL_ENV.items():
            if normalized_email == os.getenv(setting, '').strip().casefold() and os.getenv(setting, '').strip():
                return role
        if normalized_email == os.getenv('DEMO_ACCOUNT_EMAIL', '').strip().casefold() and os.getenv('DEMO_ACCOUNT_EMAIL', '').strip():
            return 'brand_admin'
    return 'creator'


def _firebase_admin_app() -> firebase_admin.App:
    expected_project_id = os.getenv('FIREBASE_PROJECT_ID', '').strip()
    if not expected_project_id:
        raise RuntimeError(
            'FIREBASE_PROJECT_ID is required and must match VITE_FIREBASE_PROJECT_ID.'
        )

    try:
        return _validate_firebase_app(firebase_admin.get_app(), expected_project_id)
    except ValueError:
        pass

    with _app_lock:
        try:
            return _validate_firebase_app(firebase_admin.get_app(), expected_project_id)
        except ValueError:
            service_account_path = (
                os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
                or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            )
            options = {'projectId': expected_project_id}

            try:
                if service_account_path:
                    path = Path(service_account_path).expanduser()
                    if not path.is_file():
                        raise RuntimeError('The configured Firebase service-account file does not exist.')
                    credential = credentials.Certificate(str(path))
                    if credential.project_id != expected_project_id:
                        raise RuntimeError(
                            'The Firebase service-account project_id does not match FIREBASE_PROJECT_ID.'
                        )
                    app = firebase_admin.initialize_app(credential, options=options)
                else:
                    credential = credentials.ApplicationDefault()
                    if credential.project_id != expected_project_id:
                        raise RuntimeError(
                            'The Application Default Credentials project ID does not match FIREBASE_PROJECT_ID.'
                        )
                    app = firebase_admin.initialize_app(credential, options=options)
                return _validate_firebase_app(app, expected_project_id)
            except RuntimeError:
                raise
            except Exception as error:
                raise RuntimeError(
                    'Firebase Admin credentials are not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH '
                    'or configure Application Default Credentials.'
                ) from error


def create_demo_custom_token(role: str = 'creator') -> str:
    if role not in DEMO_ROLE_EMAIL_ENV:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Choose a valid demo role.',
        )

    role_email_env = DEMO_ROLE_EMAIL_ENV[role]
    demo_email = os.getenv(role_email_env, '').strip()
    if role == 'creator' and not demo_email:
        demo_email = os.getenv('DEMO_ACCOUNT_EMAIL', '').strip()
    if not demo_email:
        _LOGGER.warning(
            'Demo sign-in is unavailable: %s is not set for role %s.',
            role_email_env,
            role,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Demo sign-in is not configured. Set {role_email_env} in the backend environment.',
        )

    try:
        app = _firebase_admin_app()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Demo sign-in is temporarily unavailable.',
        ) from error

    try:
        user = firebase_auth.get_user_by_email(demo_email, app=app)
    except firebase_auth.UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='The configured demo account could not be found.',
        ) from error
    except (FirebaseError, DefaultCredentialsError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Demo sign-in is temporarily unavailable.',
        ) from error

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='The configured demo account is disabled.',
        )

    try:
        token = firebase_auth.create_custom_token(
            user.uid,
            developer_claims={
                'brandguard_demo': True,
                'demo_role': role,
                'app_role': role,
            },
            app=app,
        )
    except (FirebaseError, DefaultCredentialsError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Demo sign-in is temporarily unavailable.',
        ) from error

    return token.decode('utf-8') if isinstance(token, bytes) else token


def require_firebase_identity(
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> FirebaseIdentity:
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
    except firebase_auth.ExpiredIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token has expired. Refresh the session and try again.',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error
    except firebase_auth.RevokedIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token has been revoked. Sign in again.',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error
    except firebase_auth.UserDisabledError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='This Firebase account is disabled.',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error
    except firebase_auth.CertificateFetchError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Firebase token verification is temporarily unavailable.',
        ) from error
    except DefaultCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                'Firebase Admin credentials are unavailable. Set FIREBASE_SERVICE_ACCOUNT_PATH '
                'or configure Application Default Credentials.'
            ),
        ) from error
    except firebase_auth.InvalidIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token is invalid or was issued for a different Firebase project.',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token is malformed.',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error
    except FirebaseError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Firebase token verification is temporarily unavailable.',
        ) from error

    user_id = decoded_token.get('uid')
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='The Firebase ID token did not contain a valid user ID.',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    email = decoded_token.get('email')
    display_name = decoded_token.get('name')
    email_verified = decoded_token.get('email_verified')
    brandguard_demo = decoded_token.get('brandguard_demo') is True
    demo_role = decoded_token.get('demo_role')
    app_role = decoded_token.get('app_role')
    return FirebaseIdentity(
        uid=user_id,
        email=email if isinstance(email, str) else None,
        display_name=display_name if isinstance(display_name, str) else None,
        email_verified=email_verified is True,
        brandguard_demo=brandguard_demo,
        demo_role=demo_role if isinstance(demo_role, str) else None,
        app_role=app_role if isinstance(app_role, str) else None,
    )


def require_firebase_user(identity: FirebaseIdentity = Depends(require_firebase_identity)) -> str:
    return identity.uid


def optional_firebase_identity(
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> FirebaseIdentity | None:
    if authorization is None:
        return None
    return require_firebase_identity(authorization)
