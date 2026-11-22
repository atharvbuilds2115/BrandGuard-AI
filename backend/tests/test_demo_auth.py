from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth as firebase_auth

from backend import auth
from backend.routers import demo_auth


@pytest.fixture(autouse=True)
def clear_role_demo_emails(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        'DEMO_CREATOR_EMAIL',
        'DEMO_REVIEWER_EMAIL',
        'DEMO_AGENCY_EMAIL',
        'DEMO_ADMIN_EMAIL',
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(demo_auth.router)
    monkeypatch.setattr(demo_auth, '_request_timestamps', {})
    with TestClient(app) as test_client:
        yield test_client


def test_demo_token_uses_configured_account_and_returns_custom_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_app = object()
    user = SimpleNamespace(uid='configured-demo-uid', disabled=False)
    get_user = Mock(return_value=user)
    create_token = Mock(return_value=b'synthetic-custom-token')
    monkeypatch.setenv('DEMO_ACCOUNT_EMAIL', 'demo@example.test')
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: admin_app)
    monkeypatch.setattr(firebase_auth, 'get_user_by_email', get_user)
    monkeypatch.setattr(firebase_auth, 'create_custom_token', create_token)

    response = client.post('/api/auth/demo-token')

    assert response.status_code == 200
    assert response.json() == {'custom_token': 'synthetic-custom-token'}
    assert response.headers['cache-control'] == 'no-store'
    get_user.assert_called_once_with('demo@example.test', app=admin_app)
    create_token.assert_called_once_with(
        'configured-demo-uid',
        developer_claims={
            'brandguard_demo': True,
            'demo_role': 'creator',
            'app_role': 'creator',
        },
        app=admin_app,
    )


def test_demo_token_rejects_missing_demo_email(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('DEMO_ACCOUNT_EMAIL', raising=False)
    get_admin_app = Mock(side_effect=AssertionError('Firebase Admin must not initialize'))
    monkeypatch.setattr(auth, '_firebase_admin_app', get_admin_app)

    response = client.post('/api/auth/demo-token')

    assert response.status_code == 503
    assert response.json() == {
        'detail': 'Demo sign-in is not configured. Set DEMO_CREATOR_EMAIL in the backend environment.',
    }
    get_admin_app.assert_not_called()


@pytest.mark.parametrize(
    ('role', 'email_env'),
    [
        ('creator', 'DEMO_CREATOR_EMAIL'),
        ('reviewer', 'DEMO_REVIEWER_EMAIL'),
        ('agency_partner', 'DEMO_AGENCY_EMAIL'),
        ('brand_admin', 'DEMO_ADMIN_EMAIL'),
    ],
)
def test_role_demo_token_identifies_missing_configuration_without_logging_secrets(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    role: str,
    email_env: str,
) -> None:
    response = client.post(f'/api/auth/demo-token/{role}')

    assert response.status_code == 503
    assert response.json() == {
        'detail': f'Demo sign-in is not configured. Set {email_env} in the backend environment.',
    }
    assert f'{email_env} is not set for role {role}' in caplog.text
    assert '@' not in caplog.text


def test_demo_token_rejects_unknown_firebase_account(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('DEMO_ACCOUNT_EMAIL', 'missing@example.test')
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())
    monkeypatch.setattr(
        firebase_auth,
        'get_user_by_email',
        Mock(side_effect=firebase_auth.UserNotFoundError('synthetic missing user')),
    )
    create_token = Mock()
    monkeypatch.setattr(firebase_auth, 'create_custom_token', create_token)

    response = client.post('/api/auth/demo-token')

    assert response.status_code == 404
    assert response.json() == {'detail': 'The configured demo account could not be found.'}
    create_token.assert_not_called()


def test_demo_token_rejects_disabled_firebase_account(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('DEMO_ACCOUNT_EMAIL', 'disabled@example.test')
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())
    monkeypatch.setattr(
        firebase_auth,
        'get_user_by_email',
        Mock(return_value=SimpleNamespace(uid='disabled-demo-uid', disabled=True)),
    )
    create_token = Mock()
    monkeypatch.setattr(firebase_auth, 'create_custom_token', create_token)

    response = client.post('/api/auth/demo-token')

    assert response.status_code == 403
    assert response.json() == {'detail': 'The configured demo account is disabled.'}
    create_token.assert_not_called()


def test_demo_token_endpoint_rejects_body_that_could_select_an_account(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('DEMO_ACCOUNT_EMAIL', 'demo@example.test')
    get_user = Mock()
    create_token = Mock()
    monkeypatch.setattr(firebase_auth, 'get_user_by_email', get_user)
    monkeypatch.setattr(firebase_auth, 'create_custom_token', create_token)

    response = client.post(
        '/api/auth/demo-token',
        json={
            'email': 'attacker@example.test',
            'uid': 'attacker-selected-uid',
            'password': 'synthetic-test-password',
        },
    )

    assert response.status_code == 400
    assert response.json() == {'detail': 'This endpoint does not accept a request body.'}
    get_user.assert_not_called()
    create_token.assert_not_called()


def test_demo_token_endpoint_limits_requests_per_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('DEMO_ACCOUNT_EMAIL', 'demo@example.test')
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())
    monkeypatch.setattr(
        firebase_auth,
        'get_user_by_email',
        Mock(return_value=SimpleNamespace(uid='configured-demo-uid', disabled=False)),
    )
    monkeypatch.setattr(firebase_auth, 'create_custom_token', Mock(return_value=b'synthetic-token'))

    responses = [client.post('/api/auth/demo-token') for _ in range(6)]

    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200, 429]
    assert responses[-1].json() == {
        'detail': 'Too many demo sign-in requests. Please try again shortly.',
    }


@pytest.mark.parametrize(
    'role',
    ['creator', 'reviewer', 'agency_partner', 'brand_admin'],
)
def test_role_demo_token_uses_server_role_account(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    email_env = {
        'creator': 'DEMO_CREATOR_EMAIL',
        'reviewer': 'DEMO_REVIEWER_EMAIL',
        'agency_partner': 'DEMO_AGENCY_EMAIL',
        'brand_admin': 'DEMO_ADMIN_EMAIL',
    }[role]
    monkeypatch.setenv(email_env, f'{role}@example.test')
    admin_app = object()
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: admin_app)
    monkeypatch.setattr(
        firebase_auth,
        'get_user_by_email',
        Mock(return_value=SimpleNamespace(uid=f'{role}-uid', disabled=False)),
    )
    monkeypatch.setattr(
        firebase_auth,
        'create_custom_token',
        Mock(return_value=b'synthetic-token'),
    )

    response = client.post(f'/api/auth/demo-token/{role}')

    assert response.status_code == 200
    firebase_auth.create_custom_token.assert_called_with(
        f'{role}-uid',
        developer_claims={
            'brandguard_demo': True,
            'demo_role': role,
            'app_role': role,
        },
        app=admin_app,
    )
