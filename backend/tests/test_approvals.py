from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import FirebaseIdentity, require_firebase_identity
from backend.database import Base, get_db
from backend.models import ActivityEvent, Approval, Audit, CompanyWorkspace, WorkspaceMembership
from backend.routers.activity import router as activity_router
from backend.routers.approvals import router as approvals_router


@pytest.fixture
def api() -> Iterator[tuple[TestClient, dict[str, str], sessionmaker]]:
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {
        'uid': 'reviewer-a',
        'approval_id': '',
        'workspace_id': 'workspace-a',
    }
    app = FastAPI()
    app.include_router(approvals_router)
    app.include_router(activity_router)

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
            display_name='Test reviewer',
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_firebase_identity] = override_identity

    db = test_session()
    db.add_all([
        CompanyWorkspace(id='workspace-a', name='Workspace A'),
        CompanyWorkspace(id='workspace-b', name='Workspace B'),
        WorkspaceMembership(
            workspace_id='workspace-a',
            user_id='reviewer-a',
            role='owner',
            app_role='brand_admin',
        ),
        WorkspaceMembership(
            workspace_id='workspace-b',
            user_id='reviewer-b',
            role='member',
            app_role='reviewer',
        ),
    ])
    db.flush()
    audit = Audit(
        campaign_name='Test campaign',
        campaign_type='Email',
        submitted_content='Review this campaign.',
        audit_status='completed',
        user_id='reviewer-a',
        workspace_id='workspace-a',
    )
    db.add(audit)
    db.flush()
    previous_timestamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    approval = Approval(
        audit_id=audit.id,
        decision='pending',
        reviewer='BrandGuard review',
        user_id='reviewer-a',
        workspace_id='workspace-a',
        decision_timestamp=previous_timestamp,
    )
    db.add(approval)
    db.commit()
    approval_id = approval.id
    db.close()

    client = TestClient(app)
    try:
        identity['approval_id'] = str(approval_id)
        yield client, identity, test_session
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_pending_approval_to_approved_persists_after_refresh(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, test_session = api
    approval_id = values['approval_id']
    headers = {'X-Workspace-ID': values['workspace_id']}

    response = client.patch(
        f'/api/approvals/{approval_id}',
        headers=headers,
        json={'decision': 'approved', 'comment': 'Approved for release.'},
    )

    assert response.status_code == 200
    assert response.json()['id'] == int(approval_id)
    assert response.json()['decision'] == 'approved'
    assert response.json()['comment'] == 'Approved for release.'
    refreshed = client.get('/api/approvals/workspace', headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()[0]['decision'] == 'approved'
    with test_session() as db:
        assert db.query(Audit).one().audit_status == 'approved'
        assert db.query(Approval).one().decision == 'approved'


def test_pending_approval_to_rejected_persists_after_refresh(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, test_session = api
    headers = {'X-Workspace-ID': values['workspace_id']}

    response = client.patch(
        f"/api/approvals/{values['approval_id']}",
        headers=headers,
        json={'decision': 'rejected', 'comment': 'Please revise the claim.'},
    )

    assert response.status_code == 200
    assert response.json()['decision'] == 'rejected'
    assert client.get('/api/approvals/workspace', headers=headers).json()[0]['decision'] == 'rejected'
    with test_session() as db:
        assert db.query(Audit).one().audit_status == 'rejected'
        assert db.query(Approval).one().decision == 'rejected'


def test_pending_approval_to_changes_requested_persists_comment_and_activity(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, test_session = api
    previous_timestamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    headers = {'X-Workspace-ID': values['workspace_id']}

    response = client.patch(
        f"/api/approvals/{values['approval_id']}",
        headers=headers,
        json={'decision': 'changes_requested', 'comment': 'Update the pricing details.'},
    )

    assert response.status_code == 200
    assert response.json()['decision'] == 'changes_requested'
    assert response.json()['comment'] == 'Update the pricing details.'
    assert datetime.fromisoformat(response.json()['decision_timestamp']) > previous_timestamp
    assert client.get('/api/approvals/workspace', headers=headers).json()[0]['decision'] == 'changes_requested'
    with test_session() as db:
        approval = db.query(Approval).one()
        activity = db.query(ActivityEvent).one()
        assert approval.decision == 'changes_requested'
        assert approval.comment == 'Update the pricing details.'
        assert db.query(Audit).one().audit_status == 'changes_requested'
        assert activity.event_type == 'Changes requested'
        assert activity.user_id == 'reviewer-a'
        assert activity.workspace_id == 'workspace-a'
        assert activity.timestamp is not None


@pytest.mark.parametrize(
    ('first_decision', 'second_decision'),
    [('approved', 'approved'), ('rejected', 'rejected')],
)
def test_terminal_decision_cannot_be_submitted_again(
    api: tuple[TestClient, dict[str, str], sessionmaker],
    first_decision: str,
    second_decision: str,
) -> None:
    client, values, _test_session = api
    path = f"/api/approvals/{values['approval_id']}"
    headers = {'X-Workspace-ID': values['workspace_id']}

    first = client.patch(path, headers=headers, json={'decision': first_decision})
    repeated = client.patch(path, headers=headers, json={'decision': second_decision})

    assert first.status_code == 200
    assert repeated.status_code == 409


def test_conflicting_decision_is_rejected(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, _test_session = api
    path = f"/api/approvals/{values['approval_id']}"
    headers = {'X-Workspace-ID': values['workspace_id']}

    assert client.patch(path, headers=headers, json={'decision': 'approved'}).status_code == 200
    assert client.patch(path, headers=headers, json={'decision': 'rejected'}).status_code == 409


def test_nonmember_cannot_modify_approval(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, test_session = api
    values['uid'] = 'uninvited-reviewer'

    response = client.patch(
        f"/api/approvals/{values['approval_id']}",
        headers={'X-Workspace-ID': 'workspace-a'},
        json={'decision': 'approved'},
    )

    assert response.status_code == 403
    with test_session() as db:
        assert db.query(Approval).one().decision == 'pending'


def test_approval_cannot_be_modified_from_another_workspace(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, test_session = api
    values['uid'] = 'reviewer-b'

    response = client.patch(
        f"/api/approvals/{values['approval_id']}",
        headers={'X-Workspace-ID': 'workspace-b'},
        json={'decision': 'approved'},
    )

    assert response.status_code == 404
    with test_session() as db:
        assert db.query(Approval).one().decision == 'pending'


def test_failed_database_commit_returns_error_without_persisting_decision(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, values, test_session = api

    def fail_approval_commit(db: Session) -> None:
        if any(isinstance(item, ActivityEvent) for item in db.new):
            raise SQLAlchemyError('Simulated approval transaction failure')

    event.listen(Session, 'before_commit', fail_approval_commit)
    try:
        response = client.patch(
            f"/api/approvals/{values['approval_id']}",
            headers={'X-Workspace-ID': values['workspace_id']},
            json={'decision': 'approved'},
        )
    finally:
        event.remove(Session, 'before_commit', fail_approval_commit)

    assert response.status_code == 500
    assert response.json()['detail'] == 'Approval update could not be saved.'
    with test_session() as db:
        assert db.query(Approval).one().decision == 'pending'
        assert db.query(Audit).one().audit_status == 'completed'
        assert db.query(ActivityEvent).count() == 0
