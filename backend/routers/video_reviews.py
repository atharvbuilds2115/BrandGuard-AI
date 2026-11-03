from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..auth import require_firebase_user
from ..database import get_db
from ..models import ActivityEvent, BrandGuideline, VideoReview
from ..schemas import VideoReviewOut
from ..services import video_service
from ..services.ai_provider import GeminiAnalysisError
from ..services.ai_provider import get_active_ai_provider
from ..services.ai_service import analyze_video_frames_with_model
from ..services.workspace_service import WorkspaceAccess
from ..workspace_auth import require_workspace_access

router = APIRouter(
    prefix='/api/video-reviews',
    tags=['video reviews'],
    dependencies=[Depends(require_workspace_access)],
)


@router.post('', response_model=VideoReviewOut, status_code=status.HTTP_201_CREATED)
async def create_video_review(
    file: UploadFile = File(...),
    user_id: str = Depends(require_firebase_user),
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    content = await file.read(video_service.MAX_VIDEO_SIZE_BYTES + 1)
    if len(content) > video_service.MAX_VIDEO_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='The video exceeds the 50 MB upload limit.')
    try:
        duration_seconds, frames = await run_in_threadpool(
            video_service.extract_video_frames,
            content,
            file.filename or '',
        )
        guidelines = db.query(BrandGuideline).filter(
            BrandGuideline.workspace_id == access.workspace_id,
            BrandGuideline.active.is_(True),
        ).all()
        findings, model_used, fallback_used = await run_in_threadpool(
            analyze_video_frames_with_model,
            frames,
            guidelines,
        )
        risk_score, risk_category, compliance_score = video_service.score_video_findings(findings)
    except video_service.VideoProcessingError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except GeminiAnalysisError as error:
        raise HTTPException(status_code=error.http_status_code, detail=str(error)) from error

    review = VideoReview(
        original_filename=(file.filename or 'video')[:255],
        duration_seconds=round(duration_seconds, 2),
        frame_count=len(frames),
        risk_score=risk_score,
        risk_category=risk_category,
        compliance_score=compliance_score,
        model_used=model_used,
        fallback_used=fallback_used,
        analysis_mode=f'{get_active_ai_provider()}_assisted',
        findings=findings,
        user_id=user_id,
        workspace_id=access.workspace_id,
    )
    db.add(review)
    db.flush()
    db.add(ActivityEvent(
        event_type='Video review completed',
        description=f'Video review completed for {review.original_filename}',
        related_entity_id=str(review.id),
        user_id=user_id,
        workspace_id=access.workspace_id,
    ))
    db.commit()
    db.refresh(review)
    return review


@router.get('', response_model=list[VideoReviewOut])
def list_video_reviews(
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    return db.query(VideoReview).filter(
        VideoReview.workspace_id == access.workspace_id,
    ).order_by(VideoReview.created_at.desc()).limit(100).all()


@router.get('/{review_id}', response_model=VideoReviewOut)
def get_video_review(
    review_id: int,
    access: WorkspaceAccess = Depends(require_workspace_access),
    db: Session = Depends(get_db),
):
    review = db.query(VideoReview).filter(
        VideoReview.id == review_id,
        VideoReview.workspace_id == access.workspace_id,
    ).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Video review not found.')
    return review