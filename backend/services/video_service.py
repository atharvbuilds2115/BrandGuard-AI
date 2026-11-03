from __future__ import annotations

import base64
import hashlib
import math
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2


MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 180
MAX_VIDEO_FRAMES = 12
MAX_VIDEO_FRAME_DIMENSION = 768
MAX_ANALYSIS_IMAGE_BYTES = 6 * 1024 * 1024
MAX_FRAME_EXTRACTION_SECONDS = 25
SUPPORTED_VIDEO_EXTENSIONS = {'.avi', '.m4v', '.mov', '.mp4', '.webm'}
_SEVERITY_WEIGHTS = {'low': 10, 'medium': 20, 'high': 35}


class VideoProcessingError(ValueError):
    pass


def score_video_findings(findings: list[dict[str, Any]]) -> tuple[int, str, int]:
    risk_score = min(
        100,
        sum(_SEVERITY_WEIGHTS.get(str(finding.get('severity', '')).casefold(), 0) for finding in findings),
    )
    risk_category = 'high' if risk_score >= 70 else 'medium' if risk_score >= 35 else 'low'
    return risk_score, risk_category, 100 - risk_score


def extract_video_frames(content: bytes, filename: str) -> tuple[float, list[dict[str, Any]]]:
    if not content:
        raise VideoProcessingError('The uploaded video is empty.')
    if len(content) > MAX_VIDEO_SIZE_BYTES:
        raise VideoProcessingError('The video exceeds the 50 MB upload limit.')
    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_VIDEO_EXTENSIONS:
        raise VideoProcessingError('Upload an MP4, MOV, M4V, AVI, or WebM video.')

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory) / f'upload{suffix}'
        temporary_path.write_bytes(content)
        capture = cv2.VideoCapture(str(temporary_path))
        if not capture.isOpened():
            capture.release()
            raise VideoProcessingError('OpenCV could not read this video. Check the file format and codec.')

        try:
            frame_rate = float(capture.get(cv2.CAP_PROP_FPS))
            source_frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if (
                not math.isfinite(frame_rate)
                or not math.isfinite(source_frame_count)
                or frame_rate <= 0
                or source_frame_count <= 0
            ):
                raise VideoProcessingError('The video duration or frame rate could not be determined.')
            duration_seconds = source_frame_count / frame_rate
            if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
                raise VideoProcessingError('The video exceeds the 180 second duration limit.')

            sample_count = min(MAX_VIDEO_FRAMES, max(1, math.ceil(duration_seconds / 10)))
            last_frame = max(0, int(source_frame_count) - 1)
            sample_indices = sorted({
                round(index * last_frame / max(1, sample_count - 1))
                for index in range(sample_count)
            })
            frames: list[dict[str, Any]] = []
            encoded_size = 0
            seen_frames: set[bytes] = set()
            started_at = time.monotonic()
            for frame_index in sample_indices:
                if time.monotonic() - started_at > MAX_FRAME_EXTRACTION_SECONDS:
                    raise VideoProcessingError('Video frame extraction exceeded its 25 second processing limit.')
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                success, frame = capture.read()
                if not success or frame is None:
                    raise VideoProcessingError('OpenCV could not decode a sampled video frame.')

                height, width = frame.shape[:2]
                scale = min(1.0, MAX_VIDEO_FRAME_DIMENSION / max(height, width))
                if scale < 1.0:
                    frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
                encoded, image = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not encoded:
                    raise VideoProcessingError('A sampled frame could not be encoded for analysis.')
                image_bytes = image.tobytes()
                fingerprint = hashlib.sha256(image_bytes).digest()
                if fingerprint in seen_frames:
                    continue
                seen_frames.add(fingerprint)
                encoded_size += image.nbytes
                if encoded_size > MAX_ANALYSIS_IMAGE_BYTES:
                    raise VideoProcessingError('The sampled frames exceed the 6 MB analysis processing limit.')
                timestamp_seconds = round(frame_index / frame_rate, 2)
                frames.append({
                    'timestamp_seconds': timestamp_seconds,
                    'image_base64': base64.b64encode(image_bytes).decode('ascii'),
                    'mime_type': 'image/jpeg',
                })
            return duration_seconds, frames
        finally:
            capture.release()