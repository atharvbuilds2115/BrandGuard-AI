from __future__ import annotations

from collections.abc import Iterator
import base64
import json
from types import SimpleNamespace

import cv2
import httpx
import numpy as np
import pytest
from groq import APIStatusError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import require_firebase_user
from backend import database as backend_database
from backend.database import Base, get_db
from backend.models import VideoReview
from backend.routers.video_reviews import router as video_reviews_router
from backend.services import groq_service, video_service
from backend.services.gemini_service import (
    GeminiAnalysisError,
    analyze_video_frames,
    analyze_video_frames_with_model,
)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from backend.services import gemini_service

    monkeypatch.setattr(gemini_service, '_BACKEND_ENV_FILE', tmp_path / 'test.env')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {'uid': 'video-user-a'}
    app = FastAPI()
    app.include_router(video_reviews_router)

    def override_db() -> Iterator[Session]:
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_firebase_user] = lambda: identity['uid']
    client = TestClient(app)
    try:
        yield client, identity
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _fake_frames(_content: bytes, _filename: str) -> tuple[float, list[dict]]:
    return 12.0, [{
        'timestamp_seconds': 0.0,
        'image_base64': 'ZmFrZQ==',
        'mime_type': 'image/jpeg',
    }]


def test_video_review_is_saved_and_scoped_to_authenticated_user(
    api: tuple[TestClient, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setattr(
        'backend.routers.video_reviews.analyze_video_frames_with_model',
        lambda _frames, _guidelines: ([{
                'timestamp_seconds': 0.0,
                'timestamp': '00:00',
                'title': 'Logo changes between frames',
                'severity': 'medium',
                'category': 'logo',
                'evidence': 'The visible logo appears stretched.',
                'explanation': 'The logo proportions differ from surrounding frames.',
                'suggested_correction': 'Use the approved logo asset at its original proportions.',
                'status': 'needs_verification',
            }], 'gemini-3.8-flash', False),
    )

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})
    assert response.status_code == 201
    body = response.json()
    assert body['frame_count'] == 1
    assert body['risk_score'] == 20
    assert body['risk_category'] == 'low'
    assert body['compliance_score'] == 80
    assert body['model_used'] == 'gemini-3.8-flash'
    assert body['fallback_used'] is False
    assert body['findings'][0]['timestamp'] == '00:00'
    assert client.get('/api/video-reviews').json()[0]['id'] == body['id']

    identity['uid'] = 'video-user-b'
    assert client.get('/api/video-reviews').json() == []
    assert client.get(f"/api/video-reviews/{body['id']}").status_code == 404


def test_video_upload_rejects_files_over_size_limit(
    api: tuple[TestClient, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'MAX_VIDEO_SIZE_BYTES', 4)
    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'12345', 'video/mp4')})
    assert response.status_code == 413
    assert response.json()['detail'] == 'The video exceeds the 50 MB upload limit.'


