from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from groq import APIConnectionError, APIStatusError, APITimeoutError, Groq

from ..models import BrandGuideline
from .ai_provider import AIAnalysisError, require_ai_provider_api_key, sanitize_provider_error
from .gemini_service import (
    _build_audit_prompt,
    _validate_findings,
    _validate_video_findings,
    _video_request_payload,
)


_LOGGER = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_FALLBACK_TEXT_MODEL = 'qwen/qwen3.8-27b'
_FALLBACK_VISION_MODEL = 'qwen/qwen3.8-27b'
_MAX_IMAGES_PER_REQUEST = 3
_MAX_IMAGE_REQUEST_BYTES = 20 * 1024 * 1024


def _configured_model(config_name: str, default: str) -> str:
    from .gemini_service import _configured_value

    model = _configured_value(config_name, default)
    if not re.fullmatch(r'[A-Za-z0-9._/-]+', model):
        raise AIAnalysisError(f'{config_name} contains unsupported characters.')
    return model


def _error_message(error: APIStatusError, api_key: str) -> str:
    body = getattr(error, 'body', None)
    if isinstance(body, dict):
        provider_error = body.get('error', body)
        if isinstance(provider_error, dict):
            message = provider_error.get('message') or provider_error.get('error')
            code = provider_error.get('code') or provider_error.get('type')
            parts = [str(value) for value in (code, message) if value]
            text = ': '.join(parts) if parts else str(provider_error)
        else:
            text = str(provider_error)
    else:
        text = str(error)
    text = sanitize_provider_error(text, api_key)
    return text[:500] or 'The provider returned no structured error details.'


def _is_daily_quota_exhausted(status_code: int, provider_error: str) -> bool:
    if status_code != 429:
        return False
    normalized = provider_error.casefold()
    return (
        'daily' in normalized and any(token in normalized for token in ('quota', 'limit', 'request'))
    ) or bool(re.search(r'\brequests?\s+per\s+day\b|\brpd\b', normalized))


def _retry_delay(error: APIStatusError, attempt: int) -> float:
    retry_after = error.response.headers.get('Retry-After')
    if retry_after:
        try:
            delay = max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                delay = -1.0
        if delay >= 0:
            return delay + random.uniform(0.0, min(1.0, delay * 0.1))
    return random.uniform(0.0, min(8.0, 2**attempt))


def _request_json(
    model: str,
    messages: list[dict[str, Any]],
    api_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        client = Groq(
            api_key=api_key,
            max_retries=0,
            timeout=timeout_seconds,
        )
    except TypeError as error:
        raise AIAnalysisError('The Groq client could not be configured.') from error

    with client:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={'type': 'json_object'},
                    temperature=0.1,
                    max_completion_tokens=4096,
                )
                try:
                    content = completion.choices[0].message.content
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError('The response did not contain text.')
                    payload = json.loads(content)
                except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise AIAnalysisError(
                        'Groq returned malformed or empty JSON; no AI result was saved.',
                        http_status_code=502,
                    ) from error
                _LOGGER.info('Groq analysis succeeded model=%s attempt=%d', model, attempt + 1)
                return payload
            except APIStatusError as error:
                status_code = error.status_code
                provider_error = _error_message(error, api_key)
                if _is_daily_quota_exhausted(status_code, provider_error):
                    _LOGGER.warning(
                        'Groq daily request quota exhausted model=%s status=%d attempt=%d provider_error=%s',
                        model,
                        status_code,
                        attempt + 1,
                        provider_error,
                    )
                    raise AIAnalysisError(
                        'Groq daily request quota has been exhausted for this project. Wait until the provider '
                        'quota resets, then retry; no AI result was saved.',
                        http_status_code=429,
                    ) from error

                if status_code in _RETRYABLE_STATUS_CODES and attempt + 1 < _MAX_ATTEMPTS:
                    delay = _retry_delay(error, attempt)
                    _LOGGER.warning(
                        'Groq temporary provider failure model=%s status=%d attempt=%d/%d '
                        'retry_delay_seconds=%.2f provider_error=%s',
                        model,
                        status_code,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                        delay,
                        provider_error,
                    )
                    time.sleep(delay)
                    continue

                _LOGGER.error(
                    'Groq request failed model=%s status=%d attempt=%d/%d provider_error=%s',
                    model,
                    status_code,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    provider_error,
                )
                if status_code == 401:
                    message = 'Groq rejected the configured API key. Verify GROQ_API_KEY.'
                    result_status = 502
                elif status_code == 403:
                    message = 'The Groq account does not have permission to use this model.'
                    result_status = 502
                elif status_code == 404:
                    message = f'Groq could not find model {model}. Verify GROQ_TEXT_MODEL or GROQ_VISION_MODEL.'
                    result_status = 502
                elif status_code == 429:
                    message = f'Groq rate limits persisted after three attempts. Provider: {provider_error}.'
                    result_status = 429
                elif status_code in {400, 422}:
                    message = f'Groq rejected the analysis request (HTTP {status_code}). Provider: {provider_error}.'
                    result_status = 502
                elif status_code in _RETRYABLE_STATUS_CODES:
                    message = f'Groq remained unavailable after three attempts (HTTP {status_code}).'
                    result_status = 503 if status_code != 408 else 504
                else:
                    message = f'Groq analysis failed with HTTP {status_code}. Provider: {provider_error}.'
                    result_status = 502
                raise AIAnalysisError(f'{message} No AI result was saved.', result_status) from error
            except (APITimeoutError, APIConnectionError) as error:
                if attempt + 1 == _MAX_ATTEMPTS:
                    _LOGGER.error(
                        'Groq network request exhausted retries model=%s attempt=%d/%d error_type=%s',
                        model,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                        type(error).__name__,
                    )
                    raise AIAnalysisError(
                        'Groq could not complete the request after three network attempts. '
                        'Check backend connectivity; no AI result was saved.',
                        http_status_code=504 if isinstance(error, APITimeoutError) else 502,
                    ) from error
                delay = random.uniform(0.0, min(8.0, 2**attempt))
                _LOGGER.warning(
                    'Groq network request retry model=%s attempt=%d/%d retry_delay_seconds=%.2f error_type=%s',
                    model,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    delay,
                    type(error).__name__,
                )
                time.sleep(delay)

    raise AIAnalysisError('Groq analysis could not be completed; no AI result was saved.', http_status_code=502)


