from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..database import Base
from ..models import Asset
from .document_service import extract_text_from_file


MAX_UPLOAD_SIZE_BYTES = int(os.getenv('MAX_UPLOAD_SIZE_MB', '10')) * 1024 * 1024

ALLOWED_MIME_TYPES = {
    'text/plain',
    'text/csv',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'image/png',
    'image/jpeg',
    'image/webp',
}

ALLOWED_SUFFIXES = {'.txt', '.csv', '.pdf', '.docx', '.png', '.jpg', '.jpeg', '.webp'}


def get_upload_directory() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent.resolve()
    configured_value = os.getenv('UPLOAD_DIR', '').strip()
    if configured_value:
        configured_directory = Path(configured_value).expanduser()
        if not configured_directory.is_absolute():
            configured_directory = backend_dir / configured_directory
    else:
        local_app_data = os.getenv('LOCALAPPDATA') or str(Path.home() / '.local' / 'share')
        data_dir = Path(local_app_data)
        configured_directory = data_dir / 'BrandGuardAI' / 'uploads'

    resolved_directory = configured_directory.resolve()
    if resolved_directory == project_dir or project_dir in resolved_directory.parents:
        raise RuntimeError('UPLOAD_DIR must resolve outside the project directory so files are not publicly served.')
    return resolved_directory


def validate_upload(file: UploadFile, content: bytes) -> None:
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError('Unsupported file type.')

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise ValueError('Unsupported MIME type.')

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise ValueError('File exceeds the maximum upload size.')


def persist_asset(
    db: Session,
    file: UploadFile,
    content: bytes,
    campaign_name: str | None,
    user_id: str,
) -> Asset:
    validate_upload(file, content)

    upload_dir = get_upload_directory()
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or '').suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    save_path = upload_dir / safe_name
    save_path.write_bytes(content)

    extracted_text = extract_text_from_file(str(save_path), file.content_type or '')

    asset = Asset(
        original_filename=Path(file.filename or 'upload').name,
        stored_filename=safe_name,
        mime_type=file.content_type or 'application/octet-stream',
        file_size=len(content),
        campaign_name=campaign_name,
        tags='["uploaded"]',
        extracted_text=extracted_text,
        review_status='pending',
        file_path=str(save_path),
        user_id=user_id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset
