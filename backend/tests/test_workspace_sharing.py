from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import FirebaseIdentity, require_firebase_identity
from backend.database import Base, get_db
from backend.routers.guidelines import router as guidelines_router
from backend.routers.workspaces import router as workspaces_router


def test_workspace_invitation_shares_approved_guidelines_only_with_members() -> None:
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {'uid': 'workspace-owner', 'email': 'owner@example.test'}
    app = FastAPI()
    app.include_router(workspaces_router)
    app.include_router(guidelines_router)

    def override_db() -> Iterator[Session]:
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    def override_identity() -> FirebaseIdentity:
        return FirebaseIdentity(
            uid=identity['uid'],
            email=identity['email'],
            display_name='Test user',
            email_verified=True,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_firebase_identity] = override_identity

    try:
        with TestClient(app) as client:
            personal = client.get('/api/workspaces').json()['workspaces'][0]
            company = client.post('/api/workspaces', json={'name': 'Example Company'}).json()
            company_headers = {'X-Workspace-ID': company['id']}
            created = client.post(
                '/api/guidelines',
                headers=company_headers,
                json={
                    'rule_name': 'Approved logo',
                    'category': 'logo_usage',
                    'description': 'Use the approved blue mark.',
                    'rule_value': 'Use the blue mark.',
                    'active': True,
                },
            )
            assert created.status_code == 201
            guideline_id = created.json()['id']

            private_guideline = client.get('/api/guidelines', headers={'X-Workspace-ID': personal['id']})
            assert private_guideline.status_code == 200
            assert all(item['id'] != guideline_id for item in private_guideline.json())

            invitation = client.post(
                f"/api/workspaces/{company['id']}/invitations",
                json={'email': 'member@example.test', 'role': 'member'},
            )
            assert invitation.status_code == 201

            identity.update(uid='workspace-member', email='member@example.test')
            member_workspaces = client.get('/api/workspaces').json()
            pending = member_workspaces['pending_invitations']
            assert len(pending) == 1
            accepted = client.post(f"/api/workspaces/invitations/{pending[0]['id']}/accept")
            assert accepted.status_code == 200

            shared = client.get('/api/guidelines', headers=company_headers)
            assert shared.status_code == 200
            assert [item['id'] for item in shared.json()] == [guideline_id]

            forbidden_write = client.post(
                '/api/guidelines',
                headers=company_headers,
                json={
                    'rule_name': 'Member rule',
                    'category': 'other',
                    'rule_value': 'Not allowed.',
                },
            )
            assert forbidden_write.status_code == 403

            identity.update(uid='uninvited-user', email='uninvited@example.test')
            denied = client.get('/api/guidelines', headers=company_headers)
            assert denied.status_code == 403
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