def analyze_campaign_text(
    submitted_content: str,
    guidelines: list[BrandGuideline],
) -> list[dict[str, Any]]:
    api_key = require_ai_provider_api_key('groq')
    model = _configured_model('GROQ_TEXT_MODEL', _FALLBACK_TEXT_MODEL)
    system_prompt, user_content = _build_audit_prompt(submitted_content, guidelines)
    generated_payload = _request_json(
        model,
        [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content},
        ],
        api_key,
        timeout_seconds=45.0,
    )
    return _validate_findings(generated_payload, submitted_content, guidelines)


def extract_guideline_rules_with_groq(system_prompt: str, source_text: str) -> tuple[dict[str, Any], str]:
    api_key = require_ai_provider_api_key('groq')
    model = _configured_model('GROQ_TEXT_MODEL', _FALLBACK_TEXT_MODEL)
    generated_payload = _request_json(
        model,
        [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': source_text},
        ],
        api_key,
        timeout_seconds=60.0,
    )
    return generated_payload, model


def analyze_video_frames(
    frames: list[dict[str, Any]],
    guidelines: list[BrandGuideline],
) -> tuple[list[dict[str, Any]], str]:
    if not frames:
        raise AIAnalysisError('No video frames were available for analysis.')

    api_key = require_ai_provider_api_key('groq')
    model = _configured_model('GROQ_VISION_MODEL', _FALLBACK_VISION_MODEL)
    findings: list[dict[str, Any]] = []

    for offset in range(0, len(frames), _MAX_IMAGES_PER_REQUEST):
        batch = frames[offset:offset + _MAX_IMAGES_PER_REQUEST]
        batch_bytes = 0
        for frame in batch:
            if frame.get('mime_type') != 'image/jpeg':
                raise AIAnalysisError('Groq video analysis requires locally encoded JPEG frames.')
            image_data = frame.get('image_base64')
            if not isinstance(image_data, str) or not image_data:
                raise AIAnalysisError('A sampled frame is missing its encoded image data.')
            batch_bytes += len(image_data) * 3 // 4
        if batch_bytes > _MAX_IMAGE_REQUEST_BYTES:
            raise AIAnalysisError(
                'A Groq video frame batch exceeds the provider 20 MB image request limit; no review was saved.',
                http_status_code=413,
            )

        payload = _video_request_payload(batch, guidelines)
        user_parts = payload['contents'][0]['parts']
        message_content: list[dict[str, Any]] = [{'type': 'text', 'text': user_parts[0]['text']}]
        for frame in batch:
            message_content.extend([
                {'type': 'text', 'text': f"Frame at {frame['timestamp_seconds']:.2f} seconds."},
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f"data:image/jpeg;base64,{frame['image_base64']}",
                    },
                },
            ])

        generated_payload = _request_json(
            model,
            [
                {'role': 'system', 'content': payload['systemInstruction']['parts'][0]['text']},
                {'role': 'user', 'content': message_content},
            ],
            api_key,
            timeout_seconds=120.0,
        )
        findings.extend(_validate_video_findings(generated_payload, batch))

    return _validate_video_findings({'findings': findings}, frames), model
