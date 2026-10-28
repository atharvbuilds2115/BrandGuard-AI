from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from ..models import ActivityEvent, Approval, Audit, AuditFinding, BrandGuideline


def _lower(value: str) -> str:
    return value.lower().strip()


def _extract_prices(text: str) -> list[str]:
    return re.findall(r'\$\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?%', text)


def _extract_dates(text: str) -> list[str]:
    return re.findall(r'\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b', text)


def _score_finding(severity: str) -> int:
    return {'low': 10, 'medium': 20, 'high': 35}.get(severity.lower(), 10)


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
) -> tuple[int, str, list[dict]]:
    guidelines = (
        db.query(BrandGuideline)
        .filter(BrandGuideline.active.is_(True), BrandGuideline.user_id == user_id)
        .all()
    )
    text = submitted_content.lower()
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_finding(title: str, severity: str, evidence: str, explanation: str, guideline_id: int | None, suggestion: str, status: str) -> None:
        key = (title.lower(), evidence.lower())
        if key in seen:
            return
        findings.append({
            'title': title,
            'severity': severity,
            'evidence': evidence,
            'explanation': explanation,
            'guideline_id': guideline_id,
            'suggestion': suggestion,
            'status': status,
        })
        seen.add(key)

    prohibited = [g for g in guidelines if 'prohibited' in g.category.lower()]
    for guideline in prohibited:
        term = guideline.rule_value.lower()
        if term in text:
            add_finding(
                f'Prohibited term detected: {guideline.rule_name}',
                guideline.severity,
                guideline.rule_value,
                'This phrase appears in the submitted campaign content and conflicts with active guidance.',
                guideline.id,
                f'Replace "{guideline.rule_value}" with approved language that reflects brand-safe copy.',
                'confirmed',
            )

    product_guidelines = [g for g in guidelines if 'approved' in g.category.lower() or 'terminology' in g.category.lower()]
    product_names = [g.rule_value.lower() for g in product_guidelines if 'brand' in g.rule_value.lower() or 'ai' in g.rule_value.lower()]
    if product_names and not any(name in text for name in product_names):
        add_finding(
            'Approved product name missing',
            'medium',
            'Product name absent from submitted content',
            'The copy does not include the approved product name, which may cause brand inconsistency. This should be verified by a human reviewer.',
            product_guidelines[0].id if product_guidelines else None,
            'Add the approved product name in the campaign copy and confirm the placement is consistent with brand standards.',
            'needs_verification',
        )

    pricing_guidelines = [g for g in guidelines if 'pricing' in g.category.lower() or 'offer' in g.category.lower()]
    allowed_prices = [g.rule_value for g in pricing_guidelines if '$' in g.rule_value]
    found_prices = _extract_prices(submitted_content)
    for price in found_prices:
        if allowed_prices and not any(price.lower() in allowed_value.lower() for allowed_value in allowed_prices):
            add_finding(
                'Incorrect price detected',
                'medium',
                price,
                'The submitted content includes a price value that is not listed in the approved pricing guidance.',
                next((g.id for g in pricing_guidelines), None),
                'Align the promotion with the approved pricing list and remove or revise the unsupported value.',
                'confirmed',
            )

    offer_guidelines = [g for g in guidelines if 'offer' in g.category.lower()]
    for guideline in offer_guidelines:
        if 'off' in guideline.rule_value.lower() or 'until' in guideline.rule_value.lower():
            date_match = _extract_dates(guideline.rule_value)
            if date_match:
                date_text = date_match[0]
                try:
                    parsed_date = datetime.strptime(date_text, '%d %B %Y')
                except ValueError:
                    continue
                if parsed_date < datetime.utcnow():
                    add_finding(
                        'Expired offer detected',
                        'high',
                        date_text,
                        'The referenced offer is expired relative to the current date.',
                        guideline.id,
                        'Replace the expired offer with a current promotion or remove the outdated date.',
                        'confirmed',
                    )

    for phrase in ['guaranteed increase', 'best in class', '100% risk-free', 'instant results']:
        if phrase in text:
            add_finding(
                'Potentially unsupported claim',
                'medium',
                phrase,
                'This marketing statement may require substantiation before publication because it is a strong promotional claim.',
                next((g.id for g in guidelines if 'approved_claims' in g.category.lower()), None),
                'Use factual evidence-backed language and provide verification before publication.',
                'needs_verification',
            )

    if any(keyword in text for keyword in ['guaranteed', 'risk-free', 'best in class']):
        add_finding(
            'Missing evidence for claim support',
            'low',
            'Claims without supporting evidence were detected',
            'A strongly worded claim is present, but no matching approved evidence was found in the active guidelines.',
            next((g.id for g in guidelines if 'approved_claims' in g.category.lower()), None),
            'Add evidence or revise the claim before publish approval.',
            'needs_verification',
        )

    if not findings:
        add_finding(
            'No material issues detected',
            'low',
            'No prohibited language or unsupported claims were matched in the audit patterns.',
            'The copy appears consistent with the current demo rules; a manual final check is still recommended.',
            None,
            'Continue with standard publishing review.',
            'resolved',
        )

    total_score = min(100, max(0, 20 + sum(_score_finding(f['severity']) for f in findings)))
    risk_category = derive_risk_category(total_score)
    return total_score, risk_category, findings


def create_activity_event(db: Session, event_type: str, description: str, related_entity_id: str | None = None) -> None:
    db.add(ActivityEvent(event_type=event_type, description=description, related_entity_id=related_entity_id))
    db.commit()


def create_approval_record(db: Session, audit_id: int, decision: str, reviewer: str, comment: str | None) -> Approval:
    approval = Approval(audit_id=audit_id, decision=decision, reviewer=reviewer, comment=comment)
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval
