from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import Asset, Audit, BrandGuideline
from ..schemas import GlobalSearchResultOut
from ..services.workspace_service import WorkspaceAccess
from ..workspace_auth import require_workspace_access

router = APIRouter(prefix='/api', tags=['search'], dependencies=[Depends(require_workspace_access)])
_RESULTS_PER_CATEGORY = 5


def _contains(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@router.get('/search', response_model=list[GlobalSearchResultOut])
def search_workspace(
    q: str = Query(default='', max_length=120),
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
) -> list[GlobalSearchResultOut]:
    query = q.strip()
    if not query:
        return []

    pattern = _contains(query)
    audits = (
        db.query(Audit)
        .filter(
            Audit.workspace_id == access.workspace_id,
            or_(
                Audit.campaign_name.ilike(pattern, escape='\\'),
                Audit.campaign_type.ilike(pattern, escape='\\'),
                Audit.submitted_content.ilike(pattern, escape='\\'),
            ),
        )
        .order_by(Audit.created_at.desc(), Audit.id.desc())
        .limit(_RESULTS_PER_CATEGORY)
        .all()
    )
    assets = (
        db.query(Asset)
        .filter(
            Asset.workspace_id == access.workspace_id,
            or_(
                Asset.original_filename.ilike(pattern, escape='\\'),
                Asset.campaign_name.ilike(pattern, escape='\\'),
                Asset.tags.ilike(pattern, escape='\\'),
            ),
        )
        .order_by(Asset.uploaded_at.desc(), Asset.id.desc())
        .limit(_RESULTS_PER_CATEGORY)
        .all()
    )
    guidelines = (
        db.query(BrandGuideline)
        .filter(
            BrandGuideline.workspace_id == access.workspace_id,
            BrandGuideline.active.is_(True),
            or_(
                BrandGuideline.rule_name.ilike(pattern, escape='\\'),
                BrandGuideline.category.ilike(pattern, escape='\\'),
                BrandGuideline.description.ilike(pattern, escape='\\'),
                BrandGuideline.rule_value.ilike(pattern, escape='\\'),
            ),
        )
        .order_by(BrandGuideline.updated_at.desc(), BrandGuideline.id.desc())
        .limit(_RESULTS_PER_CATEGORY)
        .all()
    )

    results = [
        GlobalSearchResultOut(
            category='Campaign',
            id=audit.id,
            name=audit.campaign_name,
            description=_short_description(f'{audit.campaign_type} campaign · {audit.risk_category.title()} risk'),
        )
        for audit in audits
    ]
    results.extend(
        GlobalSearchResultOut(
            category='Asset',
            id=asset.id,
            name=asset.original_filename,
            description=_short_description(' · '.join(part for part in (
                asset.campaign_name or '',
                asset.mime_type,
                ', '.join(_asset_tags(asset.tags)),
            ) if part) or 'Uploaded asset'),
        )
        for asset in assets
    )
    results.extend(
        GlobalSearchResultOut(
            category='Guideline',
            id=guideline.id,
            name=guideline.rule_name,
            description=_short_description(guideline.description or guideline.category),
        )
        for guideline in guidelines
    )
    return results


def _short_description(value: str, max_length: int = 160) -> str:
    description = value.strip()
    if len(description) <= max_length:
        return description
    return f'{description[:max_length - 3].rstrip()}...'


def _asset_tags(tags: str) -> list[str]:
    try:
        value = json.loads(tags)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [tag for tag in value if isinstance(tag, str)]
