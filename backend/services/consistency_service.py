from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.orm import Session, selectinload

from ..models import Audit, BrandGuideline


def _severity(value: str) -> str:
    normalized = value.casefold()
    return normalized if normalized in {'low', 'medium', 'high'} else 'low'


def _severity_counts(findings: list[Any]) -> dict[str, int]:
    counts = {'high': 0, 'medium': 0, 'low': 0}
    for finding in findings:
        severity = finding['severity'] if isinstance(finding, dict) else finding.severity
        counts[_severity(severity)] += 1
    return counts


def _issue_area(finding: Any, guideline: BrandGuideline | None) -> str:
    source = ' '.join((
        guideline.category.replace('_', ' ') if guideline else '',
        guideline.rule_name if guideline else '',
        finding.finding_title,
        finding.evidence_text,
        finding.explanation,
    )).casefold()
    if any(token in source for token in ('logo', 'brand mark', 'visual identity')):
        return 'logo'
    if any(token in source for token in ('color', 'colour', 'palette', 'hex code')):
        return 'color'
    if any(token in source for token in ('typography', 'typeface', 'font family', 'font size')):
        return 'typography'
    if any(token in source for token in (
        'messaging',
        'tone of voice',
        'approved terminology',
        'marketing claims',
        'approved claim',
        'claim style',
        'prohibited term',
        'prohibited phrase',
        'terminology',
        'brand voice',
        'copywriting',
    )):
        return 'messaging'
    return 'other'


def _normalized_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def build_consistency_report(
    db: Session,
    user_id: str,
    audit_ids: list[int],
    workspace_id: str | None = None,
) -> dict[str, Any]:
    if len(audit_ids) < 2 or len(audit_ids) > 50 or len(set(audit_ids)) != len(audit_ids):
        raise ValueError('Select between 2 and 50 distinct completed audits.')

    audit_query = (
        db.query(Audit)
        .options(selectinload(Audit.findings))
        .filter(
            Audit.id.in_(audit_ids),
            Audit.audit_status.ilike('completed'),
        )
    )
    if workspace_id:
        audit_query = audit_query.filter(Audit.workspace_id == workspace_id)
    else:
        audit_query = audit_query.filter(Audit.user_id == user_id)
    audits = audit_query.order_by(Audit.created_at.asc(), Audit.id.asc()).all()
    if len(audits) != len(audit_ids):
        raise LookupError('One or more selected completed audits are unavailable.')

    guideline_query = db.query(BrandGuideline).filter(BrandGuideline.active.is_(True))
    if workspace_id:
        guideline_query = guideline_query.filter(BrandGuideline.workspace_id == workspace_id)
    else:
        guideline_query = guideline_query.filter(BrandGuideline.user_id == user_id)
    guidelines = guideline_query.all()
    guidelines_by_id = {guideline.id: guideline for guideline in guidelines}
    campaigns: list[dict[str, Any]] = []
    grouped_findings: dict[str, dict[str, Any]] = {}
    guideline_findings: dict[int, list[dict[str, Any]]] = defaultdict(list)
    area_findings: dict[str, dict[str, Any]] = {}
    total_risk = 0
    risk_distribution = {'low': 0, 'medium': 0, 'high': 0}
    severity_distribution = {'high': 0, 'medium': 0, 'low': 0}

    for audit in audits:
        findings = [
            finding for finding in audit.findings
            if (
                finding.workspace_id == workspace_id
                if workspace_id
                else finding.user_id == user_id
            )
        ]
        risk_score = max(0, min(100, int(audit.risk_score or 0)))
        risk_category = audit.risk_category.casefold()
        if risk_category not in risk_distribution:
            risk_category = 'high' if risk_score >= 70 else 'medium' if risk_score >= 35 else 'low'
        counts = _severity_counts(findings)
        for severity, count in counts.items():
            severity_distribution[severity] += count
        risk_distribution[risk_category] += 1
        total_risk += risk_score
        campaigns.append({
            'audit_id': audit.id,
            'campaign_name': audit.campaign_name,
            'campaign_type': audit.campaign_type,
            'audited_at': audit.created_at.isoformat(),
            'risk_score': risk_score,
            'risk_category': risk_category,
            'compliance_score': 100 - risk_score,
            'finding_count': len(findings),
            'severity_counts': counts,
        })

        for finding in findings:
            guideline = guidelines_by_id.get(finding.related_guideline_id)
            evidence = finding.evidence_text.strip()
            title = finding.finding_title.strip()
            if not evidence or not title:
                continue
            guideline_key = (
                f'guideline:{guideline.id}' if guideline
                else f'finding:{_normalized_key(title)}'
            )
            saved_finding = {
                'audit_id': audit.id,
                'campaign_name': audit.campaign_name,
                'severity': _severity(finding.severity),
                'title': title,
                'evidence': evidence,
                'suggested_correction': finding.suggested_correction.strip(),
            }
            group = grouped_findings.setdefault(guideline_key, {
                'guideline_id': guideline.id if guideline else None,
                'guideline_name': guideline.rule_name if guideline else title,
                'area': _issue_area(finding, guideline),
                'findings': [],
                'campaign_ids': set(),
                'severity_counts': {'high': 0, 'medium': 0, 'low': 0},
            })
            group['findings'].append(saved_finding)
            group['campaign_ids'].add(audit.id)
            group['severity_counts'][saved_finding['severity']] += 1
            if guideline:
                guideline_findings[guideline.id].append(saved_finding)

            area = group['area']
            area_group = area_findings.setdefault(area, {
                'area': area,
                'finding_count': 0,
                'campaign_ids': set(),
                'evidence': [],
            })
            area_group['finding_count'] += 1
            area_group['campaign_ids'].add(audit.id)
            if len(area_group['evidence']) < 5:
                area_group['evidence'].append({
                    'campaign_name': audit.campaign_name,
                    'evidence': evidence,
                })

    recurring_violations = []
    recommendations_by_group = []
    for group in grouped_findings.values():
        campaign_count = len(group['campaign_ids'])
        findings = group['findings']
        corrections = [finding['suggested_correction'] for finding in findings if finding['suggested_correction']]
        if corrections:
            suggestion = Counter(corrections).most_common(1)[0][0]
            recommendations_by_group.append({
                'guideline_name': group['guideline_name'],
                'area': group['area'],
                'campaign_count': campaign_count,
                'based_on_findings': len(findings),
                'action': suggestion,
            })
        if campaign_count < 2:
            continue
        recurring_violations.append({
            'guideline_id': group['guideline_id'],
            'guideline_name': group['guideline_name'],
            'area': group['area'],
            'campaign_count': campaign_count,
            'occurrence_count': len(findings),
            'severity_counts': group['severity_counts'],
            'occurrences': findings,
        })

    recurring_violations.sort(key=lambda item: (-item['campaign_count'], -item['occurrence_count'], item['guideline_name']))
    frequent_guidelines = []
    for guideline_id, findings in guideline_findings.items():
        guideline = guidelines_by_id[guideline_id]
        frequent_guidelines.append({
            'guideline_id': guideline.id,
            'guideline_name': guideline.rule_name,
            'category': guideline.category,
            'finding_count': len(findings),
            'campaign_count': len({finding['audit_id'] for finding in findings}),
            'severity_counts': _severity_counts(findings),
            'evidence': [finding['evidence'] for finding in findings[:5]],
        })
    frequent_guidelines.sort(key=lambda item: (-item['finding_count'], -item['campaign_count'], item['guideline_name']))
    recommendations_by_group.sort(key=lambda item: (-item['campaign_count'], -item['based_on_findings']))
    consistency_areas = [
        {
            'area': item['area'],
            'finding_count': item['finding_count'],
            'campaign_count': len(item['campaign_ids']),
            'evidence': item['evidence'],
        }
        for item in sorted(area_findings.values(), key=lambda entry: (-len(entry['campaign_ids']), -entry['finding_count']))
    ]
    average_risk = round(total_risk / len(audits), 1)

    return {
        'campaigns': campaigns,
        'average_compliance_score': round(sum(item['compliance_score'] for item in campaigns) / len(campaigns), 1),
        'average_risk_score': average_risk,
        'risk_distribution': risk_distribution,
        'severity_distribution': severity_distribution,
        'risk_trends': [
            {
                'campaign_name': item['campaign_name'],
                'audited_at': item['audited_at'],
                'risk_score': item['risk_score'],
                'compliance_score': item['compliance_score'],
                'risk_category': item['risk_category'],
            }
            for item in campaigns
        ],
        'consistency_areas': consistency_areas,
        'recurring_violations': recurring_violations,
        'frequently_violated_guidelines': frequent_guidelines[:10],
        'recommendations': recommendations_by_group[:5],
    }