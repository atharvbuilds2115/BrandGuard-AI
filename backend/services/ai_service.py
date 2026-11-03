from __future__ import annotations

from typing import Any

from ..models import BrandGuideline
from .ai_provider import (
    AIProviderName,
    ai_provider_is_configured,
    get_active_ai_provider,
    require_ai_provider_api_key,
)
from .gemini_service import analyze_video_frames_with_model as analyze_with_gemini_model
from .gemini_service import analyze_with_gemini
from .guideline_import_service import (
    ExtractedDocument,
    build_guideline_extraction_prompt,
    validate_extracted_guideline_rules,
)


def analyze_campaign_text(
    submitted_content: str,
    guidelines: list[BrandGuideline],
) -> list[dict[str, Any]]:
    provider = get_active_ai_provider()
    require_ai_provider_api_key(provider)
    if provider == 'gemini':
        return analyze_with_gemini(submitted_content, guidelines)

    from .groq_service import analyze_campaign_text as analyze_with_groq

    return analyze_with_groq(submitted_content, guidelines)


def analyze_video_frames_with_model(
    frames: list[dict[str, Any]],
    guidelines: list[BrandGuideline],
) -> tuple[list[dict[str, Any]], str, bool]:
    provider = get_active_ai_provider()
    require_ai_provider_api_key(provider)
    if provider == 'gemini':
        return analyze_with_gemini_model(frames, guidelines)

    from .groq_service import analyze_video_frames

    findings, model = analyze_video_frames(frames, guidelines)
    return findings, model, False


def extract_company_guidelines(
    document: ExtractedDocument,
    existing_guidelines: list[BrandGuideline],
) -> tuple[list[dict[str, Any]], str, str]:
    provider = get_active_ai_provider()
    require_ai_provider_api_key(provider)
    system_prompt, source_text = build_guideline_extraction_prompt(document.text)
    if provider == 'gemini':
        from .gemini_service import extract_guideline_rules_with_gemini

        payload, model = extract_guideline_rules_with_gemini(system_prompt, source_text)
    else:
        from .groq_service import extract_guideline_rules_with_groq

        payload, model = extract_guideline_rules_with_groq(system_prompt, source_text)

    rules = validate_extracted_guideline_rules(payload, document, existing_guidelines)
    return rules, provider, model


def selected_provider_analysis_mode(provider: AIProviderName | None = None) -> str:
    return f'{provider or get_active_ai_provider()}_assisted'


__all__ = [
    'ai_provider_is_configured',
    'analyze_campaign_text',
    'analyze_video_frames_with_model',
    'get_active_ai_provider',
    'selected_provider_analysis_mode',
]
