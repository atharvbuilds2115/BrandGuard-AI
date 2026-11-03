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
            role='owner',
        ))

    for model in USER_OWNED_MODELS:
        db.query(model).filter(
            model.user_id == user_id,
            model.workspace_id.is_(None),
        ).update({model.workspace_id: workspace.id}, synchronize_session=False)
    db.flush()
    return workspace


def resolve_workspace_access(
    db: Session,
    user_id: str,
    requested_workspace_id: str | None,
) -> WorkspaceAccess:
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
    return WorkspaceAccess(workspace_id=workspace_id, user_id=user_id, role=membership.role)


def require_workspace_manager(access: WorkspaceAccess) -> None:
    if access.role not in {'owner', 'admin'}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Workspace owner or admin permission is required to manage company guidelines.',
        )
