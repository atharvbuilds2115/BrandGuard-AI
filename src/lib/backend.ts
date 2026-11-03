import { auth } from './firebase';
import type { Asset, WorkspaceSettings } from '../types';

const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
const apiBaseUrl = configuredApiBaseUrl || (import.meta.env.DEV ? 'http://localhost:8000' : '');
let activeWorkspaceId: string | null = null;
let activeWorkspaceUserId: string | null = null;

function backendUrl(path: string): string {
  if (!apiBaseUrl) {
    throw new Error('VITE_API_BASE_URL is required in production. Set it to the deployed FastAPI URL and rebuild.');
  }
  return `${apiBaseUrl.replace(/\/$/, '')}${path}`;
}

export function setActiveWorkspaceId(workspaceId: string | null): void {
  activeWorkspaceId = workspaceId;
  const uid = auth?.currentUser?.uid;
  activeWorkspaceUserId = uid ?? null;
  if (!uid || typeof window === 'undefined') return;
  const key = `brandguard-active-workspace-${uid}`;
  if (workspaceId) window.localStorage.setItem(key, workspaceId);
  else window.localStorage.removeItem(key);
}

export function getStoredWorkspaceId(): string | null {
  const uid = auth?.currentUser?.uid;
  if (!uid || typeof window === 'undefined') return null;
  return window.localStorage.getItem(`brandguard-active-workspace-${uid}`);
}

function currentWorkspaceId(): string | null {
  const uid = auth?.currentUser?.uid;
  return uid && uid === activeWorkspaceUserId ? activeWorkspaceId : getStoredWorkspaceId();
}

export interface ApiWorkspace {
  id: string;
  name: string;
  role: 'owner' | 'admin' | 'member';
}

export interface ApiWorkspaceMember {
  user_id: string;
  email: string;
  role: 'owner' | 'admin' | 'member';
  created_at: string;
}

export interface ApiWorkspaceInvitation {
  id: string;
  workspace_name: string;
  role: 'admin' | 'member';
}

export interface ApiWorkspaceList {
  workspaces: ApiWorkspace[];
  pending_invitations: ApiWorkspaceInvitation[];
}

export async function listWorkspaceData(): Promise<ApiWorkspaceList> {
  return backendRequest<ApiWorkspaceList>('/api/workspaces');
}

export async function listWorkspaces(): Promise<ApiWorkspace[]> {
  return (await listWorkspaceData()).workspaces;
}

export async function acceptWorkspaceInvitation(invitationId: string): Promise<void> {
  await backendRequest(`/api/workspaces/invitations/${encodeURIComponent(invitationId)}/accept`, {
    method: 'POST',
  });
}

