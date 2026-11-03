from __future__ import annotations

import base64
import json
from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError, APITimeoutError

from backend.models import BrandGuideline
from backend.services import ai_service, gemini_service, groq_service
from backend.services.ai_provider import (
    AIAnalysisError,
    ai_provider_is_configured,
    get_active_ai_provider,
    sanitize_provider_error,
)


@pytest.fixture(autouse=True)
def isolate_provider_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gemini_service, '_BACKEND_ENV_FILE', tmp_path / '.env')
    for name in (
        'AI_PROVIDER',
        'GEMINI_API_KEY',
        'GROQ_API_KEY',
        'GEMINI_MODEL',
        'GEMINI_PRIMARY_MODEL',
        'GEMINI_FALLBACK_MODEL',
        'GROQ_TEXT_MODEL',
        'GROQ_VISION_MODEL',
    ):
        monkeypatch.delenv(name, raising=False)


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def _mock_groq(
    monkeypatch: pytest.MonkeyPatch,
    respond: Callable[[dict, int], object],
) -> list[dict]:
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs['max_retries'] == 0
            assert kwargs['api_key'] == 'test-groq-key'
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def create(self, **kwargs: dict) -> object:
            requests.append(kwargs)
            result = respond(kwargs, len(requests))
            if isinstance(result, BaseException):
                raise result
            return result

    monkeypatch.setattr(groq_service, 'Groq', FakeClient)
    monkeypatch.setenv('AI_PROVIDER', 'groq')
    monkeypatch.setenv('GROQ_API_KEY', 'test-groq-key')
    return requests


def _api_status_error(status_code: int, message: str, retry_after: str = '0') -> APIStatusError:
    request = httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions')
    response = httpx.Response(
        status_code,
        headers={'Retry-After': retry_after},
        json={'error': {'message': message, 'type': 'rate_limit_error'}},
        request=request,
    )
    return APIStatusError(
        f'HTTP {status_code}',
        response=response,
        body=response.json(),
    )


def _fake_frames(count: int) -> list[dict[str, object]]:
    image = base64.b64encode(b'jpeg fixture bytes').decode('ascii')
    return [
        {
            'timestamp_seconds': float(index * 5),
            'image_base64': image,
            'mime_type': 'image/jpeg',
        }
        for index in range(count)
    ]


def test_provider_defaults_to_gemini_and_accepts_explicit_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_active_ai_provider() == 'gemini'

    monkeypatch.setenv('AI_PROVIDER', 'groq')
    assert get_active_ai_provider() == 'groq'


def test_invalid_provider_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AI_PROVIDER', 'other')
    with pytest.raises(AIAnalysisError, match="AI_PROVIDER must be either 'gemini' or 'groq'"):
        get_active_ai_provider()


@pytest.mark.parametrize(
    ('provider', 'key_name'),
    [('groq', 'GROQ_API_KEY'), ('gemini', 'GEMINI_API_KEY')],
)
def test_selected_provider_requires_its_own_api_key(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    key_name: str,
) -> None:
    monkeypatch.setenv('AI_PROVIDER', provider)
    with pytest.raises(AIAnalysisError, match=key_name):
        ai_provider_is_configured()


def test_unconfigured_default_gemini_preserves_rules_only_mode() -> None:
    assert ai_provider_is_configured() is False


def test_provider_error_sanitization_removes_keys_tokens_and_private_key_material() -> None:
    api_key = 'private-provider-key'
    jwt_token = ('e' + 'y' + 'J') + 'syntheticHeader' + '.' + 'syntheticPayload' + '.signature'
    groq_key = 'gsk' + '_' + 'SYNTHETIC_TEST_ONLY_000000000000'
    pem_header = '-----BEGIN ' + 'PRIVATE KEY-----'
    pem_footer = '-----END ' + 'PRIVATE KEY-----'
    pem_material = 'SYNTHETIC TEST-ONLY KEY MATERIAL'
    provider_error = (
        f'key={api_key}; Authorization: Bearer eyJhbGci.eyJzdWI.signature; '
        f'{jwt_token}; {groq_key}; '
        'api_key: other-provider-secret; '
        f'{pem_header}{pem_material}{pem_footer}'
    )

    sanitized = sanitize_provider_error(provider_error, api_key)

    for secret in (
        api_key,
        'other-provider-secret',
        jwt_token,
        groq_key,
        pem_material,
    ):
        assert secret not in sanitized
    assert 'Bearer [redacted]' in sanitized


def test_gemini_selection_uses_existing_gemini_analyzer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')
    monkeypatch.setattr(
        ai_service,
        'analyze_with_gemini',
        lambda content, _guidelines: [{'evidence': content}],
    )

    assert ai_service.analyze_campaign_text('campaign text', []) == [{'evidence': 'campaign text'}]


