from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .auth import (
    FirebaseIdentity,
    demo_role_for_identity,
    is_demo_identity,
    optional_firebase_identity,
    require_firebase_user,
)
from .database import get_db
from .models import UserProfile
from .services.workspace_service import WorkspaceAccess, resolve_workspace_access


def require_workspace_access(
    user_id: str = Depends(require_firebase_user),
    identity: FirebaseIdentity | None = Depends(optional_firebase_identity),
    db: Session = Depends(get_db),
    workspace_id: str | None = Header(default=None, alias='X-Workspace-ID'),
) -> WorkspaceAccess:
    effective_identity = identity
    is_demo = is_demo_identity(effective_identity) if effective_identity else False
    identity_email = effective_identity.email if effective_identity else None
    demo_role = (
        (effective_identity.demo_role or effective_identity.app_role)
        if effective_identity
        else None
    )
    if identity_email is None:
        identity_email = db.query(UserProfile.email).filter(UserProfile.uid == user_id).scalar()
    if not is_demo and identity_email:
        is_demo = is_demo_identity(FirebaseIdentity(
            uid=user_id,
            email=identity_email,
            display_name=None,
        ))
    if is_demo and effective_identity is None and identity_email:
        effective_identity = FirebaseIdentity(
            uid=user_id,
            email=identity_email,
            display_name=None,
        )
    demo_role = demo_role or (
        demo_role_for_identity(effective_identity)
        if is_demo and effective_identity
        else 'creator'
    )
    access = resolve_workspace_access(
        db,
        user_id,
        workspace_id,
        demo=is_demo,
        demo_role=demo_role,
    )
    db.commit()
    return access
