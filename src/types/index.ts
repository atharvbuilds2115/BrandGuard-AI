export type RiskSeverity = 'High' | 'Medium' | 'Low';
export type AuditStatus = 'Confirmed' | 'Needs verification' | 'Resolved' | 'Needs review';
export type AssetStatus = 'Approved' | 'Pending' | 'Flagged';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'changes_requested';

export interface Asset {
  id: string;
  title: string;
  fileType: string;
  campaign: string;
  tags: string[];
  uploadDate: string;
  status: AssetStatus;
  previewUrl?: string;
  size?: string;
  dimensions?: string;
}

export interface BrandGuideline {
  id: string;
  category: string;
  title: string;
  description: string;
  value: string;
  demo: boolean;
  severity?: string;
  active?: boolean;
  requirementType?: 'required' | 'prohibited' | 'guidance';
  sourceDocumentId?: number;
  sourceReference?: string;
  sourceExcerpt?: string;
}

export interface Campaign {
  id: string;
  name: string;
  type: 'Social Media' | 'Website' | 'Email' | 'Advertisement';
  copy: string;
  status: ApprovalStatus;
  createdAt: string;
}

export interface AuditFinding {
  id: string;
  severity: RiskSeverity;
  title: string;
  description: string;
  evidence: string;
  rule: string;
  suggestion: string;
  status: AuditStatus;
}

export interface AuditResult {
  id: string;
  campaignName: string;
  campaignType: string;
  overallScore: number;
  riskLevel: RiskSeverity;
  createdAt: string;
  findings: AuditFinding[];
  recommendations: string[];
  demoNote: string;
  submittedContent?: string;
  analysisMode?: 'rules_only' | 'gemini_assisted' | 'groq_assisted' | 'demo';
}

export interface AuditSubmission {
  campaignName: string;
  campaignType: string;
  submittedContent: string;
}

export interface Approval {
  id: string;
  auditId?: string;
  campaignName: string;
  submittedBy: string;
  submittedAt: string;
  riskLevel: RiskSeverity;
  status: ApprovalStatus;
  assetCount: number;
  comment?: string;
  assignedReviewerUid?: string;
}

export interface ActivityEvent {
  id: string;
  type: string;
  title: string;
  status: string;
  campaignName?: string;
  timestamp: string;
}

export interface WorkspaceSettings {
  workspaceName: string;
  brandName: string;
  logoUrl: string;
  notifications: {
    approvals: boolean;
    guidelineChanges: boolean;
    auditResults: boolean;
  };
  reviewPreferences: {
    defaultRiskThreshold: string;
    requireManualReview: boolean;
    autoSaveResults: boolean;
  };
}