def test_video_decode_failure_is_not_saved(
    api: tuple[TestClient, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api

    def fail_extraction(_content: bytes, _filename: str) -> tuple[float, list[dict]]:
        raise video_service.VideoProcessingError(
            'This video could not be decoded. It may be corrupted or use an unsupported codec or container.'
        )

    monkeypatch.setattr(video_service, 'extract_video_frames', fail_extraction)

    response = client.post('/api/video-reviews', files={'file': ('broken.mp4', b'video', 'video/mp4')})

    assert response.status_code == 400
    assert 'corrupted or use an unsupported codec' in response.json()['detail']
    assert client.get('/api/video-reviews').json() == []


def test_video_review_reports_missing_gemini_configuration(
    api: tuple[TestClient, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setattr(
        'backend.routers.video_reviews.analyze_video_frames_with_model',
        lambda _frames, _guidelines: (_ for _ in ()).throw(
            GeminiAnalysisError('GEMINI_API_KEY is not configured; video analysis was not run and no review was saved.')
        ),
    )
    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})
    assert response.status_code == 503
    assert 'GEMINI_API_KEY is not configured' in response.json()['detail']
    assert client.get('/api/video-reviews').json() == []


def test_video_analysis_timeout_is_returned_without_saving_a_review(
    api: tuple[TestClient, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setattr(
        'backend.routers.video_reviews.analyze_video_frames_with_model',
        lambda _frames, _guidelines: (_ for _ in ()).throw(
            GeminiAnalysisError('Gemini timed out; no review was saved.', http_status_code=504)
        ),
    )

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 504
    assert 'no review was saved' in response.json()['detail']
    assert client.get('/api/video-reviews').json() == []


def test_video_review_requires_authentication() -> None:
    app = FastAPI()
    app.include_router(video_reviews_router)
    client = TestClient(app)
    response = client.get('/api/video-reviews')
    assert response.status_code == 401


def test_frame_extraction_caps_samples_and_rejects_long_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCapture:
        def __init__(self, _path: str) -> None:
            self.seek = 0
            self.read_count = 0

        def isOpened(self) -> bool:
            return True

        def get(self, prop: int) -> float:
            if prop == video_service.cv2.CAP_PROP_FPS:
                return 10.0
            return 1200.0

        def set(self, _prop: int, value: float) -> bool:
            self.seek = int(value)
            return True

        def read(self) -> tuple[bool, object]:
            self.read_count += 1
            return True, SimpleNamespace(shape=(1080, 1920, 3))

        def release(self) -> None:
            return None

    capture = FakeCapture('')
    monkeypatch.setattr(video_service.cv2, 'VideoCapture', lambda _path: capture)
    encoded_shapes: list[tuple[int, int, int]] = []
    encoded_qualities: list[int] = []

    def fake_resize(_frame: object, size: tuple[int, int]) -> SimpleNamespace:
        return SimpleNamespace(shape=(size[1], size[0], 3))

    real_imencode = cv2.imencode

    def fake_encode(_extension: str, frame: SimpleNamespace, parameters: list[int]) -> tuple[bool, np.ndarray]:
        encoded_shapes.append(frame.shape)
        encoded_qualities.append(parameters[1])
        pixels = np.full((8, 8, 3), capture.seek % 256, dtype=np.uint8)
        return real_imencode('.jpg', pixels)

    monkeypatch.setattr(video_service.cv2, 'resize', fake_resize)
    monkeypatch.setattr(video_service.cv2, 'imencode', fake_encode)
    duration, frames = video_service.extract_video_frames(b'video', 'clip.mp4')
    assert duration == 120.0
    assert len(frames) == video_service.MAX_VIDEO_FRAMES
    assert capture.read_count == video_service.MAX_VIDEO_FRAMES
    assert frames[0]['timestamp_seconds'] == 0
    assert frames[-1]['timestamp_seconds'] == 119.9
    assert encoded_shapes[0] == (432, 768, 3)
    assert set(encoded_qualities) == {70}

    monkeypatch.setattr(FakeCapture, 'get', lambda self, prop: 10.0 if prop == video_service.cv2.CAP_PROP_FPS else 1810.0)
    with pytest.raises(video_service.VideoProcessingError, match='180 second duration limit'):
        video_service.extract_video_frames(b'video', 'clip.mp4')


def test_frame_extraction_skips_duplicate_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCapture:
        def __init__(self, _path: str) -> None:
            self.seek = 0

        def isOpened(self) -> bool:
            return True

        def get(self, prop: int) -> float:
            return 10.0 if prop == video_service.cv2.CAP_PROP_FPS else 300.0

        def set(self, _prop: int, value: float) -> bool:
            self.seek = int(value)
            return True

        def read(self) -> tuple[bool, object]:
            return True, SimpleNamespace(shape=(360, 640, 3))

        def release(self) -> None:
            return None

    monkeypatch.setattr(video_service.cv2, 'VideoCapture', FakeCapture)
    same_frame = cv2.imencode('.jpg', np.zeros((8, 8, 3), dtype=np.uint8))[1]
    monkeypatch.setattr(video_service.cv2, 'imencode', lambda *_args: (True, same_frame))

    _duration, frames = video_service.extract_video_frames(b'video', 'clip.mp4')

    assert len(frames) == 1


def test_frame_extraction_decodes_a_real_mp4(tmp_path) -> None:
    video_path = tmp_path / 'sample.mp4'
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*'mp4v'),
        10.0,
        (320, 240),
    )
    if not writer.isOpened():
        pytest.skip('OpenCV MP4 encoding is unavailable in this environment.')
    for frame_index in range(20):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(frame, str(frame_index), (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()

    duration, frames = video_service.extract_video_frames(video_path.read_bytes(), video_path.name)

    assert duration == pytest.approx(2.0)
    assert len(frames) == 1
    jpeg_bytes = base64.b64decode(frames[0]['image_base64'])
    decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert max(decoded.shape[:2]) <= video_service.MAX_VIDEO_FRAME_DIMENSION


def test_frame_extraction_uses_ffmpeg_for_a_real_mp4_when_opencv_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path = tmp_path / 'fallback-sample.mp4'
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*'mp4v'),
        10.0,
        (320, 240),
    )
    if not writer.isOpened():
        pytest.skip('OpenCV MP4 encoding is unavailable in this environment.')
    for frame_index in range(120):
        frame = np.full((240, 320, 3), frame_index * 2, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    class FailedCapture:
        def isOpened(self) -> bool:
            return True

        def get(self, prop: int) -> float:
            return 10.0 if prop == video_service.cv2.CAP_PROP_FPS else 20.0

        def set(self, _prop: int, _value: float) -> bool:
            return True

        def read(self) -> tuple[bool, None]:
            return False, None

        def release(self) -> None:
            return None

    monkeypatch.setattr(video_service.cv2, 'VideoCapture', lambda _path: FailedCapture())

    duration, frames = video_service.extract_video_frames(video_path.read_bytes(), video_path.name)

    assert duration == pytest.approx(12.0)
    assert len(frames) == 2
    assert frames[-1]['timestamp_seconds'] == pytest.approx(11.0)
    decoded = cv2.imdecode(
        np.frombuffer(base64.b64decode(frames[0]['image_base64']), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert decoded is not None
    assert decoded.size > 0


def test_invalid_video_returns_clear_error(tmp_path) -> None:
    with pytest.raises(video_service.VideoProcessingError, match='corrupted or unsupported'):
        video_service.extract_video_frames(b'not a video', 'broken.mp4')


def test_video_analysis_retries_timeouts_and_uses_long_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.8-flash')
    attempts: list[object] = []
    request_urls: list[str] = []
    result_payload = {'findings': []}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(result_payload)}]}}]}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: object) -> FakeResponse:
        attempts.append(timeout)
        request_urls.append(url)
        if len(attempts) < 3:
            raise httpx.ReadTimeout('temporary timeout')
        return FakeResponse()

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', lambda _seconds: None)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda _lower, _upper: 0)

    findings = analyze_video_frames(_fake_frames(b'', '')[1], [])

    assert findings == []
    assert len(attempts) == 3
    assert attempts[0].read == 120.0
    assert attempts[0].connect == 10.0
    assert request_urls == [
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent',
    ] * 3


