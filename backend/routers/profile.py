from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import FirebaseIdentity, require_firebase_identity
from ..database import get_db
from ..models import BrandGuideline, UserProfile
from ..schemas import ProfileOut, ProfileSettingsUpdate
from ..services.guideline_service import DEFAULT_GUIDELINES
from ..services.demo_workspace import seed_demo_workspace
from ..services.workspace_service import ensure_personal_workspace

router = APIRouter(prefix='/api', tags=['profile'])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


DEFAULT_WORKSPACE_SETTINGS = {
    'workspaceName': 'BrandGuard AI Workspace',
    'brandName': 'BrandGuard AI',
    'logoUrl': 'https://images.unsplash.com/photo-1557683316-973673baf926?auto=format&fit=crop&w=120&q=80',
    'notifications': {
        'approvals': True,
        'guidelineChanges': True,
        'auditResults': True,
    },
    'reviewPreferences': {
        'defaultRiskThreshold': 'Medium',
        'requireManualReview': True,
        'autoSaveResults': True,
    },
}


def _create_default_guidelines(db: Session, uid: str) -> None:
    if db.query(BrandGuideline.id).filter(BrandGuideline.user_id == uid).first():
        return
    for item in DEFAULT_GUIDELINES:
        db.add(BrandGuideline(**item, user_id=uid))


def _get_or_create_profile(db: Session, identity: FirebaseIdentity) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.uid == identity.uid).first()
    if profile is None:
        profile = UserProfile(
            uid=identity.uid,
            email=identity.email or '',
            display_name=identity.display_name or '',
            settings=DEFAULT_WORKSPACE_SETTINGS,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(profile)
        _create_default_guidelines(db, identity.uid)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            profile = db.query(UserProfile).filter(UserProfile.uid == identity.uid).first()
            if profile is None:
                raise
    else:
        changed = False
        if identity.email and profile.email != identity.email:
            profile.email = identity.email
            changed = True
        if identity.display_name and profile.display_name != identity.display_name:
            profile.display_name = identity.display_name
            changed = True
        if changed:
            db.commit()
            db.refresh(profile)

    return profile


@router.get('/profile', response_model=ProfileOut)
def get_profile(
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    ensure_personal_workspace(db, identity.uid)
    profile = _get_or_create_profile(db, identity)
    _create_default_guidelines(db, identity.uid)
    db.commit()
    seed_demo_workspace(db, identity.uid, identity.email)
    ensure_personal_workspace(db, identity.uid)
    db.refresh(profile)
    return profile


@router.put('/profile', response_model=ProfileOut)
def update_profile_settings(
    payload: ProfileSettingsUpdate,
    identity: FirebaseIdentity = Depends(require_firebase_identity),
    db: Session = Depends(get_db),
):
    ensure_personal_workspace(db, identity.uid)
    profile = _get_or_create_profile(db, identity)
    profile.settings = payload.settings.model_dump()
    profile.updated_at = _utcnow()
    db.commit()
    db.refresh(profile)
    return profile
