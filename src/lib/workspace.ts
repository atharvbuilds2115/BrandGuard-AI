import type {
  ActivityEvent,
  Approval,
  AuditResult,
  AuditSubmission,
  BrandGuideline,
  WorkspaceSettings,
} from '../types';
import {
  backendRequest,
  getStoredWorkspaceId,
  listWorkspaceData,
  setActiveWorkspaceId,
  type ApiActivity,
  type ApiApproval,
  type ApiAudit,
  type ApiFinding,
  type ApiGuideline,
  type ApiProfile,
} from './backend';

export interface BackendWorkspaceData {
  guidelines: BrandGuideline[];
  audits: AuditResult[];
  approvals: Approval[];
  activity: ActivityEvent[];
  settings: WorkspaceSettings;
  workspaceRole: 'owner' | 'admin' | 'member';
}

const categoryLabels: Record<string, string> = {
  brand_overview: 'Brand Overview',
  logo_and_visual_identity: 'Logo and Visual Identity',
  logo_usage: 'Logo Usage',
  brand_colors: 'Brand Colors',
  typography: 'Typography',
  company_identity: 'Company Identity',
  tone_of_voice: 'Tone of Voice',
  prohibited_terminology: 'Prohibited Terminology',
  pricing_rules: 'Pricing Rules',
  marketing_claims: 'Marketing Claims',
  image_visual_guidelines: 'Image and Visual Guidelines',
  social_media_guidelines: 'Social Media Guidelines',
  other_company_policies: 'Other Company Policies',
  approved_claims: 'Approved Claims',
  approved_terminology: 'Approved Terminology',
  pricing_and_offers: 'Pricing and Offers',
  pricing: 'Pricing and Offers',
  offers: 'Pricing and Offers',
  prohibited_terms: 'Prohibited Terms',
};

function categoryKey(category: string): string {
  return category.toLowerCase().replace(/[\s-]+/g, '_');
}

export function mapApiGuideline(item: ApiGuideline): BrandGuideline {
  return {
    id: `guideline-${item.id}`,
    category: categoryLabels[categoryKey(item.category)] ?? item.category,
    title: item.rule_name,
    description: item.description ?? '',
    value: item.rule_value,
    demo: false,
    severity: item.severity,
    active: item.active,
    requirementType: item.requirement_type ?? 'guidance',
    sourceDocumentId: item.source_document_id ?? undefined,
    sourceReference: item.source_reference ?? undefined,
    sourceExcerpt: item.source_excerpt ?? undefined,
  };
}

function apiGuidelinePayload(item: BrandGuideline) {
  return {
    rule_name: item.title,
    category: categoryKey(item.category),
    description: item.description,
    rule_value: item.value,
    severity: item.severity ?? 'medium',
    active: item.active ?? true,
    requirement_type: item.requirementType ?? 'guidance',
  };
}

function parseNumericId(value: string, prefix: string): string {
  const match = value.match(new RegExp(`^${prefix}-(\\d+)$`));
  if (!match) throw new Error(`The ${prefix} identifier is invalid.`);
  return match[1];
}

function toSeverity(value: string): AuditResult['riskLevel'] {
  const severity = value.toLowerCase();
  if (severity === 'high') return 'High';
  if (severity === 'medium') return 'Medium';
  return 'Low';
}

function toFindingStatus(value: string): AuditResult['findings'][number]['status'] {
  const status = value.toLowerCase();
  if (status === 'resolved' || status === 'approved') return 'Resolved';
  if (status === 'needs_verification') return 'Needs verification';
  if (status === 'needs review' || status === 'needs_review') return 'Needs review';
  return 'Confirmed';
}

function mapFinding(finding: ApiFinding, guidelines: BrandGuideline[]) {
  const guideline = guidelines.find((item) => item.id === `guideline-${finding.related_guideline_id}`);
  return {
    id: `finding-${finding.id}`,
    severity: toSeverity(finding.severity),
    title: finding.finding_title,
    description: finding.explanation,
    evidence: finding.evidence_text,
    rule: guideline ? `${guideline.title} · ${guideline.category}` : 'Brand review',
    suggestion: finding.suggested_correction,
    status: toFindingStatus(finding.finding_status),
  };
}

function mapAudit(audit: ApiAudit, guidelines: BrandGuideline[]): AuditResult {
  const findings = audit.findings.map((item) => mapFinding(item, guidelines));
  return {
    id: `audit-${audit.id}`,
    campaignName: audit.campaign_name,
    campaignType: audit.campaign_type,
    overallScore: audit.risk_score,
    riskLevel: toSeverity(audit.risk_category),
    createdAt: audit.created_at,
    analysisMode: audit.analysis_mode,
    findings,
    recommendations: findings.length
      ? findings.map((item) => item.suggestion)
      : ['No active text rules were triggered. Review claims and context manually before publication.'],
    demoNote: 'Rule-based audit stored in the BrandGuard application database.',
    submittedContent: audit.submitted_content,
  };
}

function mapApproval(item: ApiApproval): Approval {
  return {
    id: String(item.id),
    auditId: `audit-${item.audit_id}`,
    campaignName: item.campaign_name,
    submittedBy: item.reviewer,
    submittedAt: item.decision_timestamp,
    riskLevel: toSeverity(item.risk_level),
    status: item.decision as Approval['status'],
    assetCount: item.asset_count,
    comment: item.comment ?? undefined,
  };
}

function mapActivity(item: ApiActivity): ActivityEvent {
  return {
    id: String(item.id),
    type: item.event_type,
    title: item.description,
    status: item.event_type.toLowerCase().includes('completed') ? 'Completed' : 'Updated',
    campaignName: item.related_entity_id ?? undefined,
    timestamp: item.timestamp,
  };
}