def test_video_analysis_retries_503_and_honors_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    sleeps: list[float] = []
    requests: list[tuple[str, dict]] = []

    def fake_post(url: str, *, headers: dict, json: dict, timeout: object) -> httpx.Response:
        requests.append((url, json))
        if len(requests) == 1:
            request = httpx.Request('POST', url)
            response = httpx.Response(
                503,
                headers={'Retry-After': '4'},
                json={'error': {'status': 'UNAVAILABLE', 'message': 'Model overloaded.'}},
                request=request,
            )
            raise httpx.HTTPStatusError('HTTP 503', request=request, response=response)
        return httpx.Response(
            200,
            json={'candidates': [{'content': {'parts': [{'text': '{"findings":[]}'}]}}]},
            request=httpx.Request('POST', url),
        )

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', sleeps.append)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda lower, _upper: lower)

    findings, model_used, fallback_used = analyze_video_frames_with_model(_fake_frames(b'', '')[1], [])
    assert findings == []
    assert model_used == 'gemini-3.8-flash'
    assert fallback_used is False
    assert len(requests) == 2
    assert requests[0] == requests[1]
    assert sleeps == [4.0]


def test_video_analysis_uses_exponential_jitter_without_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    sleeps: list[float] = []
    jitter_windows: list[tuple[float, float]] = []
    calls = 0

    def fake_uniform(lower: float, upper: float) -> float:
        jitter_windows.append((lower, upper))
        return upper

    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            request = httpx.Request('POST', url)
            response = httpx.Response(
                503,
                json={'error': {'status': 'UNAVAILABLE', 'message': 'Temporarily unavailable.'}},
                request=request,
            )
            raise httpx.HTTPStatusError('HTTP 503', request=request, response=response)
        return httpx.Response(
            200,
            json={'candidates': [{'content': {'parts': [{'text': '{"findings":[]}'}]}}]},
            request=httpx.Request('POST', url),
        )

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', sleeps.append)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', fake_uniform)

    findings, model_used, fallback_used = analyze_video_frames_with_model(_fake_frames(b'', '')[1], [])
    assert findings == []
    assert model_used == 'gemini-3.8-flash'
    assert fallback_used is False
    assert calls == 3
    assert jitter_windows == [(0.0, 1.0), (0.0, 2.0)]
    assert sleeps == [1.0, 2.0]


