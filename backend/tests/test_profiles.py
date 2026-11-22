from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from google.auth.exceptions import DefaultCredentialsError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend import auth
from backend.services import audit_service, gemini_service, groq_service
from backend.auth import FirebaseIdentity, require_firebase_identity
from backend.database import Base, get_db
from backend.models import BrandGuideline, CompanyWorkspace, WorkspaceMembership
from backend.routers.activity import router as activity_router
from backend.routers.approvals import router as approvals_router
from backend.routers.audits import router as audits_router
from backend.routers.guidelines import router as guidelines_router
from backend.routers.profile import router as profile_router


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.delenv('AI_PROVIDER', raising=False)
    monkeypatch.setattr(gemini_service, '_BACKEND_ENV_FILE', tmp_path / 'test.env')
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {'uid': 'verified-user-a'}
    with test_session() as db:
        db.add(CompanyWorkspace(
            id='legacy-workspace',
            name='Legacy workspace',
            personal_owner_uid=identity['uid'],
        ))
        db.add(WorkspaceMembership(
            workspace_id='legacy-workspace',
            user_id=identity['uid'],
            role='owner',
            app_role='brand_admin',
        ))
        db.commit()
    app = FastAPI()
    for router in (profile_router, guidelines_router, audits_router, approvals_router, activity_router):
        app.include_router(router)

    def override_db() -> Iterator[Session]:
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    def override_identity() -> FirebaseIdentity:
        return FirebaseIdentity(
            uid=identity['uid'],
            email=f"{identity['uid']}@example.test",
            display_name='Test Account',
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_firebase_identity] = override_identity
    client = TestClient(app)
    try:
        yield client, identity
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_firebase_identity_verifies_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())

    def verified_claims(token: str, *, app: object, check_revoked: bool) -> dict[str, str]:
        assert token == 'signed-token'
        assert app is not None
        assert check_revoked is True
        return {
            'uid': 'verified-uid',
            'email': 'verified@example.test',
            'name': 'Verified User',
        }

    monkeypatch.setattr(auth.firebase_auth, 'verify_id_token', verified_claims)

    identity = require_firebase_identity(
        HTTPAuthorizationCredentials(scheme='Bearer', credentials='signed-token'),
    )

    assert identity == FirebaseIdentity(
        uid='verified-uid',
        email='verified@example.test',
        display_name='Verified User',
    )


def test_firebase_admin_requires_matching_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'configured-project')
    monkeypatch.setattr(
        auth.firebase_admin,
        'get_app',
        lambda: SimpleNamespace(project_id='different-project'),
    )

    with pytest.raises(RuntimeError, match='does not match FIREBASE_PROJECT_ID'):
        auth._firebase_admin_app()


def test_firebase_admin_requires_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('FIREBASE_PROJECT_ID', raising=False)

    with pytest.raises(RuntimeError, match='FIREBASE_PROJECT_ID is required'):
        auth._firebase_admin_app()


def test_missing_firebase_project_id_fails_protected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('FIREBASE_PROJECT_ID', raising=False)

    with pytest.raises(HTTPException) as error:
        require_firebase_identity(
            HTTPAuthorizationCredentials(scheme='Bearer', credentials='signed-token'),
        )

    assert error.value.status_code == 503


def test_service_account_project_must_match(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    credential_file = tmp_path / 'service-account.json'
    credential_file.write_text('{}', encoding='utf-8')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'configured-project')
    monkeypatch.setenv('FIREBASE_SERVICE_ACCOUNT_PATH', str(credential_file))
    monkeypatch.setattr(
        auth.firebase_admin,
        'get_app',
        lambda: (_ for _ in ()).throw(ValueError('app not initialized')),
    )
    monkeypatch.setattr(
        auth.credentials,
        'Certificate',
        lambda _path: SimpleNamespace(project_id='different-project'),
    )
    with pytest.raises(RuntimeError, match='service-account project_id does not match'):
        auth._firebase_admin_app()


def test_application_default_credentials_project_must_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'configured-project')
    monkeypatch.delenv('FIREBASE_SERVICE_ACCOUNT_PATH', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.setattr(
        auth.firebase_admin,
        'get_app',
        lambda: (_ for _ in ()).throw(ValueError('app not initialized')),
    )
    monkeypatch.setattr(
        auth.credentials,
        'ApplicationDefault',
        lambda: SimpleNamespace(project_id='different-project'),
    )

    with pytest.raises(RuntimeError, match='Application Default Credentials project ID'):
        auth._firebase_admin_app()


def test_invalid_firebase_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())

    def reject_token(token: str, *, app: object, check_revoked: bool) -> dict[str, str]:
        assert token == 'invalid-token'
        assert app is not None
        assert check_revoked is True
        raise ValueError('invalid token')

    monkeypatch.setattr(auth.firebase_auth, 'verify_id_token', reject_token)

    with pytest.raises(HTTPException) as error:
        require_firebase_identity(
            HTTPAuthorizationCredentials(scheme='Bearer', credentials='invalid-token'),
        )

    assert error.value.status_code == 401


@pytest.mark.parametrize(
    ('exception', 'expected_status', 'expected_detail'),
    [
        (auth.firebase_auth.ExpiredIdTokenError('expired', None), 401, 'has expired'),
        (auth.firebase_auth.RevokedIdTokenError('revoked'), 401, 'has been revoked'),
        (
            auth.firebase_auth.InvalidIdTokenError('wrong project'),
            401,
            'different Firebase project',
        ),
        (auth.firebase_auth.UserDisabledError('disabled'), 401, 'account is disabled'),
        (auth.firebase_auth.CertificateFetchError('certificate fetch failed', None), 503, 'temporarily unavailable'),
    ],
)
def test_firebase_token_errors_are_classified(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())

    def reject_token(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise exception

    monkeypatch.setattr(auth.firebase_auth, 'verify_id_token', reject_token)

    with pytest.raises(HTTPException) as error:
        require_firebase_identity(
            HTTPAuthorizationCredentials(scheme='Bearer', credentials='signed-token'),
        )

    assert error.value.status_code == expected_status
    assert expected_detail in error.value.detail


def test_missing_firebase_admin_credentials_return_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, '_firebase_admin_app', lambda: object())

    def credentials_unavailable(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise DefaultCredentialsError('credentials unavailable')

    monkeypatch.setattr(auth.firebase_auth, 'verify_id_token', credentials_unavailable)

    with pytest.raises(HTTPException) as error:
        require_firebase_identity(
            HTTPAuthorizationCredentials(scheme='Bearer', credentials='signed-token'),
        )

    assert error.value.status_code == 503


def test_profile_is_created_and_bound_to_verified_uid(api: tuple[TestClient, dict[str, str]]) -> None:
    client, identity = api
    response = client.get('/api/profile')

    assert response.status_code == 200
    assert response.json()['uid'] == identity['uid']
    assert response.json()['email'] == f"{identity['uid']}@example.test"
    assert response.json()['settings']['workspaceName'] == 'BrandGuard AI Workspace'

    profile = response.json()
    updated = client.put(
        '/api/profile',
        json={
            'uid': 'attacker-supplied-uid',
            'settings': {
                **profile['settings'],
                'workspaceName': 'Verified Workspace',
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()['uid'] == identity['uid']
    assert updated.json()['settings']['workspaceName'] == 'Verified Workspace'
    assert client.get('/api/profile').json()['settings']['workspaceName'] == 'Verified Workspace'


def test_profile_seeds_user_guidelines_and_audits_are_isolated(api: tuple[TestClient, dict[str, str]]) -> None:
    client, identity = api
    assert client.get('/api/profile').status_code == 200

    guideline_response = client.get('/api/guidelines')
    assert guideline_response.status_code == 200
    assert len(guideline_response.json()) > 0
    custom_guideline = client.post(
        '/api/guidelines',
        json={
            'rule_name': 'Private account rule',
            'category': 'prohibited_terms',
            'description': 'Must stay scoped to the signed-in user.',
            'rule_value': 'private phrase',
        },
    )
    assert custom_guideline.status_code == 201

    created = client.post(
        '/api/audits',
        json={
            'campaign_name': 'Test campaign',
            'campaign_type': 'Email',
            'submitted_content': 'Guaranteed results. No risk.',
        },
    )
    assert created.status_code == 201
    assert created.json()['approval_id'] is not None
    assert created.json()['findings']
    assert len(client.get('/api/audits').json()) == 1
    workspace_approvals = client.get('/api/approvals/workspace').json()
    assert len(workspace_approvals) == 1

    updated_approval = client.patch(
        f"/api/approvals/{workspace_approvals[0]['id']}",
        json={'decision': 'approved', 'comment': 'Approved for release.'},
    )
    assert updated_approval.status_code == 200
    events = client.get('/api/activity').json()
    assert any(event['event_type'] == 'Campaign approved' for event in events)

    identity['uid'] = 'verified-user-b'
    assert client.get('/api/profile').json()['uid'] == identity['uid']
    assert all(
        item['rule_name'] != 'Private account rule'
        for item in client.get('/api/guidelines').json()
    )
    assert client.get('/api/audits').json() == []
    assert client.get('/api/approvals/workspace').status_code == 403
    assert client.get('/api/activity').status_code == 403


def test_protected_profile_requires_bearer_token() -> None:
    app = FastAPI()
    app.include_router(profile_router)
    client = TestClient(app)

    response = client.get('/api/profile')

    assert response.status_code == 401


def test_audit_persists_guideline_findings_with_source_evidence(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, _identity = api
    assert client.get('/api/profile').status_code == 200
    content = 'BrandGuard AI promises GUARANTEED RESULTS for every campaign.'

    response = client.post(
        '/api/audits',
        json={
            'campaign_name': 'Evidence-backed campaign',
            'campaign_type': 'Advertisement',
            'submitted_content': content,
        },
    )

    assert response.status_code == 201
    audit = response.json()
    assert audit['submitted_content'] == content
    assert audit['risk_score'] > 0
    assert audit['risk_category'] in {'medium', 'high'}
    assert audit['approval_id'] is not None
    assert audit['findings']
    score_weights = {'low': 10, 'medium': 20, 'high': 35}
    assert audit['risk_score'] == min(
        100,
        sum(score_weights[finding['severity']] for finding in audit['findings']),
    )
    assert all(finding['related_guideline_id'] is not None for finding in audit['findings'])
    assert all(finding['evidence_text'] in content for finding in audit['findings'])
    assert any(
        finding['severity'] == 'high'
        and 'guaranteed results' in finding['evidence_text'].casefold()
        for finding in audit['findings']
    )
    assert all(finding['explanation'] and finding['suggested_correction'] for finding in audit['findings'])


def test_clean_audit_has_zero_risk_and_no_synthetic_finding(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, _identity = api
    assert client.get('/api/profile').status_code == 200

    response = client.post(
        '/api/audits',
        json={
            'campaign_name': 'Clean campaign',
            'campaign_type': 'Website',
            'submitted_content': 'BrandGuard AI helps teams review their campaign content.',
        },
    )

    assert response.status_code == 201
    assert response.json()['risk_score'] == 0
    assert response.json()['risk_category'] == 'low'
    assert response.json()['findings'] == []


def test_gemini_findings_are_saved_and_labeled(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    assert client.get('/api/profile').status_code == 200
    content = 'BrandGuard AI helps teams review campaign content.'
    guideline_id = client.get('/api/guidelines').json()[0]['id']
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-not-sent')

    def fake_gemini(
        submitted_content: str,
        _guidelines: list[BrandGuideline],
    ) -> list[dict[str, object]]:
        assert submitted_content == content
        return [{
            'title': 'Needs substantiation',
            'severity': 'medium',
            'evidence': 'review campaign content',
            'explanation': 'Example model finding grounded in exact submitted text.',
            'guideline_id': guideline_id,
            'suggestion': 'Verify this claim against approved brand evidence.',
            'status': 'needs_verification',
        }]

    monkeypatch.setattr(audit_service, 'analyze_with_gemini', fake_gemini)
    response = client.post(
        '/api/audits',
        json={
            'campaign_name': 'Gemini-assisted campaign',
            'campaign_type': 'Social Media',
            'submitted_content': content,
        },
    )

    assert response.status_code == 201
    assert response.json()['analysis_mode'] == 'gemini_assisted'
    assert any(item['evidence_text'] == 'review campaign content' for item in response.json()['findings'])
    saved = client.get('/api/audits').json()[0]
    assert saved['analysis_mode'] == 'gemini_assisted'


def test_groq_audit_uses_existing_response_and_sql_persistence(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    assert client.get('/api/profile').status_code == 200
    guideline = client.get('/api/guidelines').json()[0]
    content = 'BrandGuard copy remains consistent with the active style.'
    generated = {
        'findings': [{
            'title': 'Review the brand wording',
            'severity': 'low',
            'evidence': content,
            'explanation': 'The excerpt is being compared to the supplied active guideline.',
            'guideline_id': guideline['id'],
            'suggested_correction': 'Confirm the wording against the approved guideline.',
        }],
    }

    class FakeGroq:
        def __init__(self, **_kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self) -> FakeGroq:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def create(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(generated)))],
            )

    monkeypatch.setenv('AI_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-groq-key')
    monkeypatch.setattr(groq_service, 'Groq', FakeGroq)

    response = client.post(
        '/api/audits',
        json={
            'campaign_name': 'Groq-assisted campaign',
            'campaign_type': 'Social Media',
            'submitted_content': content,
        },
    )

    assert response.status_code == 201
    assert response.json()['analysis_mode'] == 'groq_assisted'
    assert any(finding['evidence_text'] == content for finding in response.json()['findings'])
    assert client.get('/api/audits').json()[0]['analysis_mode'] == 'groq_assisted'


def test_gemini_findings_reject_unverifiable_evidence_and_guidelines() -> None:
    guideline = BrandGuideline(
        id=5,
        rule_name='Prohibited phrase',
        category='prohibited_terms',
        rule_value='unsafe claim',
        severity='high',
        active=True,
    )
    finding = {
        'title': 'Unsupported finding',
        'severity': 'high',
        'evidence': 'invented text',
        'explanation': 'This quote is not in the submitted text.',
        'guideline_id': 5,
        'suggested_correction': 'Remove the claim.',
    }

    with pytest.raises(gemini_service.GeminiAnalysisError, match='exact campaign evidence'):
        gemini_service._validate_findings(
            {'findings': [finding]},
            'The submitted campaign text.',
            [guideline],
        )

    finding['evidence'] = 'The submitted campaign text.'
    finding['guideline_id'] = 999
    with pytest.raises(gemini_service.GeminiAnalysisError, match='active guideline'):
        gemini_service._validate_findings(
            {'findings': [finding]},
            'The submitted campaign text.',
            [guideline],
        )
