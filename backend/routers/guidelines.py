from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import BrandGuideline
from ..schemas import GuidelineCreate, GuidelineOut, GuidelineUpdate

router = APIRouter(prefix='/api', tags=['guidelines'])


@router.get('/guidelines', response_model=list[GuidelineOut])
def list_guidelines(
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
    category: str | None = Query(default=None),
    active: bool | None = Query(default=None),
):
    query = db.query(BrandGuideline).filter(BrandGuideline.user_id == user_id)
    if category:
        query = query.filter(BrandGuideline.category.ilike(category))
    if active is not None:
        query = query.filter(BrandGuideline.active.is_(active))
    return query.order_by(BrandGuideline.created_at.desc()).all()


@router.post('/guidelines', response_model=GuidelineOut, status_code=status.HTTP_201_CREATED)
def create_guideline(
    payload: GuidelineCreate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    guideline = BrandGuideline(
        rule_name=payload.rule_name,
        category=payload.category,
        description=payload.description,
        rule_value=payload.rule_value,
        severity=payload.severity,
        active=payload.active,
        user_id=user_id,
    )
    db.add(guideline)
    db.commit()
    db.refresh(guideline)
    return guideline


@router.get('/guidelines/{guideline_id}', response_model=GuidelineOut)
def get_guideline(
    guideline_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    guideline = db.query(BrandGuideline).filter(
        BrandGuideline.id == guideline_id,
        BrandGuideline.user_id == user_id,
    ).first()
    if not guideline:
        raise HTTPException(status_code=404, detail='Guideline not found')
    return guideline


@router.patch('/guidelines/{guideline_id}', response_model=GuidelineOut)
def update_guideline(
    guideline_id: int,
    payload: GuidelineUpdate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    guideline = db.query(BrandGuideline).filter(
        BrandGuideline.id == guideline_id,
        BrandGuideline.user_id == user_id,
    ).first()
    if not guideline:
        raise HTTPException(status_code=404, detail='Guideline not found')

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(guideline, field, value)

    db.commit()
    db.refresh(guideline)
    return guideline


@router.delete('/guidelines/{guideline_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_guideline(
    guideline_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    guideline = db.query(BrandGuideline).filter(
        BrandGuideline.id == guideline_id,
        BrandGuideline.user_id == user_id,
    ).first()
    if not guideline:
        raise HTTPException(status_code=404, detail='Guideline not found')

    db.delete(guideline)
    db.commit()
