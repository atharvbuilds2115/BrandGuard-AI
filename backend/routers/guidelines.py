from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, BrandGuideline, GuidelineDocument, GuidelineHistory
from ..schemas import (
    GuidelineCreate,
    GuidelineExtractionOut,
    GuidelineImportSave,
    GuidelineImportDocumentOut,
    GuidelineImportSaveOut,
    GuidelineOut,
    GuidelineUpdate,
)
from ..services.ai_provider import AIAnalysisError, get_active_ai_provider
from ..services.ai_service import extract_company_guidelines
from ..services.guideline_import_service import (
    MAX_GUIDELINE_FILE_SIZE_BYTES,
    GuidelineDocumentError,
    extract_guideline_document,
)
from ..services.workspace_service import WorkspaceAccess, require_mutation_allowed, require_workspace_manager
from ..workspace_auth import require_workspace_access

router = APIRouter(
    prefix='/api',
    tags=['guidelines'],
    dependencies=[Depends(require_workspace_access)],
)


def _safe_filename(filename: str) -> str:
    safe_name = PurePosixPath(filename.replace('\\', '/')).name.strip()
    if not safe_name or safe_name in {'.', '..'}:
        raise HTTPException(status_code=400, detail='The uploaded document must have a filename.')
    return safe_name[:255]


@router.post('/guideline-imports/extract', response_model=GuidelineExtractionOut)
async def extract_company_guideline_document(
    file: UploadFile = File(...),
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_workspace_manager(access)
    filename = _safe_filename(file.filename or '')
    content = await file.read(MAX_GUIDELINE_FILE_SIZE_BYTES + 1)
    if len(content) > MAX_GUIDELINE_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail='Guideline documents must be 10 MB or smaller.')
    try:
        document = await run_in_threadpool(
            extract_guideline_document,
            filename,
            file.content_type or '',
            content,
        )
        existing_guidelines = db.query(BrandGuideline).filter(
            BrandGuideline.workspace_id == access.workspace_id,
            BrandGuideline.active.is_(True),
        ).all()
        rules, provider, model = await run_in_threadpool(
            extract_company_guidelines,
            document,
            existing_guidelines,
        )
    except GuidelineDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AIAnalysisError as error:
        raise HTTPException(status_code=error.http_status_code, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    saved_document = GuidelineDocument(
        original_filename=filename,
        provider=provider,
        model_used=model,
        user_id=user_id,
        workspace_id=access.workspace_id,
        status='pending_review',
    )
    db.add(saved_document)
    db.flush()
    db.add(GuidelineHistory(
        workspace_id=access.workspace_id,
        document_id=saved_document.id,
        actor_user_id=user_id,
        action='uploaded',
        details={'filename': filename, 'provider': provider, 'model': model},
    ))
    db.commit()
    return {
        'original_filename': filename,
        'provider': provider,
        'model_used': model,
        'document_id': saved_document.id,
        'rules': rules,
    }


@router.post(
    '/guideline-imports',
    response_model=GuidelineImportSaveOut,
    status_code=status.HTTP_201_CREATED,
)
def save_imported_guidelines(
    payload: GuidelineImportSave,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_workspace_manager(access)
    try:
        provider = get_active_ai_provider()
    except AIAnalysisError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if payload.provider != provider:
        raise HTTPException(
            status_code=409,
            detail='The selected AI provider changed after extraction. Extract the document again before saving.',
        )
    if not re.fullmatch(r'[A-Za-z0-9._/-]+', payload.model_used):
        raise HTTPException(status_code=400, detail='The extraction model reference is invalid.')

    filename = _safe_filename(payload.original_filename)
    document = db.query(GuidelineDocument).filter(
        GuidelineDocument.id == payload.document_id,
        GuidelineDocument.workspace_id == access.workspace_id,
        GuidelineDocument.status == 'pending_review',
    ).first() if payload.document_id is not None else None
    if document is None and payload.document_id is not None:
        raise HTTPException(status_code=404, detail='The extracted document is unavailable in this workspace.')
    if document is None:
        document = GuidelineDocument(
            original_filename=filename,
            provider=payload.provider,
            model_used=payload.model_used,
            user_id=user_id,
            workspace_id=access.workspace_id,
            status='pending_review',
        )
        db.add(document)
        db.flush()
    if document.original_filename != filename or document.provider != payload.provider or document.model_used != payload.model_used:
        raise HTTPException(status_code=409, detail='The extracted document metadata changed. Extract it again before saving.')

    saved_guidelines: list[BrandGuideline] = []
    for rule in payload.rules:
        guideline = BrandGuideline(
            rule_name=rule.rule_name.strip(),
            category=rule.category,
            description=rule.description.strip(),
            rule_value=rule.rule_value.strip(),
            severity=rule.severity,
            active=True,
            user_id=user_id,
            workspace_id=access.workspace_id,
            source_document_id=document.id,
            source_reference=rule.source_reference,
            source_excerpt=rule.source_excerpt,
            requirement_type=rule.requirement_type,
        )
        db.add(guideline)
        saved_guidelines.append(guideline)

    db.add(ActivityEvent(
        event_type='Company guidelines imported',
        description=f'Saved {len(saved_guidelines)} approved rules from {filename}.',
        related_entity_id=str(document.id),
        user_id=user_id,
        workspace_id=access.workspace_id,
    ))
    document.status = 'approved'
    db.flush()
    db.add(GuidelineHistory(
        workspace_id=access.workspace_id,
        document_id=document.id,
        actor_user_id=user_id,
        action='approved',
        details={'rules_saved': len(saved_guidelines)},
    ))
    for guideline in saved_guidelines:
        db.add(GuidelineHistory(
            workspace_id=access.workspace_id,
            guideline_id=guideline.id,
            document_id=document.id,
            actor_user_id=user_id,
            action='approved',
            details={'rule_name': guideline.rule_name},
        ))
    db.commit()
    db.refresh(document)
    for guideline in saved_guidelines:
        db.refresh(guideline)

    return {
        'id': document.id,
        'original_filename': document.original_filename,
        'provider': document.provider,
        'model_used': document.model_used,
        'created_at': document.created_at,
        'rules_saved': len(saved_guidelines),
        'guidelines': saved_guidelines,
    }


@router.get('/guideline-imports', response_model=list[GuidelineImportDocumentOut])
def list_guideline_import_documents(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_workspace_manager(access)
    document_query = db.query(GuidelineDocument).filter(
        GuidelineDocument.workspace_id == access.workspace_id,
    )
    documents = document_query.order_by(GuidelineDocument.created_at.desc()).all()
    return [
        {
            'id': document.id,
            'original_filename': document.original_filename,
            'provider': document.provider,
            'model_used': document.model_used,
            'created_at': document.created_at,
            'rules_saved': db.query(BrandGuideline.id).filter(
                BrandGuideline.workspace_id == access.workspace_id,
                BrandGuideline.source_document_id == document.id,
            ).count(),
        }
        for document in documents
    ]


@router.get('/guideline-history')
def list_guideline_history(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_workspace_manager(access)
    history = db.query(GuidelineHistory).filter(
        GuidelineHistory.workspace_id == access.workspace_id,
    ).order_by(GuidelineHistory.created_at.desc()).limit(100).all()
    return [
        {
            'id': item.id,
            'guideline_id': item.guideline_id,
            'document_id': item.document_id,
            'actor_user_id': item.actor_user_id,
            'action': item.action,
            'details': item.details,
            'created_at': item.created_at,
        }
        for item in history
    ]


@router.get('/guidelines', response_model=list[GuidelineOut])
def list_guidelines(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
    category: str | None = Query(default=None),
    active: bool | None = Query(default=None),
):
    query = db.query(BrandGuideline).filter(BrandGuideline.workspace_id == access.workspace_id)
    if access.app_role != 'brand_admin':
        query = query.filter(BrandGuideline.active.is_(True))
    if category:
        query = query.filter(BrandGuideline.category.ilike(category))
    if active is not None:
        query = query.filter(BrandGuideline.active.is_(active))
    return query.order_by(BrandGuideline.created_at.desc()).all()


@router.post('/guidelines', response_model=GuidelineOut, status_code=status.HTTP_201_CREATED)
def create_guideline(
    payload: GuidelineCreate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_workspace_manager(access)
    guideline = BrandGuideline(
        rule_name=payload.rule_name,
        category=payload.category,
        description=payload.description,
        rule_value=payload.rule_value,
        severity=payload.severity,
        active=payload.active,
        requirement_type=payload.requirement_type,
        user_id=user_id,
        workspace_id=access.workspace_id,
    )
    db.add(guideline)
    db.commit()
    db.refresh(guideline)
    db.add(GuidelineHistory(
        workspace_id=access.workspace_id,
        guideline_id=guideline.id,
        actor_user_id=user_id,
        action='created',
        details={'rule_name': guideline.rule_name, 'active': guideline.active},
    ))
    db.commit()
    return guideline


@router.get('/guidelines/{guideline_id}', response_model=GuidelineOut)
def get_guideline(
    guideline_id: int,
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    guideline = db.query(BrandGuideline).filter(
        BrandGuideline.id == guideline_id,
        BrandGuideline.workspace_id == access.workspace_id,
    ).first()
    if guideline and access.app_role != 'brand_admin' and not guideline.active:
        guideline = None
    if not guideline:
        raise HTTPException(status_code=404, detail='Guideline not found')
    return guideline


@router.patch('/guidelines/{guideline_id}', response_model=GuidelineOut)
def update_guideline(
    guideline_id: int,
    payload: GuidelineUpdate,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_workspace_manager(access)
    guideline = db.query(BrandGuideline).filter(
        BrandGuideline.id == guideline_id,
        BrandGuideline.workspace_id == access.workspace_id,
    ).first()
    if not guideline:
        raise HTTPException(status_code=404, detail='Guideline not found')

    changed = payload.model_dump(exclude_unset=True)
    old_active = guideline.active
    for field, value in changed.items():
        if value is not None:
            setattr(guideline, field, value)

    db.add(GuidelineHistory(
        workspace_id=access.workspace_id,
        guideline_id=guideline.id,
        actor_user_id=user_id,
        action='approved' if 'active' in changed and guideline.active else (
            'rejected' if 'active' in changed and old_active and not guideline.active else 'edited'
        ),
        details={'fields': list(changed)},
    ))
    db.commit()
    db.refresh(guideline)
    return guideline


@router.delete('/guidelines/{guideline_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_guideline(
    guideline_id: int,
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    require_mutation_allowed(access)
    require_workspace_manager(access)
    guideline = db.query(BrandGuideline).filter(
        BrandGuideline.id == guideline_id,
        BrandGuideline.workspace_id == access.workspace_id,
    ).first()
    if not guideline:
        raise HTTPException(status_code=404, detail='Guideline not found')

    db.add(GuidelineHistory(
        workspace_id=access.workspace_id,
        guideline_id=guideline.id,
        actor_user_id=user_id,
        action='deleted',
        details={'rule_name': guideline.rule_name},
    ))
    db.delete(guideline)
    db.commit()
