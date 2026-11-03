from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.routers.audits import router as audits_router
from backend.routers.consistency import router as consistency_router
from backend.routers.guidelines import router as guidelines_router
from backend.routers.profile import router as profile_router
from backend.routers.video_reviews import router as video_reviews_router
from backend.services.ai_provider import AIAnalysisError, ai_provider_is_configured, get_active_ai_provider


@pytest.fixture
def live_api() -> Iterator[tuple[TestClient, str, Path]]:
    if os.getenv('BRANDGUARD_RUN_LIVE_INTEGRATION_TESTS') != '1':
        pytest.skip('Set BRANDGUARD_RUN_LIVE_INTEGRATION_TESTS=1 to run live provider/Firebase calls.')
    provider = get_active_ai_provider()
    try:
        configured = ai_provider_is_configured()
    except AIAnalysisError:
        configured = False
    if not configured:
        pytest.skip(f'A real {provider.upper()} API key is required for live integration tests.')
    id_token = os.getenv('BRANDGUARD_FIREBASE_ID_TOKEN', '').strip()
    if not id_token:
        pytest.skip('A real Firebase ID token is required in BRANDGUARD_FIREBASE_ID_TOKEN.')
    video_path_value = os.getenv('BRANDGUARD_TEST_MP4', '').strip()
    if not video_path_value:
        pytest.skip('Provide an actual MP4 path in BRANDGUARD_TEST_MP4.')
    video_path = Path(video_path_value).expanduser()
    if not video_path.is_file() or video_path.suffix.casefold() != '.mp4':
        pytest.skip('BRANDGUARD_TEST_MP4 must point to an existing MP4 file.')

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    app = FastAPI()
    for router in (profile_router, guidelines_router, audits_router, video_reviews_router, consistency_router):
        app.include_router(router)

    def override_db() -> Iterator[Session]:
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield client, id_token, video_path
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_live_selected_provider_uses_firebase_mp4_and_sql(live_api) -> None:
    client, id_token, video_path = live_api
    provider = get_active_ai_provider()
    headers = {'Authorization': f'Bearer {id_token}'}
    profile = client.get('/api/profile', headers=headers)
    assert profile.status_code == 200
    user_id = profile.json()['uid']
    assert user_id

    guidelines = client.get('/api/guidelines', headers=headers)
    assert guidelines.status_code == 200
    assert guidelines.json()

    audit_ids: list[int] = []
    for campaign_name in ('Live integration campaign A', 'Live integration campaign B'):
        audit = client.post(
            '/api/audits',
            headers=headers,
            json={
                'campaign_name': campaign_name,
                'campaign_type': 'Advertisement',
                'submitted_content': 'BrandGuard AI promises guaranteed results.',
            },
        )
        assert audit.status_code == 201
        assert audit.json()['analysis_mode'] == f'{provider}_assisted'
        assert audit.json()['audit_status'] == 'completed'
        audit_ids.append(audit.json()['id'])

    audit_history = client.get('/api/audits', headers=headers)
    assert audit_history.status_code == 200
    assert all(audit_id in {audit['id'] for audit in audit_history.json()} for audit_id in audit_ids)

    video = client.post(
        '/api/video-reviews',
        headers=headers,
        files={'file': (video_path.name, video_path.read_bytes(), 'video/mp4')},
    )
    assert video.status_code == 201
    video_data = video.json()
    assert video_data['frame_count'] > 0
    assert video_data['analysis_mode'] == f'{provider}_assisted'
    assert video_data['risk_score'] == min(100, sum(
        {'low': 10, 'medium': 20, 'high': 35}[finding['severity']]
        for finding in video_data['findings']
    ))
    assert client.get('/api/video-reviews', headers=headers).json()[0]['id'] == video_data['id']
    assert client.get(f"/api/video-reviews/{video_data['id']}", headers=headers).status_code == 200

    report = client.post('/api/consistency-reports', headers=headers, json={'audit_ids': audit_ids})
    assert report.status_code == 201
    report_id = report.json()['id']
    assert report.json()['campaign_count'] == 2
    assert client.get('/api/consistency-reports', headers=headers).json()[0]['id'] == report_id
    assert client.get(f'/api/consistency-reports/{report_id}', headers=headers).status_code == 200

    second_token = os.getenv('BRANDGUARD_SECOND_FIREBASE_ID_TOKEN', '').strip()
    if second_token:
        second_headers = {'Authorization': f'Bearer {second_token}'}
        assert client.get('/api/audits', headers=second_headers).json() == []
        assert client.get('/api/video-reviews', headers=second_headers).json() == []
        assert client.get('/api/consistency-reports', headers=second_headers).json() == []
        assert client.get(f'/api/consistency-reports/{report_id}', headers=second_headers).status_code == 404