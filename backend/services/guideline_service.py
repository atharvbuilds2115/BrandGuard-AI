from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import BrandGuideline


DEFAULT_GUIDELINES = [
    {
        'rule_name': 'Prohibited phrase',
        'category': 'prohibited_terms',
        'description': 'Do not use guaranteed results language.',
        'rule_value': 'Guaranteed results',
        'severity': 'high',
        'active': True,
    },
    {
        'rule_name': 'Approved product name',
        'category': 'approved_terminology',
        'description': 'Use the approved brand name consistently.',
        'rule_value': 'BrandGuard AI',
        'severity': 'medium',
        'active': True,
    },
    {
        'rule_name': 'Approved pricing',
        'category': 'pricing',
        'description': 'Price rules for approved promotion language.',
        'rule_value': '$49/month',
        'severity': 'medium',
        'active': True,
    },
    {
        'rule_name': 'Approved pricing',
        'category': 'pricing',
        'description': 'Second approved price',
        'rule_value': '$99/month',
        'severity': 'medium',
        'active': True,
    },
    {
        'rule_name': 'Approved offer',
        'category': 'offers',
        'description': 'Offer valid until 30 November 2026.',
        'rule_value': '20% off until 30 November 2026',
        'severity': 'medium',
        'active': True,
    },
    {
        'rule_name': 'Prohibited claim',
        'category': 'prohibited_terms',
        'description': 'Do not claim no risk or certainty.',
        'rule_value': 'No risk',
        'severity': 'high',
        'active': True,
    },
    {
        'rule_name': 'Approved claim style',
        'category': 'approved_claims',
        'description': 'Marketing should stay factual and trustworthy.',
        'rule_value': 'Clear, trustworthy, professional',
        'severity': 'low',
        'active': True,
    },
]


def seed_default_guidelines(db: Session) -> None:
    if db.query(BrandGuideline).count() > 0:
        return

    for item in DEFAULT_GUIDELINES:
        guideline = BrandGuideline(
            rule_name=item['rule_name'],
            category=item['category'],
            description=item['description'],
            rule_value=item['rule_value'],
            severity=item['severity'],
            active=item['active'],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(guideline)

    db.commit()
