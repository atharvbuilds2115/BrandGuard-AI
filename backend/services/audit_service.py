from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import ActivityEvent, Approval, Audit, AuditFinding, BrandGuideline
from .ai_provider import ai_provider_is_configured, get_active_ai_provider
from .ai_service import analyze_campaign_text
from .gemini_service import GeminiAnalysisError, analyze_with_gemini


_PRICE_PATTERN = re.compile(r'\$\s?\d+(?:,\d{3})*(?:\.\d+)?|\b\d+(?:\.\d+)?%')
_DATE_PATTERN = re.compile(
    r'\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b|\b[A-Za-z]+\s+\d{1,2},?\s+\d{4}\b'
)
_CLAIM_PATTERNS = (
    re.compile(r'\bguaranteed(?:\s+\w+){0,3}\b', re.IGNORECASE),
    re.compile(r'\b(?:100\s*%\s*)?risk[- ]free\b', re.IGNORECASE),
    re.compile(r'\bbest[- ]in[- ]class\b', re.IGNORECASE),
    re.compile(r'\binstant results\b', re.IGNORECASE),
)


def _category(guideline: BrandGuideline) -> str:
    return re.sub(r'[\s-]+', '_', guideline.category.strip().lower())


def _severity(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in {'low', 'medium', 'high'} else 'medium'


def _excerpt(text: str, start: int, end: int) -> str:
    boundaries = '.!?\n'
    left = max((text.rfind(char, 0, start) for char in boundaries), default=-1) + 1
    right_candidates = [index for char in boundaries if (index := text.find(char, end)) >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    excerpt = text[left:right].strip()
    if len(excerpt) > 320:
        match_start = max(0, start - left - 120)
        excerpt = excerpt[match_start:match_start + 320].strip()
        if match_start:
            excerpt = f'...{excerpt}'
        if left + match_start + 320 < right:
            excerpt = f'{excerpt}...'
    return excerpt


def _find_matches(pattern: re.Pattern[str], text: str) -> list[tuple[str, str]]:
    return [
        (match.group(0), _excerpt(text, match.start(), match.end()))
        for match in pattern.finditer(text)
    ]


def _parse_date(value: str) -> datetime | None:
    for date_format in ('%d %B %Y', '%B %d %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return None


def _price_key(value: str) -> str:
    normalized = value.replace('$', '').replace(',', '').replace(' ', '').casefold()
    if normalized.endswith('%'):
        number = normalized[:-1]
        try:
            return f'{float(number):g}%'
        except ValueError:
            return normalized
    try:
        return f'${float(normalized):g}'
    except ValueError:
        return normalized


def _finding_score(severity: str) -> int:
    return {'low': 10, 'medium': 20, 'high': 35}[severity]


def derive_risk_category(score: int) -> str:
    if score >= 70:
        return 'high'
    if score >= 35:
        return 'medium'
    return 'low'


def run_audit_engine(
    campaign_name: str,
    campaign_type: str,
    submitted_content: str,
    db: Session,
    user_id: str,
    workspace_id: str | None = None,
) -> tuple[int, str, list[dict], str]:
    guideline_query = db.query(BrandGuideline).filter(BrandGuideline.active.is_(True))
    if workspace_id:
        guideline_query = guideline_query.filter(BrandGuideline.workspace_id == workspace_id)
    else:
        guideline_query = guideline_query.filter(BrandGuideline.user_id == user_id)
    guidelines = guideline_query.all()
    findings: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add_finding(
        title: str,
        severity: str,
        evidence: str,
        explanation: str,
        guideline_id: int | None,
        suggestion: str,
        status: str = 'confirmed',
    ) -> None:
        normalized_severity = _severity(severity)
        key = (title.casefold(), evidence.casefold(), str(guideline_id))
        if key in seen:
            return
        findings.append({
            'title': title,
            'severity': normalized_severity,
            'evidence': evidence,
            'explanation': explanation,
            'guideline_id': guideline_id,
            'suggestion': suggestion,
            'status': status,
        })
        seen.add(key)

    prohibited = [
        guideline
        for guideline in guidelines
        if guideline.requirement_type == 'prohibited'
        or 'prohibit' in _category(guideline)
        or 'forbidden' in _category(guideline)
    ]
    for guideline in prohibited:
        term = guideline.rule_value.strip()
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for matched_text, evidence in _find_matches(pattern, submitted_content):
            add_finding(
                f'Prohibited language: {guideline.rule_name}',
                guideline.severity,
                evidence,
                (
                    f'The submitted text contains “{matched_text}”, which matches the prohibited value '
                    f'from the active guideline “{guideline.rule_name}”. '
                    f'{guideline.description or ""}'
                ).strip(),
                guideline.id,
                f'Remove or replace “{matched_text}” with approved language. '
                f'Guideline: {guideline.rule_value}.',
            )

    terminology_guidelines = [
        guideline
        for guideline in guidelines
        if _category(guideline) in {'approved_terminology', 'approved_terms'}
        or guideline.requirement_type == 'required'
    ]
    for guideline in terminology_guidelines:
        name_and_description = f'{guideline.rule_name} {guideline.description or ""}'.casefold()
        requires_term = guideline.requirement_type == 'required' or (
            'product name' in name_and_description
            or 'must include' in name_and_description
            or 'required term' in name_and_description
        )
        approved_term = guideline.rule_value.strip()
        if requires_term and approved_term and not re.search(re.escape(approved_term), submitted_content, re.IGNORECASE):
            add_finding(
                f'Required terminology missing: {guideline.rule_name}',
                guideline.severity,
                f'No exact match for required term “{approved_term}” was found in the submitted text.',
                (
                    f'The active guideline “{guideline.rule_name}” requires the approved term '
                    f'“{approved_term}”, but no case-insensitive exact match was found.'
                ),
                guideline.id,
                f'Include the approved term “{approved_term}” in the campaign content.',
                'needs_verification',
            )

    pricing_guidelines = [
        guideline
        for guideline in guidelines
        if _category(guideline) in {'pricing', 'pricing_and_offers', 'offers', 'pricing_rules'}
    ]
    if pricing_guidelines:
        approved_prices = {
            _price_key(match.group(0))
            for guideline in pricing_guidelines
            for match in _PRICE_PATTERN.finditer(guideline.rule_value)
        }
        for match in _PRICE_PATTERN.finditer(submitted_content):
            price = match.group(0)
            if approved_prices and _price_key(price) not in approved_prices:
                evidence = _excerpt(submitted_content, match.start(), match.end())
                guideline = pricing_guidelines[0]
                add_finding(
                    'Price is not listed in active pricing guidance',
                    guideline.severity,
                    evidence,
                    (
                        f'The submitted text contains “{price}”, which does not match any price or '
                        'percentage found in the active pricing guidelines.'
                    ),
                    guideline.id,
                    'Replace this value with an approved price or promotion, or update the saved guidance first.',
                )

        approved_dates = {
            parsed
            for guideline in pricing_guidelines
            for date_match in _DATE_PATTERN.finditer(guideline.rule_value)
            if (parsed := _parse_date(date_match.group(0))) is not None
        }
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for date_match in _DATE_PATTERN.finditer(submitted_content):
            parsed = _parse_date(date_match.group(0))
            if parsed and parsed < now and (not approved_dates or parsed not in approved_dates):
                evidence = _excerpt(submitted_content, date_match.start(), date_match.end())
                guideline = next(
                    (item for item in pricing_guidelines if any(token in _category(item) for token in ('offer', 'pricing'))),
                    pricing_guidelines[0],
                )
                add_finding(
                    'Campaign contains an expired or unapproved date',
                    guideline.severity,
                    evidence,
                    (
                        f'The date “{date_match.group(0)}” is earlier than the current date and does not '
                        'match an active approved date in the saved pricing guidance.'
                    ),
                    guideline.id,
                    'Remove this date or replace it with a currently approved offer period.',
                )

    claim_guideline = next(
        (guideline for guideline in guidelines if 'approved_claim' in _category(guideline)),
        None,
    )
    for pattern in _CLAIM_PATTERNS:
        for matched_text, evidence in _find_matches(pattern, submitted_content):
            if claim_guideline is not None:
                add_finding(
                    'Promotional claim needs substantiation',
                    claim_guideline.severity,
                    evidence,
                    (
                        f'The phrase “{matched_text}” is a strong performance or certainty claim. '
                        f'It should be checked against the active approved-claims guideline '
                        f'“{claim_guideline.rule_name}” before publication.'
                    ),
                    claim_guideline.id,
                    'Provide substantiation that supports this exact claim, or revise it to a factual, qualified statement.',
                    'needs_verification',
                )

    analysis_mode = 'rules_only'
    if ai_provider_is_configured():
        provider = get_active_ai_provider()
        provider_findings = (
            analyze_with_gemini(submitted_content, guidelines)
            if provider == 'gemini'
            else analyze_campaign_text(submitted_content, guidelines)
        )
        existing = {
            (finding['guideline_id'], finding['evidence'].casefold())
            for finding in findings
        }
        for finding in provider_findings:
            key = (finding['guideline_id'], finding['evidence'].casefold())
            if key not in existing:
                findings.append(finding)
                existing.add(key)
        analysis_mode = f'{provider}_assisted'

    total_score = min(100, sum(_finding_score(finding['severity']) for finding in findings))
    risk_category = derive_risk_category(total_score)
    return total_score, risk_category, findings, analysis_mode


def create_activity_event(db: Session, event_type: str, description: str, related_entity_id: str | None = None) -> None:
    db.add(ActivityEvent(event_type=event_type, description=description, related_entity_id=related_entity_id))
    db.commit()


def create_approval_record(db: Session, audit_id: int, decision: str, reviewer: str, comment: str | None) -> Approval:
    approval = Approval(audit_id=audit_id, decision=decision, reviewer=reviewer, comment=comment)
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval
