from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import require_firebase_user
from backend.database import Base, get_db
from backend.models import (
    Audit,
    AuditFinding,
    BrandGuideline,
    CompanyWorkspace,
    ConsistencyReport,
    WorkspaceMembership,
)
from backend.routers.consistency import router as consistency_router
from backend.services.consistency_service import _issue_area
from backend.services.workspace_service import WorkspaceAccess, ensure_personal_workspace
from backend.workspace_auth import require_workspace_access


@pytest.fixture
def api() -> Iterator[tuple[TestClient, dict[str, str], sessionmaker]]:
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {'uid': 'consistency-user-a'}
    app = FastAPI()
    app.include_router(consistency_router)

    def override_db() -> Iterator[Session]:
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    def override_workspace_access(
        user_id: str = Depends(require_firebase_user),
        db: Session = Depends(get_db),
    ) -> WorkspaceAccess:
        workspace = ensure_personal_workspace(db, user_id)
        membership = db.query(WorkspaceMembership).filter_by(
            workspace_id=workspace.id,
            user_id=user_id,
        ).one()
        membership.app_role = 'brand_admin'
        return WorkspaceAccess(
            workspace_id=workspace.id,
            user_id=user_id,
            role=membership.role,
            app_role='brand_admin',
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_firebase_user] = lambda: identity['uid']
    app.dependency_overrides[require_workspace_access] = override_workspace_access
    client = TestClient(app)
    try:
        yield client, identity, test_session
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_audits(test_session: sessionmaker) -> list[int]:
    db = test_session()
    guideline = BrandGuideline(
        rule_name='Approved product name',
        category='approved_terminology',
        description='Use the approved name consistently.',
        rule_value='BrandGuard AI',
        severity='medium',
        active=True,
        user_id='consistency-user-a',
    )
    db.add(guideline)
    db.flush()
    audit_ids = []
    for index, risk_score in enumerate((55, 25, 0), start=1):
        audit = Audit(
            campaign_name=f'Campaign {index}',
            campaign_type='Email',
            submitted_content='BrandGuard AI promise text',
            risk_score=risk_score,
            risk_category='high' if risk_score >= 35 else 'low',
            audit_status='completed',
            analysis_mode='rules_only',
            created_at=datetime(2026, 10, index),
            user_id='consistency-user-a',
        )
        db.add(audit)
        db.flush()
        audit_ids.append(audit.id)
        if index < 3:
            db.add(AuditFinding(
                audit_id=audit.id,
                finding_title='Required terminology missing',
                severity='high' if index == 1 else 'medium',
                evidence_text='The submitted copy uses the wrong product name.',
                explanation='Saved audit evidence identifies inconsistent product terminology.',
                related_guideline_id=guideline.id,
                suggested_correction='Use the approved product name BrandGuard AI.',
                finding_status='confirmed',
                user_id='consistency-user-a',
            ))
    db.commit()
    db.close()
    return audit_ids


def test_report_compares_saved_audits_and_persists_evidence(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, _identity, test_session = api
    audit_ids = _seed_audits(test_session)
    response = client.post('/api/consistency-reports', json={'audit_ids': audit_ids[:2]})

    assert response.status_code == 201
    report = response.json()
    data = report['report_data']
    assert report['campaign_count'] == 2
    assert data['average_compliance_score'] == 60.0
    assert data['average_risk_score'] == 40.0
    assert [campaign['compliance_score'] for campaign in data['campaigns']] == [45, 75]
    assert data['severity_distribution'] == {'high': 1, 'medium': 1, 'low': 0}
    assert data['recurring_violations'][0]['campaign_count'] == 2
    assert data['recurring_violations'][0]['area'] == 'messaging'
    assert data['recurring_violations'][0]['occurrences'][0]['evidence'] == 'The submitted copy uses the wrong product name.'
    assert data['frequently_violated_guidelines'][0]['finding_count'] == 2
    assert data['recommendations'][0]['action'] == 'Use the approved product name BrandGuard AI.'
    assert client.get('/api/consistency-reports').json()[0]['id'] == report['id']
    assert client.get(f"/api/consistency-reports/{report['id']}").status_code == 200

    db = test_session()
    assert db.query(ConsistencyReport).filter_by(user_id='consistency-user-a').count() == 1
    db.close()


def test_report_rejects_unowned_or_incomplete_audits(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, identity, test_session = api
    audit_ids = _seed_audits(test_session)
    response = client.post('/api/consistency-reports', json={'audit_ids': [audit_ids[0], audit_ids[2]]})
    assert response.status_code == 201

    identity['uid'] = 'consistency-user-b'
    assert client.get('/api/consistency-reports').json() == []
    assert client.get(f"/api/consistency-reports/{response.json()['id']}").status_code == 404
    assert client.post('/api/consistency-reports', json={'audit_ids': audit_ids[:2]}).status_code == 404


def test_report_requires_at_least_two_distinct_audits(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, _identity, test_session = api
    audit_ids = _seed_audits(test_session)
    assert client.post('/api/consistency-reports', json={'audit_ids': [audit_ids[0]]}).status_code == 422
    assert client.post('/api/consistency-reports', json={'audit_ids': [audit_ids[0], audit_ids[0]]}).status_code == 422


def test_report_endpoint_requires_authentication() -> None:
    app = FastAPI()
    app.include_router(consistency_router)
    client = TestClient(app)
    assert client.get('/api/consistency-reports').status_code == 401


@pytest.mark.parametrize(
    ('category', 'expected_area'),
    [
        ('logo_visual_identity', 'logo'),
        ('brand_colors', 'color'),
        ('typography', 'typography'),
        ('approved_claims', 'messaging'),
        ('prohibited_terms', 'messaging'),
        ('unclassified_rule', 'other'),
    ],
)
def test_issue_areas_follow_saved_guideline_category(
    category: str,
    expected_area: str,
) -> None:
    guideline = BrandGuideline(
        category=category,
        rule_name='Saved rule',
    )
    finding = SimpleNamespace(
        finding_title='Saved audit finding',
        evidence_text='Exact evidence from the saved finding.',
        explanation='Saved audit explanation.',
    )
    assert _issue_area(finding, guideline) == expected_area