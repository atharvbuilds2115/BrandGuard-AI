from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import Asset
from ..schemas import AssetOut, AssetUpdate
from ..services.asset_service import MAX_UPLOAD_SIZE_BYTES, get_upload_directory, persist_asset

router = APIRouter(prefix='/api', tags=['assets'])


@router.get('/assets', response_model=list[AssetOut])
def list_assets(
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
    q: str | None = None,
    file_type: str | None = None,
    status: str | None = None,
    sort: str = 'newest',
):
    query = db.query(Asset).filter(Asset.user_id == user_id)
    if q:
        like = f'%{q}%'
        query = query.filter((Asset.original_filename.ilike(like)) | (Asset.tags.ilike(like)))
    if file_type:
        query = query.filter(Asset.mime_type.ilike(f'%{file_type}%'))
    if status:
        query = query.filter(Asset.review_status.ilike(status))

    if sort == 'oldest':
        query = query.order_by(Asset.uploaded_at.asc())
    elif sort == 'alphabetical':
        query = query.order_by(Asset.original_filename.asc())
    else:
        query = query.order_by(Asset.uploaded_at.desc())

    return query.all()


@router.get('/assets/{asset_id}', response_model=AssetOut)
def get_asset(
    asset_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail='Asset not found')
    return asset


@router.post('/assets/upload', response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(...),
    campaign_name: str | None = Form(default=None),
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    try:
        asset = persist_asset(db, file, content, campaign_name, user_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return asset


@router.patch('/assets/{asset_id}', response_model=AssetOut)
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail='Asset not found')

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(asset, field, value)

    db.commit(); db.refresh(asset)
    return asset


@router.delete('/assets/{asset_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail='Asset not found')

    upload_root = get_upload_directory()
    file_path = Path(asset.file_path).resolve()
    if upload_root not in file_path.parents:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Stored asset path is invalid.')
    if file_path.exists():
        file_path.unlink()

    db.delete(asset)
    db.commit()


@router.get('/assets/{asset_id}/download')
def download_asset(
    asset_id: int,
    user_id: str = Depends(require_firebase_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail='Asset not found')

    upload_root = get_upload_directory()
    file_path = Path(asset.file_path).resolve()
    if upload_root not in file_path.parents:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Stored asset path is invalid.')
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found on disk')

    return FileResponse(file_path, filename=asset.original_filename)
