from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import (
    FirebaseIdentity,
    demo_role_for_identity,
    is_demo_identity,
    require_firebase_identity,
)
from ..database import get_db
from ..models import CompanyWorkspace, UserProfile, WorkspaceInvitation, WorkspaceMembership
from ..services.workspace_service import ensure_personal_workspace, require_app_role

router = APIRouter(prefix='/api/workspaces', tags=['workspaces'])


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = 'member'
    app_role: str | None = None


class MembershipRoleUpdate(BaseModel):
    app_role: str


APP_ROLES = {'creator', 'reviewer', 'agency_partner', 'brand_admin'}


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', normalized):
        raise HTTPException(status_code=422, detail='Enter a valid email address.')
    return normalized


def _membership(db: Session, workspace_id: str, user_id: str) -> WorkspaceMembership:
    membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == user_id,
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail='You are not a member of this workspace.')
    return membership


def _reject_demo_mutation(identity: FirebaseIdentity) -> None:
    if is_demo_identity(identity):
        raise HTTPException(status_code=403, detail='Workspace changes are disabled in Demo Mode.')


@router.get('')
def list_workspaces(
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    if is_demo_identity(identity):
        from ..services.workspace_service import ensure_demo_workspace
        ensure_demo_workspace(
            db,
            identity.uid,
            demo_role_for_identity(identity),
        )
    else:
        ensure_personal_workspace(db, identity.uid)
    memberships = db.query(WorkspaceMembership, CompanyWorkspace).join(
        CompanyWorkspace,
        CompanyWorkspace.id == WorkspaceMembership.workspace_id,
    ).filter(WorkspaceMembership.user_id == identity.uid).all()
    pending = []
    if identity.email and identity.email_verified:
        pending = db.query(WorkspaceInvitation, CompanyWorkspace.name).join(
            CompanyWorkspace,
            CompanyWorkspace.id == WorkspaceInvitation.workspace_id,
        ).filter(
            WorkspaceInvitation.email == _email(identity.email),
            WorkspaceInvitation.status == 'pending',
            WorkspaceInvitation.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        ).all()
    db.commit()
    return {
        'workspaces': [
            {
                'id': workspace.id,
                'name': workspace.name,
                'role': membership.role,
                'app_role': membership.app_role or (
                    'brand_admin' if membership.role in {'owner', 'admin'} else 'creator'
                ),
            }
            for membership, workspace in memberships
        ],
        'pending_invitations': [
            {
                'id': invitation.id,
                'workspace_name': workspace_name,
                'role': invitation.role,
                'app_role': invitation.app_role,
            }
            for invitation, workspace_name in pending
        ],
    }


@router.post('', status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    _reject_demo_mutation(identity)
    administrator = db.query(WorkspaceMembership.workspace_id).filter(
        WorkspaceMembership.user_id == identity.uid,
        WorkspaceMembership.app_role == 'brand_admin',
    ).first()
    if administrator is None:
        raise HTTPException(
            status_code=403,
            detail='An existing Brand Admin must authorize new workspace creation.',
        )
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail='Workspace names must contain at least two non-space characters.')
    workspace = CompanyWorkspace(id=str(uuid4()), name=name)
    db.add(workspace)
    db.add(WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=identity.uid,
        role='owner',
        app_role='brand_admin',
    ))
    db.commit()
    return {'id': workspace.id, 'name': workspace.name, 'role': 'owner', 'app_role': 'brand_admin'}


@router.get('/{workspace_id}/members')
def list_workspace_members(
    workspace_id: str,
    db: Session = Depends(get_db),
    identity: FirebaseIdentity = Depends(require_firebase_identity),
):
    member = _membership(db, workspace_id, identity.uid)
    require_app_role(
        _workspace_access_for_member(db, workspace_id, identity.uid, member),
        'brand_admin',
    )
    memberships = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.workspace_id == workspace_id,
    ).order_by(WorkspaceMembership.created_at.asc()).all()
    return [
        {
            'user_id': member.user_id,
            'email': (db.query(UserProfile.email).filter(UserProfile.uid == member.user_id).scalar() or ''),
            'role': member.role,
            'app_role': member.app_role or (
                'brand_admin' if member.role in {'owner', 'admin'} else 'creator'
            ),
            'created_at': member.created_at,
        }
        for member in memberships
    ]


@router.get('/{workspace_id}/invitations')
def list_workspace_invitations(
    workspace_id: str,
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    member = _membership(db, workspace_id, identity.uid)
    require_app_role(
        _workspace_access_for_member(db, workspace_id, identity.uid, member),
        'brand_admin',
    )
    return db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.workspace_id == workspace_id,
        WorkspaceInvitation.status == 'pending',
        WorkspaceInvitation.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
    ).order_by(WorkspaceInvitation.created_at.desc()).all()