export async function createWorkspace(name: string): Promise<ApiWorkspace> {
  return backendRequest<ApiWorkspace>('/api/workspaces', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function listWorkspaceMembers(workspaceId: string): Promise<ApiWorkspaceMember[]> {
  return backendRequest<ApiWorkspaceMember[]>(`/api/workspaces/${encodeURIComponent(workspaceId)}/members`);
}

export async function inviteWorkspaceMember(
  workspaceId: string,
  email: string,
  role: 'member' | 'admin',
): Promise<void> {
  await backendRequest(`/api/workspaces/${encodeURIComponent(workspaceId)}/invitations`, {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
}

interface ApiAsset {
  id: number;
  original_filename: string;
  mime_type: string;
  file_size: number;
  campaign_name: string | null;
  uploaded_at: string;
  review_status: string;
  tags: string;
}

export interface ApiGuideline {
  id: number;
  rule_name: string;
  category: string;
  description: string | null;
  rule_value: string;
  severity: string;
  active: boolean;
  source_document_id?: number | null;
  source_reference?: string | null;
  source_excerpt?: string | null;
  requirement_type?: 'required' | 'prohibited' | 'guidance';
}

export interface ApiExtractedGuidelineRule {
  rule_name: string;
  category: string;
  description: string;
  rule_value: string;
  requirement_type: 'required' | 'prohibited' | 'guidance';
  severity: 'low' | 'medium' | 'high';
  source_reference: string;
  source_excerpt: string;
  manual_review: boolean;
  potential_duplicate: boolean;
}

export interface ApiGuidelineExtraction {
  original_filename: string;
  provider: 'gemini' | 'groq';
  model_used: string;
  document_id: number;
  rules: ApiExtractedGuidelineRule[];
}

export interface ApiSavedGuidelineImport {
  id: number;
  original_filename: string;
  provider: 'gemini' | 'groq';
  model_used: string;
  created_at: string;
  rules_saved: number;
  guidelines: ApiGuideline[];
}

export interface ApiGlobalSearchResult {
  category: 'Campaign' | 'Asset' | 'Guideline';
  id: number;
  name: string;
  description: string;
}

export interface ApiFinding {
  id: number;
  audit_id: number;
  finding_title: string;
  severity: string;
  evidence_text: string;
  explanation: string;
  related_guideline_id: number | null;
  suggested_correction: string;
  finding_status: string;
}

export interface ApiAudit {
  id: number;
  approval_id?: number | null;
  campaign_name: string;
  campaign_type: string;
  submitted_content: string;
  risk_score: number;
  risk_category: string;
  audit_status: string;
  analysis_mode: 'rules_only' | 'gemini_assisted' | 'groq_assisted';
  created_at: string;
  findings: ApiFinding[];
}

export interface ApiApproval {
  id: number;
  audit_id: number;
  decision: string;
  reviewer: string;
  comment: string | null;
  decision_timestamp: string;
  campaign_name: string;
  risk_level: string;
  asset_count: number;
}

export interface ApiActivity {
  id: number;
  event_type: string;
  description: string;
  related_entity_id: string | null;
  timestamp: string;
}

export interface ApiProfile {
  uid: string;
  email: string;
  display_name: string;
  settings: WorkspaceSettings;
}

export interface ApiVideoFinding {
  timestamp_seconds: number;
  timestamp: string;
  title: string;
  severity: 'low' | 'medium' | 'high';
  category: 'logo' | 'color' | 'typography' | 'visual_consistency' | 'on_screen_text' | 'other';
  evidence: string;
  explanation: string;
  suggested_correction: string;
  status: string;
}

export interface ApiVideoReview {
  id: number;
  original_filename: string;
  duration_seconds: number;
  frame_count: number;
  risk_score: number;
  risk_category: 'low' | 'medium' | 'high';
  compliance_score: number;
  model_used: string | null;
  fallback_used: boolean;
  analysis_mode: 'gemini_assisted' | 'groq_assisted' | 'demo_sample';
  findings: ApiVideoFinding[];
  created_at: string;
}

export interface ApiConsistencyCampaign {
  audit_id: number;
  campaign_name: string;
  campaign_type: string;
  audited_at: string;
  risk_score: number;
  risk_category: 'low' | 'medium' | 'high';
  compliance_score: number;
  finding_count: number;
  severity_counts: Record<'high' | 'medium' | 'low', number>;
}

export interface ApiConsistencyReportData {
  demonstration_note?: string;
  campaigns: ApiConsistencyCampaign[];
  average_compliance_score: number;
  average_risk_score: number;
  risk_distribution: Record<'low' | 'medium' | 'high', number>;
  severity_distribution: Record<'high' | 'medium' | 'low', number>;
  risk_trends: Array<{
    campaign_name: string;
    audited_at: string;
    risk_score: number;
    compliance_score: number;
    risk_category: string;
  }>;
  consistency_areas: Array<{
    area: string;
    finding_count: number;
    campaign_count: number;
    evidence: Array<{ campaign_name: string; evidence: string }>;
  }>;
  recurring_violations: Array<{
    guideline_id: number | null;
    guideline_name: string;
    area: string;
    campaign_count: number;
    occurrence_count: number;
    severity_counts: Record<'high' | 'medium' | 'low', number>;
    occurrences: Array<{
      audit_id: number;
      campaign_name: string;
      severity: string;
      title: string;
      evidence: string;
      suggested_correction: string;
    }>;
  }>;
  frequently_violated_guidelines: Array<{
    guideline_id: number;
    guideline_name: string;
    category: string;
    finding_count: number;
    campaign_count: number;
    severity_counts: Record<'high' | 'medium' | 'low', number>;
    evidence: string[];
  }>;
  recommendations: Array<{
    guideline_name: string;
    area: string;
    campaign_count: number;
    based_on_findings: number;
    action: string;
  }>;
}

export interface ApiConsistencyReport {
  id: number;
  audit_ids: number[];
  campaign_count: number;
  report_data: ApiConsistencyReportData;
  created_at: string;
}

async function fetchApi(path: string, init: RequestInit | undefined, token: string): Promise<Response> {
  const headers = new Headers(init?.headers);
  const workspaceId = currentWorkspaceId();
  if (workspaceId) headers.set('X-Workspace-ID', workspaceId);
  headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');

  const url = backendUrl(path);
  try {
    return await fetch(url, { ...init, headers });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new Error(`The BrandGuard API is unavailable at ${apiBaseUrl}. Start the FastAPI backend and try again.`);
  }
}

export async function backendRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const user = auth?.currentUser;
  if (!user) throw new Error('Sign in to access your application data.');

  let token = await user.getIdToken();
  let response = await fetchApi(path, init, token);
  if (response.status === 401 && auth?.currentUser?.uid === user.uid) {
    token = await user.getIdToken(true);
    response = await fetchApi(path, init, token);
  }

  const text = await response.text();
  let result: unknown;
  try {
    result = text ? JSON.parse(text) : undefined;
  } catch {
    if (!response.ok) throw new Error(`The API request failed with status ${response.status}.`);
    throw new Error('The API returned an invalid response.');
  }

  if (!response.ok) {
    const detail =
      typeof result === 'object' && result !== null && 'detail' in result && typeof result.detail === 'string'
        ? result.detail
        : `The API request failed with status ${response.status}.`;
    throw new Error(detail);
  }
  return result as T;
}

export function backendErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'The BrandGuard API request failed. Please try again.';
}

function mapAsset(item: ApiAsset): Asset {
  let parsedTags: unknown;
  try {
    parsedTags = JSON.parse(item.tags);
  } catch {
    throw new Error(`The backend returned invalid tag data for asset ${item.id}.`);
  }
  if (!Array.isArray(parsedTags) || !parsedTags.every((tag) => typeof tag === 'string')) {
    throw new Error(`The backend returned invalid tag data for asset ${item.id}.`);
  }
  const image = item.mime_type.startsWith('image/');
  return {
    id: `asset-${item.id}`,
    title: item.original_filename,
    fileType: image ? 'Image' : item.mime_type.includes('pdf') ? 'PDF' : 'Document',
    campaign: item.campaign_name ?? 'New Upload',
    tags: parsedTags,
    uploadDate: item.uploaded_at.slice(0, 10),
    status: item.review_status === 'approved' ? 'Approved' : item.review_status === 'flagged' ? 'Flagged' : 'Pending',
    size: `${(item.file_size / 1024 / 1024).toFixed(1)} MB`,
    dimensions: image ? 'Uploaded file' : 'n/a',
  };
}

export async function uploadAssetToBackend(file: File): Promise<Asset> {
  const formData = new FormData();
  formData.append('file', file);
  const result = await backendRequest<ApiAsset>('/api/assets/upload', { method: 'POST', body: formData });
  return mapAsset(result);
}

export async function extractGuidelineDocument(
  file: File,
  onUploadProgress: (progress: number) => void,
): Promise<ApiGuidelineExtraction> {
  const user = auth?.currentUser;
  if (!user) throw new Error('Sign in to import company guidelines.');
  const formData = new FormData();
  formData.append('file', file);

  const send = (token: string) => new Promise<Response>((resolve, reject) => {
    const request = new XMLHttpRequest();
    try {
      request.open('POST', backendUrl('/api/guideline-imports/extract'));
    } catch (error) {
      reject(error);
      return;
    }
    request.setRequestHeader('Authorization', `Bearer ${token}`);
    const workspaceId = currentWorkspaceId();
    if (workspaceId) request.setRequestHeader('X-Workspace-ID', workspaceId);
    request.responseType = 'text';
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onUploadProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onerror = () => reject(new Error(
      `The BrandGuard API is unavailable at ${apiBaseUrl}. Start the FastAPI backend and try again.`,
    ));
    request.onabort = () => reject(new Error('The guideline document upload was cancelled.'));
    request.onload = () => resolve(new Response(request.responseText, {
      status: request.status,
      statusText: request.statusText,
      headers: { 'Content-Type': request.getResponseHeader('Content-Type') ?? 'application/json' },
    }));
    request.send(formData);
  });

  let token = await user.getIdToken();
  let response = await send(token);
  if (response.status === 401 && auth?.currentUser?.uid === user.uid) {
    token = await user.getIdToken(true);
    response = await send(token);
  }
  const text = await response.text();
  let result: unknown;
  try {
    result = text ? JSON.parse(text) : undefined;
  } catch {
    throw new Error(response.ok ? 'The API returned an invalid response.' : `The API request failed with status ${response.status}.`);
  }
  if (!response.ok) {
    const detail =
      typeof result === 'object' && result !== null && 'detail' in result && typeof result.detail === 'string'
        ? result.detail
        : `The API request failed with status ${response.status}.`;
    throw new Error(detail);
  }
  return result as ApiGuidelineExtraction;
}

export async function saveGuidelineImport(
  extraction: ApiGuidelineExtraction,
  rules: ApiExtractedGuidelineRule[],
): Promise<ApiSavedGuidelineImport> {
  return backendRequest<ApiSavedGuidelineImport>('/api/guideline-imports', {
    method: 'POST',
    body: JSON.stringify({
      original_filename: extraction.original_filename,
      provider: extraction.provider,
      model_used: extraction.model_used,
      document_id: extraction.document_id,
      rules,
    }),
  });
}

export async function listAssetsFromBackend(): Promise<Asset[]> {
  const items = await backendRequest<ApiAsset[]>('/api/assets');
  return items.map(mapAsset);
}

export async function searchWorkspace(query: string, signal?: AbortSignal): Promise<ApiGlobalSearchResult[]> {
  const params = new URLSearchParams({ q: query });
  return backendRequest<ApiGlobalSearchResult[]>(`/api/search?${params.toString()}`, { signal });
}

export async function updateAssetInBackend(asset: Asset): Promise<void> {
  const assetId = asset.id.replace(/^asset-/, '');
  if (!/^\d+$/.test(assetId)) throw new Error('The asset does not have a valid backend identifier.');
  await backendRequest<ApiAsset>(`/api/assets/${assetId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      tags: JSON.stringify(asset.tags),
      campaign_name: asset.campaign,
      review_status: asset.status.toLowerCase(),
    }),
  });
}

export async function deleteAssetFromBackend(assetId: string): Promise<void> {
  const id = assetId.replace(/^asset-/, '');
  if (!/^\d+$/.test(id)) throw new Error('The asset does not have a valid backend identifier.');
  await backendRequest<void>(`/api/assets/${id}`, { method: 'DELETE' });
}

export async function uploadVideoForReview(file: File): Promise<ApiVideoReview> {
  const formData = new FormData();
  formData.append('file', file);
  return backendRequest<ApiVideoReview>('/api/video-reviews', { method: 'POST', body: formData });
}

export async function listVideoReviews(): Promise<ApiVideoReview[]> {
  return backendRequest<ApiVideoReview[]>('/api/video-reviews');
}

export async function listCompletedAudits(): Promise<ApiAudit[]> {
  return backendRequest<ApiAudit[]>('/api/audits?status=completed');
}

export async function listConsistencyReports(): Promise<ApiConsistencyReport[]> {
  return backendRequest<ApiConsistencyReport[]>('/api/consistency-reports');
}

export async function createConsistencyReport(auditIds: number[]): Promise<ApiConsistencyReport> {
  return backendRequest<ApiConsistencyReport>('/api/consistency-reports', {
    method: 'POST',
    body: JSON.stringify({ audit_ids: auditIds }),
  });
}