def test_groq_text_analysis_uses_json_mode_and_validates_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guideline = BrandGuideline(
        id=7,
        rule_name='Approved product name',
        category='approved_terminology',
        rule_value='BrandGuard',
        severity='medium',
        active=True,
    )
    generated = {
        'findings': [{
            'title': 'Product name is missing',
            'severity': 'medium',
            'evidence': 'Campaign copy without the product name.',
            'explanation': 'The exact submitted copy omits the required product name.',
            'guideline_id': 7,
            'suggested_correction': 'Add BrandGuard to the campaign copy.',
        }],
    }
    requests = _mock_groq(
        monkeypatch,
        lambda _request, _count: _completion(json.dumps(generated)),
    )
    content = 'Campaign copy without the product name.'

    findings = ai_service.analyze_campaign_text(content, [guideline])

    assert findings[0]['evidence'] == content
    assert findings[0]['guideline_id'] == 7
    assert findings[0]['status'] == 'needs_verification'
    assert requests[0]['model'] == 'qwen/qwen3.8-27b'
    assert requests[0]['response_format'] == {'type': 'json_object'}
    assert requests[0]['messages'][0]['role'] == 'system'
    assert requests[0]['messages'][1]['role'] == 'user'


def test_groq_image_analysis_uses_data_url_and_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _mock_groq(monkeypatch, lambda _request, _count: _completion('{"findings":[]}'))
    findings, model, fallback_used = ai_service.analyze_video_frames_with_model(_fake_frames(1), [])

    content = requests[0]['messages'][1]['content']
    assert findings == []
    assert model == 'qwen/qwen3.8-27b'
    assert fallback_used is False
    assert requests[0]['response_format'] == {'type': 'json_object'}
    assert content[1]['type'] == 'text'
    assert content[2]['type'] == 'image_url'
    assert content[2]['image_url']['url'].startswith('data:image/jpeg;base64,')


def test_groq_video_analysis_batches_twelve_frames_in_groups_of_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _mock_groq(monkeypatch, lambda _request, _count: _completion('{"findings":[]}'))

    findings, model, _fallback_used = ai_service.analyze_video_frames_with_model(_fake_frames(12), [])

    image_counts = [
        sum(part['type'] == 'image_url' for part in request['messages'][1]['content'])
        for request in requests
    ]
    assert findings == []
    assert model == 'qwen/qwen3.8-27b'
    assert image_counts == [3, 3, 3, 3]
    assert all(count <= 3 for count in image_counts)


def test_groq_malformed_json_is_rejected_without_fabricated_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_groq(monkeypatch, lambda _request, _count: _completion('not json'))

    with pytest.raises(AIAnalysisError, match='malformed or empty JSON'):
        ai_service.analyze_campaign_text('Submitted copy.', [])


@pytest.mark.parametrize(('status_code', 'message'), [(429, 'Please retry shortly.'), (503, 'Service overloaded.')])
def test_groq_retries_temporary_rate_limit_and_overload(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    message: str,
) -> None:
    sleeps: list[float] = []
    requests = _mock_groq(
        monkeypatch,
        lambda _request, count: (
            _api_status_error(status_code, message)
            if count == 1
            else _completion('{"findings":[]}')
        ),
    )
    monkeypatch.setattr(groq_service.time, 'sleep', sleeps.append)
    monkeypatch.setattr(groq_service.random, 'uniform', lambda lower, _upper: lower)

    assert ai_service.analyze_campaign_text('Submitted copy.', []) == []
    assert len(requests) == 2
    assert sleeps == [0.0]


@pytest.mark.parametrize(
    ('status_code', 'message', 'expected_detail'),
    [
        (401, 'Invalid API key.', 'rejected the configured API key'),
        (403, 'Model access denied.', 'does not have permission'),
        (404, 'Model not found.', 'could not find model'),
        (400, 'Invalid request.', 'rejected the analysis request'),
    ],
)
def test_groq_permanent_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    message: str,
    expected_detail: str,
) -> None:
    requests = _mock_groq(
        monkeypatch,
        lambda _request, _count: _api_status_error(status_code, message),
    )

    with pytest.raises(AIAnalysisError, match=expected_detail):
        ai_service.analyze_campaign_text('Submitted copy.', [])

    assert len(requests) == 1


def test_groq_daily_quota_exhaustion_is_not_retried_or_fallbacked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _mock_groq(
        monkeypatch,
        lambda _request, _count: _api_status_error(
            429,
            'Daily request quota exceeded for requests per day (RPD).',
        ),
    )
    monkeypatch.setattr(
        groq_service.time,
        'sleep',
        lambda _seconds: pytest.fail('A daily quota error must not be retried.'),
    )

    with pytest.raises(AIAnalysisError, match='daily request quota has been exhausted') as error:
        ai_service.analyze_video_frames_with_model(_fake_frames(4), [])

    assert error.value.http_status_code == 429
    assert len(requests) == 1


def test_groq_timeout_retries_with_sdk_retries_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _mock_groq(
        monkeypatch,
        lambda _request, count: (
            APITimeoutError(request=httpx.Request('POST', 'https://api.groq.com'))
            if count == 1
            else _completion('{"findings":[]}')
        ),
    )
    sleeps: list[float] = []
    monkeypatch.setattr(groq_service.time, 'sleep', sleeps.append)
    monkeypatch.setattr(groq_service.random, 'uniform', lambda lower, _upper: lower)

    assert ai_service.analyze_campaign_text('Submitted copy.', []) == []
    assert len(requests) == 2
    assert sleeps == [0.0]