def test_video_analysis_falls_back_after_primary_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.6-flash')
    urls: list[str] = []

    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        urls.append(url)
        request = httpx.Request('POST', url)
        if 'gemini-3.8-flash' in url:
            response = httpx.Response(
                503,
                json={'error': {'status': 'UNAVAILABLE', 'message': 'Model temporarily overloaded.'}},
                request=request,
            )
            raise httpx.HTTPStatusError('HTTP 503', request=request, response=response)
        return httpx.Response(
            200,
            json={'candidates': [{'content': {'parts': [{'text': '{"findings":[]}'}]}}]},
            request=request,
        )

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', lambda _seconds: None)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda _lower, _upper: 0)

    findings, model_used, fallback_used = analyze_video_frames_with_model(_fake_frames(b'', '')[1], [])

    assert findings == []
    assert model_used == 'gemini-3.6-flash'
    assert fallback_used is True
    assert urls.count('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent') == 3
    assert urls.count('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent') == 1


def test_video_review_with_fallback_saves_model_and_fallback_metadata(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.6-flash')
    requests: list[str] = []

    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        requests.append(url)
        request = httpx.Request('POST', url)
        if 'gemini-3.8-flash' in url:
            response = httpx.Response(
                503,
                json={'error': {'status': 'UNAVAILABLE', 'message': 'Model overloaded.'}},
                request=request,
            )
            raise httpx.HTTPStatusError('HTTP 503', request=request, response=response)
        return httpx.Response(
            200,
            json={'candidates': [{'content': {'parts': [{
                'text': json.dumps({'findings': [{
                    'timestamp_seconds': 0.0,
                    'title': 'Logo appears stretched',
                    'severity': 'high',
                    'category': 'logo',
                    'evidence': 'The visible logo appears stretched.',
                    'explanation': 'The logo proportions differ from surrounding frames.',
                    'suggested_correction': 'Use the approved logo at its original proportions.',
                }]})
            }]}}]},
            request=request,
        )

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', lambda _seconds: None)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda _lower, _upper: 0)

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 201
    review = response.json()
    assert review['model_used'] == 'gemini-3.6-flash'
    assert review['fallback_used'] is True
    assert review['risk_score'] == 35
    assert review['risk_category'] == 'medium'
    assert review['compliance_score'] == 65
    assert review['findings'][0]['timestamp'] == '00:00'
    assert client.get(f"/api/video-reviews/{review['id']}").json() == review
    assert client.get('/api/video-reviews').json()[0] == review
    assert len(requests) == 4


def test_groq_batch_failure_does_not_save_partial_video_review(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    frames = [{
        'timestamp_seconds': float(index * 3),
        'image_base64': 'anBlZy1mcmFtZQ==',
        'mime_type': 'image/jpeg',
    } for index in range(4)]
    monkeypatch.setattr(video_service, 'extract_video_frames', lambda _content, _filename: (12.0, frames))
    monkeypatch.setenv('AI_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-groq-key')
    requests: list[dict] = []

    class FakeGroq:
        def __init__(self, **_kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self) -> FakeGroq:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def create(self, **kwargs: dict) -> SimpleNamespace:
            requests.append(kwargs)
            if len(requests) == 1:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"findings":[]}'))],
                )
            request = httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions')
            response = httpx.Response(
                503,
                headers={'Retry-After': '0'},
                json={'error': {'message': 'Model temporarily unavailable.'}},
                request=request,
            )
            raise APIStatusError('HTTP 503', response=response, body=response.json())

    monkeypatch.setattr(groq_service, 'Groq', FakeGroq)
    monkeypatch.setattr(groq_service.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(groq_service.random, 'uniform', lambda lower, _upper: lower)

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 503
    assert 'no ai result was saved' in response.json()['detail'].casefold()
    assert len(requests) == 4
    assert client.get('/api/video-reviews').json() == []


def test_groq_video_review_saves_only_completed_model_response(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setenv('AI_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-groq-key')

    class FakeGroq:
        def __init__(self, **_kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self) -> FakeGroq:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def create(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"findings":[]}'))],
            )

    monkeypatch.setattr(groq_service, 'Groq', FakeGroq)

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 201
    review = response.json()
    assert review['analysis_mode'] == 'groq_assisted'
    assert review['model_used'] == 'qwen/qwen3.8-27b'
    assert review['fallback_used'] is False
    assert client.get(f"/api/video-reviews/{review['id']}").json() == review


def test_groq_daily_quota_error_does_not_save_video_review(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setenv('AI_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-groq-key')
    calls = 0

    class FakeGroq:
        def __init__(self, **_kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self) -> FakeGroq:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def create(self, **_kwargs: object) -> None:
            nonlocal calls
            calls += 1
            request = httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions')
            response = httpx.Response(
                429,
                json={'error': {'message': 'Daily request quota exhausted.'}},
                request=request,
            )
            raise APIStatusError('HTTP 429', response=response, body=response.json())

    monkeypatch.setattr(groq_service, 'Groq', FakeGroq)
    monkeypatch.setattr(
        groq_service.time,
        'sleep',
        lambda _seconds: pytest.fail('A daily quota error must not be retried.'),
    )

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 429
    assert 'daily request quota' in response.json()['detail'].casefold()
    assert calls == 1
    assert client.get('/api/video-reviews').json() == []


def test_video_daily_quota_exhaustion_does_not_retry_fallback_or_save(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.6-flash')
    requests: list[str] = []

    def fake_post(url: str, **_kwargs: object) -> None:
        requests.append(url)
        request = httpx.Request('POST', url)
        response = httpx.Response(
            429,
            json={'error': {
                'status': 'RESOURCE_EXHAUSTED',
                'message': 'Daily Free Tier request quota exceeded.',
                'details': [{
                    'quotaFailure': {'violations': [{
                        'quotaMetric': 'generate_content_free_tier_requests',
                        'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier',
                    }]},
                }],
            }},
            request=request,
        )
        raise httpx.HTTPStatusError('HTTP 429', request=request, response=response)

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr(
        'backend.services.gemini_service.time.sleep',
        lambda _seconds: pytest.fail('Daily quota exhaustion must not be retried.'),
    )

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 429
    assert 'daily request quota has been exhausted' in response.json()['detail'].casefold()
    assert 'quota resets' in response.json()['detail'].casefold()
    assert 'no review was saved' in response.json()['detail'].casefold()
    assert requests == [
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent',
    ]
    assert client.get('/api/video-reviews').json() == []


def test_video_analysis_retries_temporary_429_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.6-flash')
    requests: list[str] = []
    sleeps: list[float] = []

    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        requests.append(url)
        if len(requests) == 1:
            request = httpx.Request('POST', url)
            response = httpx.Response(
                429,
                json={'error': {
                    'status': 'RESOURCE_EXHAUSTED',
                    'message': 'Too many requests. Please retry shortly.',
                }},
                request=request,
            )
            raise httpx.HTTPStatusError('HTTP 429', request=request, response=response)
        return httpx.Response(
            200,
            json={'candidates': [{'content': {'parts': [{'text': '{"findings":[]}'}]}}]},
            request=httpx.Request('POST', url),
        )

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', sleeps.append)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda _lower, _upper: 0)

    findings, model_used, fallback_used = analyze_video_frames_with_model(_fake_frames(b'', '')[1], [])

    assert findings == []
    assert model_used == 'gemini-3.8-flash'
    assert fallback_used is False
    assert len(requests) == 2
    assert requests[0] == requests[1]
    assert sleeps == [0]


def test_video_review_saves_nothing_when_primary_and_fallback_are_unavailable(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setattr(video_service, 'extract_video_frames', _fake_frames)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.6-flash')
    urls: list[str] = []

    def unavailable(url: str, **_kwargs: object) -> None:
        urls.append(url)
        request = httpx.Request('POST', url)
        response = httpx.Response(
            503,
            json={'error': {'status': 'UNAVAILABLE', 'message': 'High demand.'}},
            request=request,
        )
        raise httpx.HTTPStatusError('HTTP 503', request=request, response=response)

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', unavailable)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', lambda _seconds: None)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda _lower, _upper: 0)

    response = client.post('/api/video-reviews', files={'file': ('launch.mp4', b'video', 'video/mp4')})

    assert response.status_code == 503
    assert 'High demand.' in response.json()['detail']
    assert 'no review was saved' in response.json()['detail']
    assert len(urls) == 6
    assert client.get('/api/video-reviews').json() == []


@pytest.mark.parametrize(
    ('request_error', 'message', 'expected_http_status'),
    [
        (httpx.ReadTimeout('timed out'), 'timed out after three attempts', 504),
        (httpx.ConnectError('offline'), 'network error', 502),
    ],
)
def test_video_analysis_reports_exhausted_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
    request_error: httpx.RequestError,
    message: str,
    expected_http_status: int,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    attempts = 0

    def fake_post(_url: str, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise request_error

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', lambda _seconds: None)

    with pytest.raises(GeminiAnalysisError, match=message) as error:
        analyze_video_frames(_fake_frames(b'', '')[1], [])

    assert attempts == 3
    assert error.value.http_status_code == expected_http_status


@pytest.mark.parametrize(
    ('response_status', 'upstream_message', 'message', 'expected_calls', 'expected_http_status'),
    [
        (401, '', 'API key', 1, 502),
        (403, '', 'API key', 1, 502),
        (400, 'API key not valid', 'API key', 1, 502),
        (400, 'Invalid request', 'request as invalid', 1, 502),
        (404, '', 'GEMINI_MODEL', 1, 502),
        (501, 'Not implemented.', 'non-retryable HTTP 501', 1, 502),
        (429, 'Quota exceeded.', 'rate limits', 3, 503),
        (502, 'Bad gateway.', 'returned HTTP', 3, 503),
        (503, 'The model is overloaded. test-key', 'returned HTTP', 3, 503),
        (500, 'Internal provider error.', 'returned HTTP', 3, 503),
        (504, 'Gateway timeout.', 'returned HTTP', 3, 503),
    ],
)
def test_video_analysis_classifies_upstream_errors_and_retries_only_transient_statuses(
    monkeypatch: pytest.MonkeyPatch,
    response_status: int,
    upstream_message: str,
    message: str,
    expected_calls: int,
    expected_http_status: int,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.8-flash')
    calls = 0

    def fake_post(_url: str, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        request = httpx.Request('POST', 'https://example.test')
        raise httpx.HTTPStatusError(
            f'HTTP {response_status}',
            request=request,
            response=httpx.Response(
                response_status,
                json={
                    'error': {
                        'status': 'UNAVAILABLE' if response_status == 503 else 'PROVIDER_ERROR',
                        'message': upstream_message,
                    },
                },
                request=request,
            ),
        )

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    monkeypatch.setattr('backend.services.gemini_service.time.sleep', lambda _seconds: None)
    monkeypatch.setattr('backend.services.gemini_service.random.uniform', lambda _lower, _upper: 0)

    with pytest.raises(GeminiAnalysisError, match=message) as error:
        analyze_video_frames(_fake_frames(b'', '')[1], [])

    assert calls == expected_calls
    assert error.value.http_status_code == expected_http_status
    if response_status == 503:
        assert 'UNAVAILABLE' in str(error.value)
        assert 'The model is overloaded.' in str(error.value)
        assert 'test-key' not in str(error.value)
    if response_status in {500, 502, 503, 504}:
        assert f'HTTP {response_status}' in str(error.value)


def test_gemini_video_request_includes_image_and_validates_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_PRIMARY_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.6-flash')
    frames = [{
        'timestamp_seconds': 1.25,
        'image_base64': 'ZmFrZQ==',
        'mime_type': 'image/jpeg',
    }]
    result_payload = {'findings': [{
        'timestamp_seconds': 1.25,
        'title': 'Logo is distorted',
        'severity': 'high',
        'category': 'logo',
        'evidence': 'The mark is visibly stretched in this frame.',
        'explanation': 'The logo proportions differ from the supplied brand presentation.',
        'suggested_correction': 'Replace it with the approved logo asset at its original aspect ratio.',
    }]}
    request: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(result_payload)}]}}]}

    def fake_post(_url: str, *, headers: dict, json: dict, timeout: object) -> FakeResponse:
        request.update(json)
        assert headers['x-goog-api-key'] == 'test-key'
        return FakeResponse()

    monkeypatch.setattr('backend.services.gemini_service.httpx.post', fake_post)
    findings, model_used, fallback_used = analyze_video_frames_with_model(frames, [])
    submitted_parts = request['contents'][0]['parts']
    assert {'inlineData': {'mimeType': 'image/jpeg', 'data': 'ZmFrZQ=='}} in submitted_parts
    assert 'Do not claim audio analysis' in request['systemInstruction']['parts'][0]['text']
    task = json.loads(submitted_parts[0]['text'])['task']
    assert 'on-screen text and captions only when they are clearly legible' in task
    assert findings[0]['timestamp'] == '00:01'
    assert findings[0]['category'] == 'logo'
    assert model_used == 'gemini-3.8-flash'
    assert fallback_used is False

    result_payload['findings'][0]['timestamp_seconds'] = float('nan')
    with pytest.raises(GeminiAnalysisError, match='valid frame timestamp'):
        analyze_video_frames(frames, [])


