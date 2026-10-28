export const STORAGE_KEYS = {
  assets: 'brandguard-assets',
  guidelines: 'brandguard-guidelines',
  approvals: 'brandguard-approvals',
  activity: 'brandguard-activity',
  settings: 'brandguard-settings',
  auditResult: 'brandguard-audit-result',
};

export function safeReadStorage<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;

  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeStorage<T>(key: string, value: T) {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore storage quota issues gracefully
  }
}

export function clearStorageKey(key: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(key);
}
