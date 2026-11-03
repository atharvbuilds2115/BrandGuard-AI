from __future__ import annotations

import re
from typing import Literal


class AIAnalysisError(RuntimeError):
    def __init__(self, message: str, http_status_code: int = 503) -> None:
        super().__init__(message)
        self.http_status_code = http_status_code


GeminiAnalysisError = AIAnalysisError
AIProviderName = Literal['gemini', 'groq']


def sanitize_provider_error(message: str, api_key: str = '') -> str:
    if api_key:
        message = message.replace(api_key, '[redacted]')
    message = re.sub(r'AIza[0-9A-Za-z_-]{20,}', '[redacted]', message)
    message = re.sub(r'gsk_[0-9A-Za-z_-]{20,}', '[redacted]', message)
    message = re.sub(r'\bsk-[0-9A-Za-z_-]{20,}\b', '[redacted]', message)
    message = re.sub(r'\bBearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [redacted]', message, flags=re.IGNORECASE)
    message = re.sub(
        r'\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b',
        '[redacted]',
        message,
    )
    message = re.sub(
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
        '[redacted private key]',
        message,
        flags=re.DOTALL,
    )
    message = re.sub(
        r'(?i)("private_key(?:_id)?"\s*:\s*")[^"]*(")',
        r'\1[redacted]\2',
        message,
    )
    message = re.sub(
        r'(?i)("?(?:api[_ -]?key|x-goog-api-key)"?\s*:\s*")[^"]*(")',
        r'\1[redacted]\2',
        message,
    )
    message = re.sub(
        r'(?i)\b(?:api[_ -]?key|x-goog-api-key)\s*[:=]\s*["\']?[^\s,;}"\']+',
        '[redacted]',
        message,
    )
    message = re.sub(r'[\x00-\x1f\x7f]+', ' ', message).strip()
    return message


def _configured_value(name: str, default: str = '') -> str:
    from .gemini_service import _configured_value as get_gemini_configured_value

    return get_gemini_configured_value(name, default)


def get_active_ai_provider() -> AIProviderName:
    provider = _configured_value('AI_PROVIDER', 'gemini').casefold()
    if provider == 'gemini':
        return 'gemini'
    if provider == 'groq':
        return 'groq'
    raise AIAnalysisError("AI_PROVIDER must be either 'gemini' or 'groq'. No AI analysis was run.")


def get_ai_provider_api_key(provider: AIProviderName | None = None) -> str:
    selected_provider = provider or get_active_ai_provider()
    key_name = 'GROQ_API_KEY' if selected_provider == 'groq' else 'GEMINI_API_KEY'
    return _configured_value(key_name)


def ai_provider_is_configured() -> bool:
    provider = get_active_ai_provider()
    if get_ai_provider_api_key(provider):
        return True

    if _configured_value('AI_PROVIDER'):
        key_name = 'GROQ_API_KEY' if provider == 'groq' else 'GEMINI_API_KEY'
        raise AIAnalysisError(
            f'{key_name} is not configured for the selected {provider} provider. '
            'Set it in backend/.env or the backend process environment; no AI analysis was run.'
        )
    return False


def require_ai_provider_api_key(provider: AIProviderName | None = None) -> str:
    selected_provider = provider or get_active_ai_provider()
    api_key = get_ai_provider_api_key(selected_provider)
    if not api_key:
        key_name = 'GROQ_API_KEY' if selected_provider == 'groq' else 'GEMINI_API_KEY'
        raise AIAnalysisError(
            f'{key_name} is not configured. Set it in backend/.env or the backend process environment; '
            'no AI analysis was run.'
        )
    return api_key