export async function ensureApplicationProfile(): Promise<{
  profile: ApiProfile;
  workspaceRole: 'owner' | 'admin' | 'member';
}> {
  const profile = await backendRequest<ApiProfile>('/api/profile');
  const workspaceData = await listWorkspaceData();
  const workspaces = workspaceData.workspaces;
  const storedId = getStoredWorkspaceId();
  const selected = workspaces.find((workspace) => workspace.id === storedId) ?? workspaces[0];
  if (!selected) throw new Error('No workspace is available for this account.');
  setActiveWorkspaceId(selected.id);
  return { profile, workspaceRole: selected.role };
}

export async function loadWorkspaceActivity(): Promise<ActivityEvent[]> {
  const records = await backendRequest<ApiActivity[]>('/api/activity?limit=100');
  return records.map(mapActivity);
}

export async function loadWorkspace(): Promise<BackendWorkspaceData> {
  const { profile, workspaceRole } = await ensureApplicationProfile();
  const [guidelineRecords, auditRecords, approvalRecords, activity] = await Promise.all([
    backendRequest<ApiGuideline[]>('/api/guidelines'),
    backendRequest<ApiAudit[]>('/api/audits'),
    backendRequest<ApiApproval[]>('/api/approvals/workspace'),
    loadWorkspaceActivity(),
  ]);
  const guidelines = guidelineRecords.map(mapApiGuideline);
  const audits = auditRecords.map((item) => mapAudit(item, guidelines));
  return {
    guidelines,
    audits,
    approvals: approvalRecords.map(mapApproval),
    activity,
    settings: profile.settings,
    workspaceRole,
  };
}

export async function listWorkspaceApprovals(): Promise<Approval[]> {
  const records = await backendRequest<ApiApproval[]>('/api/approvals/workspace', { cache: 'no-store' });
  return records.map(mapApproval);
}

export async function saveGuideline(guideline: BrandGuideline): Promise<BrandGuideline> {
  const match = guideline.id.match(/^guideline-(\d+)$/);
  const saved = match
    ? await backendRequest<ApiGuideline>(`/api/guidelines/${match[1]}`, {
        method: 'PATCH',
        body: JSON.stringify(apiGuidelinePayload(guideline)),
      })
    : await backendRequest<ApiGuideline>('/api/guidelines', {
        method: 'POST',
        body: JSON.stringify(apiGuidelinePayload(guideline)),
      });
  return mapApiGuideline(saved);
}

export async function removeGuideline(id: string): Promise<void> {
  const backendId = parseNumericId(id, 'guideline');
  await backendRequest<void>(`/api/guidelines/${backendId}`, { method: 'DELETE' });
}

export async function saveActivity(item: Omit<ActivityEvent, 'id' | 'timestamp'>): Promise<ActivityEvent> {
  const saved = await backendRequest<ApiActivity>('/api/activity', {
    method: 'POST',
    body: JSON.stringify({
      event_type: item.type,
      description: item.title,
      related_entity_id: item.campaignName ?? null,
    }),
  });
  return mapActivity(saved);
}

export async function saveApproval(approval: Approval): Promise<Approval> {
  const approvalId = approval.id.match(/^\d+$/)?.[0];
  if (!approvalId) throw new Error('The approval does not have a valid backend identifier.');
  const decision = approval.status === 'pending' ? 'changes_requested' : approval.status;
  const saved = await backendRequest<Omit<ApiApproval, 'campaign_name' | 'risk_level' | 'asset_count'>>(
    `/api/approvals/${approvalId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ decision, comment: approval.comment ?? null }),
    },
  );
  return {
    ...approval,
    id: String(saved.id),
    auditId: `audit-${saved.audit_id}`,
    submittedBy: saved.reviewer,
    submittedAt: saved.decision_timestamp,
    status: saved.decision as Approval['status'],
    comment: saved.comment ?? undefined,
  };
}

export async function createAudit(
  audit: AuditSubmission,
  guidelines: BrandGuideline[],
): Promise<{ audit: AuditResult; approval: Approval }> {
  const saved = await backendRequest<ApiAudit>('/api/audits', {
    method: 'POST',
    body: JSON.stringify({
      campaign_name: audit.campaignName,
      campaign_type: audit.campaignType,
      submitted_content: audit.submittedContent,
    }),
  });
  if (!saved.approval_id) throw new Error('The backend did not create an audit review record.');
  const mappedAudit = mapAudit(saved, guidelines);
  return {
    audit: mappedAudit,
    approval: {
      id: String(saved.approval_id),
      auditId: mappedAudit.id,
      campaignName: mappedAudit.campaignName,
      submittedBy: 'BrandGuard review',
      submittedAt: mappedAudit.createdAt,
      riskLevel: mappedAudit.riskLevel,
      status: 'pending',
      assetCount: 0,
    },
  };
}

export async function updateFindingStatus(
  auditId: string,
  findingId: string,
  status: AuditResult['findings'][number]['status'],
  guidelines: BrandGuideline[],
): Promise<AuditResult> {
  const backendAuditId = parseNumericId(auditId, 'audit');
  const backendFindingId = parseNumericId(findingId, 'finding');
  const statusValue = status === 'Needs verification' ? 'needs_verification' : status.toLowerCase();
  const saved = await backendRequest<ApiAudit>(
    `/api/audits/${backendAuditId}/findings/${backendFindingId}?status_value=${encodeURIComponent(statusValue)}`,
    { method: 'PATCH' },
  );
  return mapAudit(saved, guidelines);
}

export async function updateWorkspaceSettings(settings: WorkspaceSettings): Promise<WorkspaceSettings> {
  const profile = await backendRequest<ApiProfile>('/api/profile', {
    method: 'PUT',
    body: JSON.stringify({ settings }),
  });
  return profile.settings;
}