@router.post('/{workspace_id}/invitations', status_code=status.HTTP_201_CREATED)
def invite_workspace_member(
    workspace_id: str,
    payload: InvitationCreate,
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    _reject_demo_mutation(identity)
    actor = _membership(db, workspace_id, identity.uid)
    actor_access = _workspace_access_for_member(db, workspace_id, identity.uid, actor)
    require_app_role(actor_access, 'brand_admin')
    if payload.role not in {'member', 'admin'} or (payload.role == 'admin' and actor.role != 'owner'):
        raise HTTPException(status_code=403, detail='Only a workspace owner can invite an admin.')
    app_role = payload.app_role or ('brand_admin' if payload.role == 'admin' else 'creator')
    if app_role not in APP_ROLES:
        raise HTTPException(status_code=422, detail='Choose a valid workspace role.')
    if app_role == 'brand_admin' and actor.role != 'owner':
        raise HTTPException(status_code=403, detail='Only a workspace owner can assign Brand Admin.')
    email = _email(payload.email)
    if identity.email and _email(identity.email) == email:
        raise HTTPException(status_code=409, detail='You are already a member of this workspace.')
    pending = db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.workspace_id == workspace_id,
        WorkspaceInvitation.email == email,
        WorkspaceInvitation.status == 'pending',
    ).first()
    if pending:
        pending.role = payload.role
        pending.app_role = app_role
        pending.invited_by = identity.uid
        pending.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=14)
        db.commit()
        return pending
    invitation = WorkspaceInvitation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        email=email,
        role=payload.role,
        app_role=app_role,
        invited_by=identity.uid,
        status='pending',
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=14),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


@router.patch('/{workspace_id}/members/{member_user_id}/role')
def update_member_role(
    workspace_id: str,
    member_user_id: str,
    payload: MembershipRoleUpdate,
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    _reject_demo_mutation(identity)
    actor = _membership(db, workspace_id, identity.uid)
    require_app_role(
        _workspace_access_for_member(db, workspace_id, identity.uid, actor),
        'brand_admin',
    )
    if payload.app_role not in APP_ROLES:
        raise HTTPException(status_code=422, detail='Choose a valid workspace role.')
    if member_user_id == identity.uid:
        raise HTTPException(status_code=403, detail='You cannot change your own workspace role.')
    if payload.app_role == 'brand_admin' and actor.role != 'owner':
        raise HTTPException(status_code=403, detail='Only a workspace owner can assign Brand Admin.')
    member = _membership(db, workspace_id, member_user_id)
    if member.role == 'owner':
        raise HTTPException(status_code=403, detail='Workspace owner roles cannot be changed here.')
    if member.app_role == 'brand_admin' and payload.app_role != 'brand_admin':
        administrators = db.query(WorkspaceMembership).filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.app_role == 'brand_admin',
        ).count()
        if administrators <= 1:
            raise HTTPException(status_code=409, detail='A workspace must retain at least one Brand Admin.')
    member.app_role = payload.app_role
    db.commit()
    return {'user_id': member.user_id, 'role': member.role, 'app_role': member.app_role}


@router.post('/invitations/{invitation_id}/accept')
def accept_workspace_invitation(
    invitation_id: str,
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    _reject_demo_mutation(identity)
    if not identity.email or not identity.email_verified:
        raise HTTPException(status_code=403, detail='Verify your Firebase email address before accepting an invitation.')
    invitation = db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.id == invitation_id,
        WorkspaceInvitation.email == _email(identity.email),
        WorkspaceInvitation.status == 'pending',
        WorkspaceInvitation.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
    ).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail='A valid invitation for this verified email was not found.')
    _add_membership(db, invitation, identity.uid)
    db.commit()
    return {'workspace_id': invitation.workspace_id, 'role': invitation.role}


def _add_membership(db: Session, invitation: WorkspaceInvitation, user_id: str) -> None:
    membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.workspace_id == invitation.workspace_id,
        WorkspaceMembership.user_id == user_id,
    ).first()
    if membership is None:
        db.add(WorkspaceMembership(
            workspace_id=invitation.workspace_id,
            user_id=user_id,
            role=invitation.role,
            app_role=invitation.app_role,
        ))
    invitation.status = 'accepted'


def _workspace_access_for_member(
    db: Session,
    workspace_id: str,
    user_id: str,
    membership: WorkspaceMembership,
):
    from ..services.workspace_service import WorkspaceAccess

    return WorkspaceAccess(
        workspace_id=workspace_id,
        user_id=user_id,
        role=membership.role,
        app_role=membership.app_role or (
            'brand_admin' if membership.role in {'owner', 'admin'} else 'creator'
        ),
    )
