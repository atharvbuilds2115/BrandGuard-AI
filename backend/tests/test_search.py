from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import require_firebase_user
from backend.database import Base, get_db
from backend.models import Asset, Audit, BrandGuideline
from backend.routers.search import router as search_router


@pytest.fixture
def api() -> Iterator[tuple[TestClient, dict[str, str], sessionmaker]]:
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {'uid': 'search-user-a'}
    app = FastAPI()
    app.include_router(search_router)

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
        yield client, identity, test_session
    finally:
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_search_records(test_session: sessionmaker, user_id: str = 'search-user-a') -> None:
    db = test_session()
    db.add_all([
        Audit(
            campaign_name='Spring Launch',
            campaign_type='Email',
            submitted_content='A seasonal product announcement',
            risk_score=15,
            risk_category='low',
            audit_status='completed',
            analysis_mode='rules_only',
            created_at=datetime(2026, 1, 1),
            user_id=user_id,
        ),
        Asset(
            original_filename='spring-banner.png',
            stored_filename='stored-spring-banner.png',
            mime_type='image/png',
            file_size=1024,
            campaign_name='Spring Launch',
            tags='["Seasonal","Hero"]',
            file_path='assets/stored-spring-banner.png',
            uploaded_at=datetime(2026, 1, 2),
            user_id=user_id,
        ),
        BrandGuideline(
            rule_name='Seasonal imagery',
            category='Visual Identity',
            description='Use warm colors for spring promotions.',
            rule_value='Spring palette',
            severity='medium',
            active=True,
            user_id=user_id,
        ),
    ])
    db.commit()
    db.close()


def test_search_returns_partial_case_insensitive_matches_in_all_categories(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, _identity, test_session = api
    _seed_search_records(test_session)

    response = client.get('/api/search', params={'q': 'sPrInG'})

    assert response.status_code == 200
    results = response.json()
    assert {result['category'] for result in results} == {'Campaign', 'Asset', 'Guideline'}
    assert next(item for item in results if item['category'] == 'Campaign')['name'] == 'Spring Launch'
    assert next(item for item in results if item['category'] == 'Asset')['name'] == 'spring-banner.png'
    assert next(item for item in results if item['category'] == 'Guideline')['name'] == 'Seasonal imagery'


@pytest.mark.parametrize('query', ['', '   '])
def test_search_returns_no_results_for_empty_or_whitespace_query(
    api: tuple[TestClient, dict[str, str], sessionmaker],
    query: str,
) -> None:
    client, _identity, test_session = api
    _seed_search_records(test_session)

    response = client.get('/api/search', params={'q': query})

    assert response.status_code == 200
    assert response.json() == []


def test_search_returns_no_results_for_unmatched_or_wildcard_query(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, _identity, test_session = api
    _seed_search_records(test_session)

    assert client.get('/api/search', params={'q': 'not-present'}).json() == []
    assert client.get('/api/search', params={'q': '%'}).json() == []


def test_search_isolates_results_to_verified_firebase_uid(
    api: tuple[TestClient, dict[str, str], sessionmaker],
) -> None:
    client, identity, test_session = api
    _seed_search_records(test_session, 'search-user-a')
    _seed_search_records(test_session, 'search-user-b')

    response = client.get('/api/search', params={'q': 'spring'})
    assert response.status_code == 200
    assert len(response.json()) == 3

    identity['uid'] = 'search-user-b'
    response = client.get('/api/search', params={'q': 'spring'})
    assert response.status_code == 200
    assert len(response.json()) == 3
