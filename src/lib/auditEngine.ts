import type { AuditResult, AuditFinding, BrandGuideline } from '../types';

export function runDemoAudit(
  campaignName: string,
  campaignType: string,
  copy: string,
  guidelines: BrandGuideline[],
): AuditResult {
  const findings: AuditFinding[] = [];
  const text = copy.toLowerCase();
  const prohibitedTerms = guidelines
    .filter((item) => item.category === 'Prohibited Terms')
    .map((item) => item.value.toLowerCase());

  prohibitedTerms.forEach((term) => {
    if (text.includes(term)) {
      findings.push({
        id: `finding-prohibited-${term}`,
        severity: 'High',
        title: `Prohibited language detected: "${term}"`,
        description: 'This phrase is prohibited in brand-approved marketing copy.',
        evidence: term,
        rule: 'Prohibited Terms',
        suggestion: `Replace "${term}" with approved messaging that stays within policy guardrails.`,
        status: 'Confirmed',
      });
    }
  });

  const pricingRules = guidelines.filter((item) => item.category === 'Pricing and Offers');
  const pricingValues = pricingRules
    .map((rule) => rule.value)
    .join(' ')
    .toLowerCase();

  const rawPrices = [...copy.matchAll(/\$\d+(?:\.\d+)?|\$\d+(?:,\d{3})*(?:\.\d+)?|\d+%/g)].map((match) => match[0]);
  if (rawPrices.length > 0) {
    const invalidPrice = rawPrices.some((price) => {
      const formatted = price.toLowerCase();
      return !pricingValues.includes(formatted);
    });

    if (invalidPrice) {
      findings.push({
        id: 'finding-price',
        severity: 'Medium',
        title: 'Pricing is not aligned to approved offers',
        description: 'The campaign references pricing that is not recognized in approved guidance.',
        evidence: rawPrices.join(', '),
        rule: 'Pricing and Offers',
        suggestion: 'Align pricing language with the approved price book and current offer window.',
        status: 'Confirmed',
      });
    }
  }

  const offerWindow = guidelines.find((item) => item.category === 'Pricing and Offers' && item.title === 'Approved offer');
  if (offerWindow && /\d{1,2}\s+[A-Z][a-z]+\s+\d{4}/.test(copy)) {
    const dateMatch = copy.match(/\d{1,2}\s+[A-Z][a-z]+\s+\d{4}/g);
    if (dateMatch?.length) {
      const asDate = new Date(dateMatch[0].replace(/\s+/g, ' '));
      if (!Number.isNaN(asDate.getTime()) && asDate < new Date('2026-11-30T00:00:00Z')) {
        findings.push({
          id: 'finding-date',
          severity: 'High',
          title: 'Offer expiration date may be expired',
          description: 'The copied date suggests the promotion is already past its approved valid period.',
          evidence: dateMatch[0],
          rule: 'Pricing and Offers',
          suggestion: 'Update the claim to a current offer period or remove the outdated date.',
          status: 'Confirmed',
        });
      }
    }
  }

  const approvedProductName = guidelines.find((item) => item.category === 'Approved Claims' && item.title === 'Approved product name');
  if (approvedProductName && !text.includes(approvedProductName.value.toLowerCase())) {
    findings.push({
      id: 'finding-product-name',
      severity: 'Medium',
      title: 'Approved product name missing',
      description: 'The copied content does not reference the approved product name, which can create consistency risks.',
      evidence: 'Product name omitted',
      rule: 'Approved Claims',
      suggestion: 'Add “BrandGuard AI” to the copy in the approved brand format.',
      status: 'Needs verification',
    });
  }

  const unsupportedClaims = ['guaranteed increase', 'instant results', '100% risk-free', 'best in class'];
  unsupportedClaims.forEach((claim) => {
    if (text.includes(claim)) {
      findings.push({
        id: `finding-claim-${claim}`,
        severity: 'Medium',
        title: 'Promotion wording may need review',
        description: 'This wording may be perceived as a performance claim and requires a human review.',
        evidence: claim,
        rule: 'Approved Claims',
        suggestion: 'Use factual, evidence-based claims and add substantiation before publishing.',
        status: 'Needs verification',
      });
    }
  });

  const riskLevel = findings.some((item) => item.severity === 'High') ? 'High' : findings.some((item) => item.severity === 'Medium') ? 'Medium' : 'Low';
  const recommendations = findings.length
    ? findings.map((item) => item.suggestion)
    : ['No blocking issues detected. Continue with careful review before approval.'];

  const scoreBase = findings.reduce((total, item) => {
    if (item.severity === 'High') return total + 28;
    if (item.severity === 'Medium') return total + 16;
    return total + 8;
  }, 0);

  const overallScore = Math.min(100, Math.max(0, 38 + scoreBase));

  return {
    id: `audit-${Date.now()}`,
    campaignName,
    campaignType,
    overallScore,
    riskLevel,
    createdAt: new Date().toISOString(),
    findings:
      findings.length > 0
        ? findings
        : [
            {
              id: 'finding-safe',
              severity: 'Low',
              title: 'Copy is in good standing',
              description: 'No material violations were identified in this deterministic demo check.',
              evidence: 'No prohibited or expired claims found',
              rule: 'General review',
              suggestion: 'Proceed with final human review before publishing.',
              status: 'Resolved',
            },
          ],
    recommendations,
    demoNote: 'Demo rule-based audit only. No external AI service is connected.',
  };
}
