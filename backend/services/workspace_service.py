from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import (
    ActivityEvent,
    Approval,
    Asset,
    Audit,
    AuditFinding,
    BrandGuideline,
    CompanyWorkspace,
    ConsistencyReport,
    GuidelineDocument,
    VideoReview,
    WorkspaceMembership,
)


USER_OWNED_MODELS = (
    BrandGuideline,
    GuidelineDocument,
    Asset,
    Audit,
    AuditFinding,
    Approval,
    ActivityEvent,
    VideoReview,
    ConsistencyReport,
)


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace_id: str
    user_id: str
    role: str
    app_role: str
    demo: bool = False


def ensure_personal_workspace(db: Session, user_id: str) -> CompanyWorkspace:
    workspace = db.query(CompanyWorkspace).filter(
        CompanyWorkspace.personal_owner_uid == user_id,
    ).first()
    if workspace is None:
        workspace = CompanyWorkspace(
            id=str(uuid4()),
            name='Personal workspace',
            personal_owner_uid=user_id,
        )
        db.add(workspace)
        db.flush()

    membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.workspace_id == workspace.id,
        WorkspaceMembership.user_id == user_id,
    ).first()
    if membership is None:
        db.add(WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user_id,
            role='member',
            app_role='creator',
        ))

    for model in USER_OWNED_MODELS:
        db.query(model).filter(
            model.user_id == user_id,
            model.workspace_id.is_(None),
        ).update({model.workspace_id: workspace.id}, synchronize_session=False)
    db.flush()
    return workspace


DEMO_WORKSPACE_IDS = {
    'creator': 'brandguard-demo-workspace',
    'reviewer': 'brandguard-demo-reviewer-workspace',
    'agency_partner': 'brandguard-demo-agency-workspace',
    'brand_admin': 'brandguard-demo-admin-workspace',
}
DEMO_WORKSPACE_NAMES = {
    'creator': 'Creator Demo Workspace',
    'reviewer': 'Reviewer Demo Workspace',
    'agency_partner': 'Agency Partner Demo Workspace',
    'brand_admin': 'Brand Admin Demo Workspace',
}
DEMO_WORKSPACE_ID = DEMO_WORKSPACE_IDS['creator']
APP_ROLES = {'creator', 'reviewer', 'agency_partner', 'brand_admin'}


def ensure_demo_workspace(db: Session, user_id: str, app_role: str) -> CompanyWorkspace:
    if app_role not in APP_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='The demo account does not have a valid workspace role.',
        )
    workspace_id = DEMO_WORKSPACE_IDS[app_role]
    workspace = db.query(CompanyWorkspace).filter(
        CompanyWorkspace.id == workspace_id,
    ).first()
    if workspace is None:
        workspace = CompanyWorkspace(
            id=workspace_id,
            name=DEMO_WORKSPACE_NAMES[app_role],
        )
        db.add(workspace)
        db.flush()

    other_workspace_ids = [
        value for value in DEMO_WORKSPACE_IDS.values()
        if value != workspace_id
    ]
    db.query(WorkspaceMembership).filter(
        WorkspaceMembership.user_id == user_id,
        WorkspaceMembership.workspace_id.in_(other_workspace_ids),
    ).delete(synchronize_session=False)

    membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == user_id,
    ).first()
    if membership is None:
        db.add(WorkspaceMembership(
            workspace_id=workspace_id,
            user_id=user_id,
            role='owner' if app_role == 'brand_admin' else 'member',
            app_role=app_role,
        ))
    else:
        membership.app_role = app_role
        membership.role = 'owner' if app_role == 'brand_admin' else 'member'
    db.commit()
    return workspace


def resolve_workspace_access(
    db: Session,
    user_id: str,
    requested_workspace_id: str | None,
    demo: bool = False,
    demo_role: str | None = None,
) -> WorkspaceAccess:
    if demo:
        app_role = demo_role or 'creator'
        ensure_demo_workspace(db, user_id, app_role)
        workspace_id = DEMO_WORKSPACE_IDS[app_role]
        membership = db.query(WorkspaceMembership).filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        ).first()
        if membership is None:
            raise HTTPException(status_code=403, detail='You are not a member of the demo workspace.')
        return WorkspaceAccess(
            workspace_id=workspace_id,
            user_id=user_id,
            role=membership.role,
            app_role=membership.app_role,
            demo=True,
        )
    personal = ensure_personal_workspace(db, user_id)
    workspace_id = requested_workspace_id or personal.id
    membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == user_id,
    ).first()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of the selected workspace.',
        )
    app_role = membership.app_role or (
        'brand_admin' if membership.role in {'owner', 'admin'} else 'creator'
    )
    return WorkspaceAccess(
        workspace_id=workspace_id,
        user_id=user_id,
        role=membership.role,
        app_role=app_role,
    )


def require_workspace_manager(access: WorkspaceAccess) -> None:
    if access.app_role != 'brand_admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Brand Admin permission is required for this operation.',
        )


def require_app_role(access: WorkspaceAccess, *roles: str) -> None:
    if access.app_role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Your workspace role does not permit this operation.',
        )


def require_mutation_allowed(access: WorkspaceAccess) -> None:
    if access.demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Destructive changes are disabled in Demo Mode. Use demo reset to restore sample data.',
        )
