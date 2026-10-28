import { auth } from './firebase';
import type { Asset } from '../types';

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000';

interface UploadedAssetResponse {
  id: number;
  original_filename: string;
  mime_type: string;
  file_size: number;
  campaign_name: string | null;
  uploaded_at: string;
  review_status: string;
  tags: string;
}

async function authenticatedRequest(path: string, init?: RequestInit): Promise<Response> {
  if (!auth?.currentUser) throw new Error('Sign in before uploading a file.');
  const token = await auth.currentUser.getIdToken();
  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  return fetch(`${apiBaseUrl.replace(/\/$/, '')}${path}`, { ...init, headers });
}

async function readResponse<T>(response: Response): Promise<T> {
  const result = await response.json() as T & { detail?: string };
  if (!response.ok) {
    throw new Error(result.detail || `The API request failed with status ${response.status}.`);
  }
  return result;
}

function mapAsset(item: UploadedAssetResponse): Asset {
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

  const response = await authenticatedRequest('/api/assets/upload', {
    method: 'POST',
    body: formData,
  });
  return mapAsset(await readResponse<UploadedAssetResponse>(response));
}

export async function listAssetsFromBackend(): Promise<Asset[]> {
  const response = await authenticatedRequest('/api/assets');
  const items = await readResponse<UploadedAssetResponse[]>(response);
  return items.map(mapAsset);
}

export async function updateAssetInBackend(asset: Asset): Promise<void> {
  const assetId = asset.id.replace(/^asset-/, '');
  if (!/^\d+$/.test(assetId)) throw new Error('The asset does not have a valid backend identifier.');
  const response = await authenticatedRequest(`/api/assets/${assetId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      tags: JSON.stringify(asset.tags),
      campaign_name: asset.campaign,
      review_status: asset.status.toLowerCase(),
    }),
  });
  await readResponse<UploadedAssetResponse>(response);
}

export async function deleteAssetFromBackend(assetId: string): Promise<void> {
  const id = assetId.replace(/^asset-/, '');
  if (!/^\d+$/.test(id)) throw new Error('The asset does not have a valid backend identifier.');
  const response = await authenticatedRequest(`/api/assets/${id}`, { method: 'DELETE' });
  if (!response.ok) await readResponse<{ detail?: string }>(response);
}
