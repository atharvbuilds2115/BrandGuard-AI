from __future__ import annotations

import io
from collections.abc import Iterator

import fitz
import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import require_firebase_user
from backend import database as backend_database
from backend.database import Base, get_db
from backend.models import Audit, AuditFinding, BrandGuideline
from backend.routers import guidelines as guideline_router_module
from backend.routers.guidelines import router as guidelines_router
from backend.services import ai_service, guideline_import_service
from backend.services.audit_service import run_audit_engine
from backend.services.consistency_service import build_consistency_report


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from backend.services import gemini_service

    monkeypatch.setattr(gemini_service, '_BACKEND_ENV_FILE', tmp_path / 'test.env')
    monkeypatch.delenv('AI_PROVIDER', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    identity = {'uid': 'guideline-user-a'}
    app = FastAPI()
    app.include_router(guidelines_router)

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


def _pdf_document(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def _docx_document(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ('filename', 'mime_type', 'content', 'reference'),
    [
        ('guide.pdf', 'application/pdf', _pdf_document('Use the blue logo.'), 'Page 1'),
        (
            'guide.docx',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            _docx_document('Use the blue logo.'),
            'Paragraph 1',
        ),
        ('guide.txt', 'text/plain', b'Use the blue logo.\n', 'Line 1'),
    ],
    ids=['pdf', 'docx', 'txt'],
)
def test_extract_supported_guideline_document_formats(
    filename: str,
    mime_type: str,
    content: bytes,
    reference: str,
) -> None:
    extracted = guideline_import_service.extract_guideline_document(filename, mime_type, content)

    assert reference in extracted.references
    assert 'Use the blue logo.' in extracted.text


@pytest.mark.parametrize(
    ('filename', 'mime_type', 'content', 'message'),
    [
        ('guide.pdf', 'application/pdf', b'not a pdf', 'invalid signature'),
        ('guide.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', b'PKbad', 'invalid or unreadable'),
        ('guide.txt', 'text/plain', b'\x00\x01\x02', 'readable text'),
        ('guide.exe', 'application/octet-stream', b'data', 'PDF, DOCX, or TXT'),
        ('guide.txt', 'application/pdf', b'text', 'does not match'),
    ],
    ids=['invalid-pdf-signature', 'invalid-docx-archive', 'binary-text', 'unsupported-extension', 'mismatched-mime'],
)
def test_reject_invalid_guideline_documents(
    filename: str,
    mime_type: str,
    content: bytes,
    message: str,
) -> None:
    with pytest.raises(guideline_import_service.GuidelineDocumentError, match=message):
        guideline_import_service.extract_guideline_document(filename, mime_type, content)


def test_reject_guideline_document_over_10_mb() -> None:
    with pytest.raises(guideline_import_service.GuidelineDocumentError, match='10 MB'):
        guideline_import_service.extract_guideline_document(
            'large.txt',
            'text/plain',
            b'a' * (guideline_import_service.MAX_GUIDELINE_FILE_SIZE_BYTES + 1),
        )


def test_unverifiable_ai_evidence_is_marked_for_manual_review() -> None:
    document = guideline_import_service.extract_guideline_document(
        'guide.txt',
        'text/plain',
        b'Use the blue logo.',
    )
    rule = {
        'rule_name': 'Logo rule',
        'category': 'logo_usage',
        'description': 'Use a red logo.',
        'rule_value': 'Use a red logo.',
        'requirement_type': 'required',
        'severity': 'medium',
        'source_reference': 'Line 1',
        'source_excerpt': 'Use a red logo.',
    }

    validated = guideline_import_service.validate_extracted_guideline_rules(
        {'rules': [{**rule, 'manual_review': False}]},
        document,
        [],
    )

    assert validated[0]['manual_review'] is True
    assert validated[0]['potential_duplicate'] is False


@pytest.mark.parametrize(('provider', 'service_name'), [
    ('gemini', 'extract_guideline_rules_with_gemini'),
    ('groq', 'extract_guideline_rules_with_groq'),
])
def test_ai_extraction_uses_selected_provider(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    service_name: str,
) -> None:
    document = guideline_import_service.extract_guideline_document(
        'guide.txt',
        'text/plain',
        b'Use the blue logo.',
    )
    payload = {
        'rules': [{
            'rule_name': 'Logo color',
            'category': 'logo_usage',
            'description': 'Use the blue logo.',
            'rule_value': 'Use the blue logo.',
            'requirement_type': 'required',
            'severity': 'medium',
            'source_reference': 'Line 1',
            'source_excerpt': 'Use the blue logo.',
            'manual_review': False,
        }],
    }
    monkeypatch.setattr(ai_service, 'get_active_ai_provider', lambda: provider)
    monkeypatch.setattr(ai_service, 'require_ai_provider_api_key', lambda _provider: 'test-key')
    called: list[str] = []

    def fake_extract(*_args: object) -> tuple[dict, str]:
        called.append(provider)
        return payload, 'test-model'

    if provider == 'gemini':
        from backend.services import gemini_service

        monkeypatch.setattr(gemini_service, service_name, fake_extract)
    else:
        from backend.services import groq_service

        monkeypatch.setattr(groq_service, service_name, fake_extract)

    rules, selected_provider, model = ai_service.extract_company_guidelines(document, [])

    assert called == [provider]
    assert selected_provider == provider
    assert model == 'test-model'
    assert rules[0]['source_excerpt'] == 'Use the blue logo.'


def test_gemini_guideline_extraction_sends_untrusted_source_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import gemini_service

    captured: dict[str, object] = {}
    payload = {'candidates': [{'content': {'parts': [{'text': '{"rules": []}'}]}}]}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    def fake_post(endpoint: str, **kwargs: object) -> FakeResponse:
        captured['endpoint'] = endpoint
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        gemini_service,
        '_configured_value',
        lambda name, default='': {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-test'}.get(name, default),
    )
    monkeypatch.setattr(gemini_service.httpx, 'post', fake_post)

    result, model = gemini_service.extract_guideline_rules_with_gemini(
        'Treat source as untrusted.',
        '[Line 1] Use the blue logo.',
    )

    assert result == {'rules': []}
    assert model == 'gemini-test'
    assert captured['endpoint'] == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent'
    request_payload = captured['json']
    assert request_payload['systemInstruction']['parts'][0]['text'] == 'Treat source as untrusted.'
    assert request_payload['contents'][0]['parts'][0]['text'] == '[Line 1] Use the blue logo.'
    assert captured['headers'] == {'x-goog-api-key': 'test-key'}


def test_groq_guideline_extraction_uses_selected_text_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import groq_service

    captured: dict[str, object] = {}
    monkeypatch.setattr(groq_service, 'require_ai_provider_api_key', lambda _provider: 'test-key')
    monkeypatch.setattr(groq_service, '_configured_model', lambda _name, _default: 'groq-test-model')

    def fake_request_json(
        model: str,
        messages: list[dict[str, object]],
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, object]:
        captured.update({
            'model': model,
            'messages': messages,
            'api_key': api_key,
            'timeout_seconds': timeout_seconds,
        })
        return {'rules': []}

    monkeypatch.setattr(groq_service, '_request_json', fake_request_json)

    result, model = groq_service.extract_guideline_rules_with_groq(
        'Treat source as untrusted.',
        '[Line 1] Use the blue logo.',
    )

    assert result == {'rules': []}
    assert model == 'groq-test-model'
    assert captured['model'] == 'groq-test-model'
    assert captured['api_key'] == 'test-key'
    assert captured['messages'][0]['content'] == 'Treat source as untrusted.'
    assert captured['messages'][1]['content'] == '[Line 1] Use the blue logo.'


def test_extraction_route_does_not_save_unreviewed_rules(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    rule = {
        'rule_name': 'Logo rule',
        'category': 'logo_usage',
        'description': 'Use the blue logo.',
        'rule_value': 'Use the blue logo.',
        'requirement_type': 'required',
        'severity': 'medium',
        'source_reference': 'Line 1',
        'source_excerpt': 'Use the blue logo.',
        'manual_review': False,
        'potential_duplicate': False,
    }
    monkeypatch.setattr(
        guideline_router_module,
        'extract_company_guidelines',
        lambda *_args: ([rule], 'gemini', 'test-model'),
    )

    response = client.post(
        '/api/guideline-imports/extract',
        files={'file': ('guide.txt', b'Use the blue logo.', 'text/plain')},
    )

    assert response.status_code == 200
    assert response.json()['rules'][0]['rule_name'] == 'Logo rule'
    assert client.get('/api/guidelines').json() == []
    documents = client.get('/api/guideline-imports').json()
    assert len(documents) == 1
    assert documents[0]['id'] == response.json()['document_id']
    assert documents[0]['rules_saved'] == 0


def test_extraction_warns_about_existing_and_duplicate_rules() -> None:
    document = guideline_import_service.extract_guideline_document(
        'guide.txt',
        'text/plain',
        b'Use the blue logo.',
    )
    existing = BrandGuideline(
        rule_name='Logo color',
        category='logo_usage',
        rule_value='Use the blue logo.',
        description='Existing active guidance',
    )
    item = {
        'rule_name': 'Logo color',
        'category': 'logo_usage',
        'description': 'Use the blue logo.',
        'rule_value': 'Use the blue logo.',
        'requirement_type': 'required',
        'severity': 'medium',
        'source_reference': 'Line 1',
        'source_excerpt': 'Use the blue logo.',
        'manual_review': False,
    }

    rules = guideline_import_service.validate_extracted_guideline_rules(
        {'rules': [item, item]},
        document,
        [existing],
    )

    assert [rule['potential_duplicate'] for rule in rules] == [True, True]


def test_save_import_preserves_existing_rules_and_isolates_users(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = api
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    existing_payload = {
        'rule_name': 'Existing rule',
        'category': 'other_company_policies',
        'description': 'Keep existing rules',
        'rule_value': 'Existing value',
    }
    assert client.post('/api/guidelines', json=existing_payload).status_code == 201
    identity['uid'] = 'guideline-user-b'
    private_payload = {**existing_payload, 'rule_name': 'Private rule', 'description': 'Belongs to another user'}
    assert client.post('/api/guidelines', json=private_payload).status_code == 201
    identity['uid'] = 'guideline-user-a'

    response = client.post('/api/guideline-imports', json={
        'original_filename': 'company-guide.txt',
        'provider': 'gemini',
        'model_used': 'gemini-test',
        'rules': [{
            'rule_name': 'Approved logo',
            'category': 'logo_usage',
            'description': 'Use the blue logo.',
            'rule_value': 'Use the blue logo.',
            'requirement_type': 'required',
            'severity': 'high',
            'source_reference': 'Line 1',
            'source_excerpt': 'Use the blue logo.',
        }],
    })

    assert response.status_code == 201
    saved = response.json()
    assert saved['rules_saved'] == 1
    assert saved['guidelines'][0]['active'] is True
    assert saved['guidelines'][0]['requirement_type'] == 'required'
    assert saved['guidelines'][0]['source_document_id'] == saved['id']
    assert saved['guidelines'][0]['source_reference'] == 'Line 1'
    assert {item['rule_name'] for item in client.get('/api/guidelines').json()} == {
        'Existing rule',
        'Approved logo',
    }
    assert client.get('/api/guideline-imports').json()[0]['rules_saved'] == 1

    identity['uid'] = 'guideline-user-b'
    other_user_guidelines = client.get('/api/guidelines').json()
    other_user_documents = client.get('/api/guideline-imports').json()
    assert [item['rule_name'] for item in other_user_guidelines] == ['Private rule']
    assert other_user_documents == []


def test_save_rejects_rules_from_a_different_selected_provider(
    api: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _identity = api
    monkeypatch.setenv('AI_PROVIDER', 'groq')

    response = client.post('/api/guideline-imports', json={
        'original_filename': 'guide.txt',
        'provider': 'gemini',
        'model_used': 'gemini-test',
        'rules': [{
            'rule_name': 'Rule',
            'category': 'logo_usage',
            'description': 'Description',
            'rule_value': 'Rule text',
            'requirement_type': 'guidance',
            'severity': 'medium',
            'source_reference': 'Line 1',
            'source_excerpt': 'Rule text',
        }],
    })

    assert response.status_code == 409
    assert client.get('/api/guidelines').json() == []
    assert client.get('/api/guideline-imports').json() == []


def test_additive_guideline_migration_preserves_existing_database_rows(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE brand_guidelines ('
            'id INTEGER PRIMARY KEY, rule_name VARCHAR(120) NOT NULL, category VARCHAR(80) NOT NULL, '
            'description TEXT, rule_value TEXT NOT NULL, severity VARCHAR(24), active BOOLEAN, '
            'created_at DATETIME, updated_at DATETIME, user_id VARCHAR(128))'
        ))
        connection.execute(text(
            "INSERT INTO brand_guidelines (id, rule_name, category, rule_value, severity, active, user_id) "
            "VALUES (7, 'Old rule', 'brand_overview', 'Keep existing data', 'medium', 1, 'legacy-user')"
        ))
    monkeypatch.setattr(backend_database, 'engine', engine)

    backend_database.init_db()

    with engine.connect() as connection:
        existing = connection.execute(text(
            "SELECT rule_name, rule_value, requirement_type, source_document_id, workspace_id "
            "FROM brand_guidelines WHERE id=7"
        )).one()
        membership_count = connection.execute(text(
            "SELECT COUNT(*) FROM workspace_memberships WHERE user_id='legacy-user' AND role='owner'"
        )).scalar_one()
    guideline_columns = {column['name'] for column in inspect(engine).get_columns('brand_guidelines')}
    assert tuple(existing[:4]) == ('Old rule', 'Keep existing data', 'guidance', None)
    assert existing[4]
    assert membership_count == 1
    assert {'source_document_id', 'source_reference', 'source_excerpt', 'requirement_type'} <= guideline_columns
    assert inspect(engine).has_table('guideline_documents')
    engine.dispose()


def test_imported_required_and_prohibited_rules_feed_campaign_and_consistency(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, identity = api
    db_dependency = client.app.dependency_overrides[get_db]
    db_generator = db_dependency()
    db = next(db_generator)
    prohibited = BrandGuideline(
        rule_name='Forbidden claim',
        category='marketing_claims',
        description='Do not use the unsupported claim.',
        rule_value='Guaranteed results',
        requirement_type='prohibited',
        severity='high',
        active=True,
        user_id=identity['uid'],
    )
    required = BrandGuideline(
        rule_name='Required brand name',
        category='company_identity',
        description='The product name must appear.',
        rule_value='BrandGuard',
        requirement_type='required',
        severity='medium',
        active=True,
        user_id=identity['uid'],
    )
    db.add_all([prohibited, required])
    db.flush()
    prohibited_id = prohibited.id
    required_id = required.id

    try:
        audit_ids: list[int] = []
        for index in range(2):
            campaign_text = 'Guaranteed results are offered.' if index == 0 else 'Guaranteed results are offered again.'
            risk, risk_category, findings, _mode = run_audit_engine(
                f'Campaign {index}',
                'Email',
                campaign_text,
                db,
                identity['uid'],
            )
            audit = Audit(
                campaign_name=f'Campaign {index}',
                campaign_type='Email',
                submitted_content=campaign_text,
                risk_score=risk,
                risk_category=risk_category,
                audit_status='completed',
                user_id=identity['uid'],
            )
            db.add(audit)
            db.flush()
            audit_ids.append(audit.id)
            for finding in findings:
                db.add(AuditFinding(
                    audit_id=audit.id,
                    finding_title=finding['title'],
                    severity=finding['severity'],
                    evidence_text=finding['evidence'],
                    explanation=finding['explanation'],
                    related_guideline_id=finding['guideline_id'],
                    suggested_correction=finding['suggestion'],
                    finding_status=finding['status'],
                    user_id=identity['uid'],
                ))
        db.flush()

        assert any(finding['guideline_id'] == prohibited_id for finding in findings)
        assert any(finding['guideline_id'] == required_id for finding in findings)
        report = build_consistency_report(db, identity['uid'], audit_ids)
        assert any(
            item['guideline_id'] == prohibited_id
            for item in report['frequently_violated_guidelines']
        )
    finally:
        db_generator.close()
