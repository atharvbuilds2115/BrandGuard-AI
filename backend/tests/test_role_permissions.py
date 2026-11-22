from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import FirebaseIdentity, require_firebase_identity
from backend.database import Base, get_db, _migrate_workspace_roles
from backend.models import Approval, Audit, CompanyWorkspace, WorkspaceMembership
from backend.routers.approvals import router as approvals_router
from backend.routers.audits import router as audits_router
from backend.routers.profile import router as profile_router
from backend.routers.workspaces import router as workspaces_router


@pytest.fixture
def api() -> Iterator[tuple[TestClient, dict[str, str], sessionmaker]]:
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    state = {'uid': 'member-a', 'demo': 'false'}
    app = FastAPI()
    app.include_router(approvals_router)
    app.include_router(audits_router)
    app.include_router(profile_router)
    app.include_router(workspaces_router)

    def override_db() -> Iterator[Session]:
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    def override_identity() -> FirebaseIdentity:
        return FirebaseIdentity(
            uid=state['uid'],
            email=f"{state['uid']}@example.test",
            display_name='Test user',
            email_verified=True,
            brandguard_demo=state['demo'] == 'true',
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_firebase_identity] = override_identity

    with test_session() as db:
        db.add_all([
            CompanyWorkspace(id='workspace-a', name='Workspace A'),
            CompanyWorkspace(id='workspace-b', name='Workspace B'),
            WorkspaceMembership(
                workspace_id='workspace-a',
                user_id='member-a',
                role='member',
                app_role='creator',
            ),
            WorkspaceMembership(
                workspace_id='workspace-a',
                user_id='member-b',
                role='member',
                app_role='creator',
            ),
            WorkspaceMembership(
                workspace_id='workspace-a',
                user_id='reviewer-b',
                role='member',
                app_role='reviewer',
            ),
            WorkspaceMembership(
                workspace_id='workspace-a',
                user_id='owner-a',
                role='owner',
                app_role='brand_admin',
            ),
            WorkspaceMembership(
                workspace_id='workspace-a',
                user_id='admin-a',
                role='admin',
                app_role='brand_admin',
            ),
            WorkspaceMembership(
                workspace_id='workspace-b',
                user_id='member-b',
                role='member',
                app_role='creator',
            ),
        ])
        audit = Audit(
            campaign_name='Assigned campaign',
            campaign_type='Email',
            submitted_content='Review this campaign.',
            user_id='owner-a',
            workspace_id='workspace-a',
        )
        db.add(audit)
        db.flush()
        db.add(Approval(
            audit_id=audit.id,
            decision='pending',
            reviewer='BrandGuard review',
            user_id='owner-a',
            workspace_id='workspace-a',
        ))
        unassigned_audit = Audit(
            campaign_name='Unassigned campaign',
            campaign_type='Email',
            submitted_content='Not assigned for review.',
            user_id='owner-a',
            workspace_id='workspace-a',
        )
        db.add(unassigned_audit)
        db.flush()
        db.add(Approval(
            audit_id=unassigned_audit.id,
            decision='pending',
            reviewer='BrandGuard review',
            user_id='owner-a',
            workspace_id='workspace-a',
        ))
        db.commit()

    client = TestClient(app)
    try:
        yield client, state, test_session
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize(
    ('app_role', 'expected_status'),
    [
        ('creator', 403),
        ('reviewer', 200),
        ('agency_partner', 403),
        ('brand_admin', 200),
    ],
)
def test_approval_access_is_limited_to_reviewers_and_brand_admins(
    api: tuple[TestClient, dict[str, str], sessionmaker],
    app_role: str,
    expected_status: int,
) -> None:
    client, state, test_session = api
    with test_session() as db:
        membership = db.query(WorkspaceMembership).filter_by(
            workspace_id='workspace-a',
            user_id='member-a',
        ).one()
        membership.app_role = app_role
        db.commit()

    response = client.get('/api/approvals', headers={'X-Workspace-ID': 'workspace-a'})

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ('app_role', 'expected_status'),
    [
        ('creator', 201),
        ('reviewer', 403),
        ('agency_partner', 201),
        ('brand_admin', 201),
    ],
)
def test_campaign_audit_access_matches_role_permissions(
    api: tuple[TestClient, dict[str, str], sessionmaker],
    monkeypatch: pytest.MonkeyPatch,
    app_role: str,
    expected_status: int,
) -> None:
    client, _, test_session = api
    with test_session() as db:
        membership = db.query(WorkspaceMembership).filter_by(
            workspace_id='workspace-a',
            user_id='member-a',
        ).one()
        membership.app_role = app_role
        db.commit()
    monkeypatch.setattr(
        'backend.routers.audits.run_audit_engine',
        lambda *args: (0, 'low', [], 'rules_only'),
    )

    response = client.post(
        '/api/audits',
        headers={'X-Workspace-ID': 'workspace-a'},
        json={
            'campaign_name': 'Test campaign',
            'campaign_type': 'Email',
            'submitted_content': 'A test campaign.',
        },
    )

    assert response.status_code == expected_status


def test_only_brand_admin_can_assign_roles_and_only_owner_can_assign_brand_admin(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, state, _ = api
    headers = {'X-Workspace-ID': 'workspace-a'}
    target_path = '/api/workspaces/workspace-a/members/member-b/role'
    payload = {'app_role': 'reviewer'}

    response = client.patch(target_path, headers=headers, json=payload)
    assert response.status_code == 403

    state['uid'] = 'admin-a'
    response = client.patch(
        target_path,
        headers=headers,
        json={'app_role': 'brand_admin'},
    )
    assert response.status_code == 403
    response = client.patch(target_path, headers=headers, json=payload)
    assert response.status_code == 200

    state['uid'] = 'owner-a'
    self_assignment = client.patch(
        '/api/workspaces/workspace-a/members/owner-a/role',
        headers=headers,
        json={'app_role': 'creator'},
    )
    assert self_assignment.status_code == 403
    response = client.patch(
        target_path,
        headers=headers,
        json={'app_role': 'brand_admin'},
    )
    assert response.status_code == 200
    assert response.json()['app_role'] == 'brand_admin'


def test_reviewers_only_see_and_decide_submissions_assigned_to_them(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, state, test_session = api
    with test_session() as db:
        approval_id = db.query(Approval.id).order_by(Approval.id.asc()).first()[0]
        unassigned_audit_id = db.query(Audit.id).filter(
            Audit.campaign_name == 'Unassigned campaign',
        ).one()[0]
        reviewer = db.query(WorkspaceMembership).filter_by(
            workspace_id='workspace-a',
            user_id='member-a',
        ).one()
        reviewer.app_role = 'reviewer'
        db.commit()
    state['uid'] = 'owner-a'

    assigned = client.patch(
        f'/api/approvals/{approval_id}/assignment',
        headers={'X-Workspace-ID': 'workspace-a'},
        json={'reviewer_user_id': 'member-a'},
    )
    assert assigned.status_code == 200
    assert assigned.json()['assigned_reviewer_uid'] == 'member-a'

    state['uid'] = 'member-a'
    headers = {'X-Workspace-ID': 'workspace-a'}
    visible = client.get('/api/approvals/workspace', headers=headers)
    assert visible.status_code == 200
    assert len(visible.json()) == 1
    reviewer_audits = client.get('/api/audits', headers=headers)
    assert reviewer_audits.status_code == 200
    assert [audit['campaign_name'] for audit in reviewer_audits.json()] == ['Assigned campaign']
    assert client.get(f'/api/audits/{unassigned_audit_id}', headers=headers).status_code == 404
    decision = client.patch(
        f'/api/approvals/{approval_id}',
        headers=headers,
        json={'decision': 'approved', 'comment': 'Reviewed.'},
    )
    assert decision.status_code == 200

    state['uid'] = 'reviewer-b'
    assert client.get('/api/approvals/workspace', headers=headers).json() == []
    denied = client.patch(
        f'/api/approvals/{approval_id}',
        headers=headers,
        json={'decision': 'rejected', 'comment': 'Not assigned.'},
    )
    assert denied.status_code == 403


def test_workspace_membership_prevents_cross_organisation_access(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, _, _ = api

    response = client.get('/api/approvals', headers={'X-Workspace-ID': 'workspace-b'})

    assert response.status_code == 403


def test_demo_accounts_cannot_create_or_mutate_workspace_memberships(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, state, _ = api
    state['demo'] = 'true'

    assert client.post('/api/workspaces', json={'name': 'Real workspace'}).status_code == 403
    assert client.post(
        '/api/workspaces/workspace-a/invitations',
        json={'email': 'new-member@example.test', 'role': 'member'},
    ).status_code == 403
    assert client.patch(
        '/api/workspaces/workspace-a/members/member-b/role',
        json={'app_role': 'brand_admin'},
    ).status_code == 403
    assert client.post('/api/workspaces/invitations/unknown/accept').status_code == 403


def test_new_account_starts_as_creator_and_only_existing_admin_can_create_workspaces(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, state, test_session = api
    state['uid'] = 'new-user'

    profile = client.get('/api/profile')
    assert profile.status_code == 200
    settings_update = client.put(
        '/api/profile',
        json={'settings': profile.json()['settings']},
    )
    assert settings_update.status_code == 403
    workspaces = client.get('/api/workspaces')
    assert workspaces.status_code == 200
    assert workspaces.json()['workspaces'][0]['app_role'] == 'creator'

    denied = client.post('/api/workspaces', json={'name': 'New company'})
    assert denied.status_code == 403

    with test_session() as db:
        personal_workspace = db.query(CompanyWorkspace).filter_by(personal_owner_uid='new-user').one()
        membership = db.query(WorkspaceMembership).filter_by(
            workspace_id=personal_workspace.id,
            user_id='new-user',
        ).one()
        membership.app_role = 'brand_admin'
        db.commit()
    created = client.post('/api/workspaces', json={'name': 'New company'})
    assert created.status_code == 201
    assert created.json()['app_role'] == 'brand_admin'


def test_legacy_workspace_roles_migrate_without_changing_membership_access() -> None:
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE workspace_memberships ('
            'workspace_id VARCHAR(36), user_id VARCHAR(128), role VARCHAR(16), '
            'PRIMARY KEY (workspace_id, user_id))'
        ))
        connection.execute(text(
            'CREATE TABLE workspace_invitations ('
            'id VARCHAR(36) PRIMARY KEY, email VARCHAR(254), role VARCHAR(16))'
        ))
        connection.execute(text(
            "INSERT INTO workspace_memberships VALUES "
            "('workspace', 'legacy-owner', 'owner'), "
            "('workspace', 'legacy-admin', 'admin'), "
            "('workspace', 'legacy-member', 'member')"
        ))
        connection.execute(text(
            "INSERT INTO workspace_invitations VALUES "
            "('invite-admin', 'admin@example.test', 'admin'), "
            "('invite-member', 'member@example.test', 'member')"
        ))

    _migrate_workspace_roles(engine)
    with engine.connect() as connection:
        memberships = dict(connection.execute(text(
            'SELECT user_id, app_role FROM workspace_memberships'
        )).all())
        invitations = dict(connection.execute(text(
            'SELECT id, app_role FROM workspace_invitations'
        )).all())
        roles = dict(connection.execute(text(
            'SELECT user_id, role FROM workspace_memberships'
        )).all())

    assert memberships == {
        'legacy-owner': 'brand_admin',
        'legacy-admin': 'brand_admin',
        'legacy-member': 'creator',
    }
    assert roles == {
        'legacy-owner': 'owner',
        'legacy-admin': 'admin',
        'legacy-member': 'member',
    }
    assert invitations == {'invite-admin': 'brand_admin', 'invite-member': 'creator'}
    engine.dispose()
