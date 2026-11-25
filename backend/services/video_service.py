from __future__ import annotations

import base64
import hashlib
import logging
import math
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np


MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 180
MAX_VIDEO_FRAMES = 12
MAX_VIDEO_FRAME_DIMENSION = 768
MAX_ANALYSIS_IMAGE_BYTES = 12 * 1024 * 1024
MAX_FRAME_EXTRACTION_SECONDS = 25
SUPPORTED_VIDEO_EXTENSIONS = {'.avi', '.m4v', '.mov', '.mp4', '.webm'}
_SEVERITY_WEIGHTS = {'low': 10, 'medium': 20, 'high': 35}
_DURATION_PATTERN = re.compile(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)')
_FFMPEG_SCALE_FILTER = (
    f"scale='min({MAX_VIDEO_FRAME_DIMENSION},iw)':"
    f"'min({MAX_VIDEO_FRAME_DIMENSION},ih)':force_original_aspect_ratio=decrease"
)
_logger = logging.getLogger(__name__)


class VideoProcessingError(ValueError):
    pass


class _FrameExtractionFailed(Exception):
    pass


def score_video_findings(findings: list[dict[str, Any]]) -> tuple[int, str, int]:
    risk_score = min(
        100,
        sum(_SEVERITY_WEIGHTS.get(str(finding.get('severity', '')).casefold(), 0) for finding in findings),
    )
    risk_category = 'high' if risk_score >= 70 else 'medium' if risk_score >= 35 else 'low'
    return risk_score, risk_category, 100 - risk_score


def _check_time_limit(started_at: float) -> None:
    if time.monotonic() - started_at > MAX_FRAME_EXTRACTION_SECONDS:
        raise VideoProcessingError('Video frame extraction exceeded its 25 second processing limit.')


def _sample_timestamps(duration_seconds: float) -> list[float]:
    sample_count = min(MAX_VIDEO_FRAMES, max(1, math.ceil(duration_seconds / 10)))
    if sample_count == 1:
        return [0.0]
    last_timestamp = duration_seconds - min(1.0, duration_seconds / (sample_count - 1))
    return [
        last_timestamp * index / (sample_count - 1)
        for index in range(sample_count)
    ]


def _encode_frame(frame: Any, timestamp_seconds: float) -> tuple[dict[str, Any], bytes]:
    if frame is None or not hasattr(frame, 'shape') or len(frame.shape) < 2:
        raise _FrameExtractionFailed
    height, width = frame.shape[:2]
    if height <= 0 or width <= 0:
        raise _FrameExtractionFailed
    scale = min(1.0, MAX_VIDEO_FRAME_DIMENSION / max(height, width))
    if scale < 1.0:
        frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
    encoded, image = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not encoded or image is None:
        raise _FrameExtractionFailed
    image_bytes = image.tobytes()
    if not image_bytes:
        raise _FrameExtractionFailed
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None or decoded.size == 0:
        raise _FrameExtractionFailed
    return ({
        'timestamp_seconds': round(timestamp_seconds, 2),
        'image_base64': base64.b64encode(image_bytes).decode('ascii'),
        'mime_type': 'image/jpeg',
    }, image_bytes)


def _collect_sample(
    frame: Any,
    timestamp_seconds: float,
    frames: list[dict[str, Any]],
    seen_frames: set[bytes],
    encoded_size: int,
) -> int:
    item, image_bytes = _encode_frame(frame, timestamp_seconds)
    fingerprint = hashlib.sha256(image_bytes).digest()
    if fingerprint in seen_frames:
        return encoded_size
    new_size = encoded_size + len(image_bytes)
    if new_size > MAX_ANALYSIS_IMAGE_BYTES:
        raise VideoProcessingError('The sampled frames exceed the 12 MB analysis processing limit.')
    seen_frames.add(fingerprint)
    frames.append(item)
    return new_size


def _extract_with_opencv(
    video_path: Path,
    started_at: float,
) -> tuple[float, list[dict[str, Any]]] | None:
    capture = None
    try:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            return None
        frame_rate = float(capture.get(cv2.CAP_PROP_FPS))
        source_frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if (
            not math.isfinite(frame_rate)
            or not math.isfinite(source_frame_count)
            or frame_rate <= 0
            or source_frame_count <= 0
        ):
            return None
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
        for frame_index in sample_indices:
            _check_time_limit(started_at)
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                return None
            success, frame = capture.read()
            if not success or frame is None:
                return None
            try:
                encoded_size = _collect_sample(
                    frame,
                    frame_index / frame_rate,
                    frames,
                    seen_frames,
                    encoded_size,
                )
            except _FrameExtractionFailed:
                return None
        if not frames:
            return None
        return duration_seconds, frames
    except cv2.error:
        return None
    finally:
        if capture is not None:
            capture.release()