def test_missing_gemini_key_error_identifies_backend_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        'backend.services.gemini_service._BACKEND_ENV_FILE',
        tmp_path / '.env',
    )
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(GeminiAnalysisError, match=r'Set it in backend/\.env'):
        analyze_video_frames(_fake_frames(b'', '')[1], [])


def test_gemini_settings_can_be_read_from_backend_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / '.env'
    env_file.write_text(
        'GEMINI_API_KEY=unit-test-key\nGEMINI_MODEL=gemini-3.8-flash\n',
        encoding='utf-8',
    )
    monkeypatch.setattr('backend.services.gemini_service._BACKEND_ENV_FILE', env_file)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_MODEL', raising=False)

    from backend.services import gemini_service

    assert gemini_service.gemini_is_configured()
    assert gemini_service._configured_value('GEMINI_MODEL') == 'gemini-3.8-flash'


@pytest.mark.parametrize(
    ('severities', 'expected_score', 'expected_category', 'expected_compliance'),
    [
        ([], 0, 'low', 100),
        (['high', 'medium'], 55, 'medium', 45),
        (['high', 'high', 'medium'], 90, 'high', 10),
    ],
)
def test_video_overall_scores_are_derived_from_findings(
    severities: list[str],
    expected_score: int,
    expected_category: str,
    expected_compliance: int,
) -> None:
    findings = [{'severity': severity} for severity in severities]
    assert video_service.score_video_findings(findings) == (
        expected_score,
        expected_category,
        expected_compliance,
    )


