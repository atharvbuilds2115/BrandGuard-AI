from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .auth import require_firebase_user
from .database import get_db
from .services.workspace_service import WorkspaceAccess, resolve_workspace_access


def require_workspace_access(
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
    workspace_id: str | None = Header(default=None, alias='X-Workspace-ID'),
) -> WorkspaceAccess:
    access = resolve_workspace_access(db, user_id, workspace_id)
    db.commit()
    return access