def _run_ffmpeg(
    executable: str,
    arguments: list[str],
    started_at: float,
) -> subprocess.CompletedProcess[bytes]:
    _check_time_limit(started_at)
    remaining = MAX_FRAME_EXTRACTION_SECONDS - (time.monotonic() - started_at)
    try:
        return subprocess.run(
            [executable, *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=max(0.1, remaining),
        )
    except subprocess.TimeoutExpired as error:
        raise VideoProcessingError(
            'Video frame extraction exceeded its 25 second processing limit.'
        ) from error


def _extract_with_ffmpeg(
    video_path: Path,
    duration_hint: float | None,
    started_at: float,
) -> tuple[float, list[dict[str, Any]]]:
    try:
        import imageio_ffmpeg

        executable = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as error:
        _logger.error('FFmpeg fallback is unavailable; video decoding could not continue.')
        raise VideoProcessingError(
            'Video decoding is unavailable on the server. Please try again later.'
        ) from error

    first_result = _run_ffmpeg(executable, [
        '-hide_banner',
        '-loglevel', 'info',
        '-i', str(video_path),
        '-map', '0:v:0',
        '-frames:v', '1',
        '-vf', _FFMPEG_SCALE_FILTER,
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',
        'pipe:1',
    ], started_at)
    duration_seconds = duration_hint
    if duration_seconds is None or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        match = _DURATION_PATTERN.search(first_result.stderr.decode('utf-8', errors='replace'))
        if match:
            hours, minutes, seconds = match.groups()
            duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration_seconds is None or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        _logger.warning('FFmpeg could not determine the video duration.')
        raise VideoProcessingError(
            'The video duration could not be determined. The file may be corrupted or unsupported.'
        )
    if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
        raise VideoProcessingError('The video exceeds the 180 second duration limit.')

    if first_result.returncode != 0 or not first_result.stdout:
        _logger.warning('FFmpeg could not decode the first video frame (exit_code=%s).', first_result.returncode)
        raise VideoProcessingError(
            'This video could not be decoded. It may be corrupted or use an unsupported codec or container.'
        )

    frames: list[dict[str, Any]] = []
    seen_frames: set[bytes] = set()
    encoded_size = 0
    timestamps = _sample_timestamps(duration_seconds)
    for sample_index, timestamp_seconds in enumerate(timestamps):
        _check_time_limit(started_at)
        if sample_index == 0:
            result = first_result
        else:
            result = _run_ffmpeg(executable, [
                '-hide_banner',
                '-loglevel', 'error',
                '-ss', f'{timestamp_seconds:.3f}',
                '-i', str(video_path),
                '-map', '0:v:0',
                '-frames:v', '1',
                '-vf', _FFMPEG_SCALE_FILTER,
                '-f', 'image2pipe',
                '-vcodec', 'mjpeg',
                'pipe:1',
            ], started_at)
        if result.returncode != 0 or not result.stdout:
            _logger.warning('FFmpeg could not decode a sampled frame (sample=%d).', sample_index)
            raise VideoProcessingError(
                'This video could not be decoded. It may be corrupted or use an unsupported codec or container.'
            )
        frame = cv2.imdecode(np.frombuffer(result.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)
        try:
            encoded_size = _collect_sample(
                frame,
                timestamp_seconds,
                frames,
                seen_frames,
                encoded_size,
            )
        except _FrameExtractionFailed as error:
            _logger.warning('FFmpeg produced an invalid sampled frame (sample=%d).', sample_index)
            raise VideoProcessingError(
                'A sampled video frame could not be validated. The file may be corrupted or unsupported.'
            ) from error
    if not frames:
        raise VideoProcessingError('No valid video frames could be extracted for analysis.')
    return duration_seconds, frames


def extract_video_frames(content: bytes, filename: str) -> tuple[float, list[dict[str, Any]]]:
    if not content:
        raise VideoProcessingError('The uploaded video is empty.')
    if len(content) > MAX_VIDEO_SIZE_BYTES:
        raise VideoProcessingError('The video exceeds the 50 MB upload limit.')
    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_VIDEO_EXTENSIONS:
        raise VideoProcessingError('Upload an MP4, MOV, M4V, AVI, or WebM video.')

    started_at = time.monotonic()
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory) / f'upload{suffix}'
        written_size = temporary_path.write_bytes(content)
        if written_size != len(content):
            raise VideoProcessingError('The uploaded video could not be written for decoding.')
        try:
            result = _extract_with_opencv(temporary_path, started_at)
        except VideoProcessingError:
            raise
        if result is not None:
            return result
        _logger.info('OpenCV could not extract all sampled frames; trying FFmpeg fallback (extension=%s).', suffix)
        return _extract_with_ffmpeg(temporary_path, None, started_at)