def test_video_review_schema_upgrade_preserves_existing_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-video.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE video_reviews ('
            'id INTEGER PRIMARY KEY, original_filename VARCHAR(255) NOT NULL, '
            'duration_seconds FLOAT NOT NULL, frame_count INTEGER NOT NULL, '
            'analysis_mode VARCHAR(32) NOT NULL, findings JSON NOT NULL, '
            'created_at DATETIME NOT NULL, user_id VARCHAR(128))'
        ))
        connection.execute(text(
            "INSERT INTO video_reviews "
            "(id, original_filename, duration_seconds, frame_count, analysis_mode, findings, created_at, user_id) "
            "VALUES (1, 'legacy.mp4', 9.0, 1, 'gemini_assisted', '[]', '2026-10-01 00:00:00', 'owner-a')"
        ))

    monkeypatch.setattr(backend_database, 'engine', engine)
    backend_database.init_db()

    columns = {column['name'] for column in inspect(engine).get_columns('video_reviews')}
    assert {'risk_score', 'risk_category', 'compliance_score', 'model_used', 'fallback_used'} <= columns
    with engine.connect() as connection:
        row = connection.execute(text(
            'SELECT original_filename, risk_score, risk_category, compliance_score, model_used, fallback_used '
            'FROM video_reviews WHERE id = 1'
        )).one()
    assert row == ('legacy.mp4', 0, 'low', 100, None, 0)
    engine.dispose()