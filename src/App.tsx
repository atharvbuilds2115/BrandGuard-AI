import { useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from 'react';
import { BrowserRouter, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import type { User } from 'firebase/auth';
import {
  Area,
  AreaChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Check,
  CheckCheck,
  ChevronDown,
  CircleAlert,
  Copy,
  FileImage,
  FileText,
  FolderOpen,
  Grid2x2,
  History,
  LayoutDashboard,
  ListFilter,
  LogOut,
  Menu,
  PenSquare,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Tag,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { defaultSettings, demoActivity, demoApprovals, demoAssets, demoGuidelines } from './data/demoData';
import { runDemoAudit } from './lib/auditEngine';
import { STORAGE_KEYS, clearStorageKey, safeReadStorage, writeStorage } from './lib/storage';
import AuthScreen from './components/AuthScreen';
import {
  deleteAssetFromBackend,
  listAssetsFromBackend,
  updateAssetInBackend,
  uploadAssetToBackend,
} from './lib/backend';
import {
  cloudErrorMessage,
  loadWorkspace,
  removeAsset,
  removeGuideline,
  saveActivity,
  saveApproval,
  saveAudit,
  saveAuditSubmission,
  saveGuideline,
  saveSettings,
} from './lib/firestore';
import { firebaseConfigState, firebaseConfigured, listenToAuthState, logout } from './lib/firebase';
import type {
  ActivityEvent,
  Approval,
  Asset,
  AuditResult,
  BrandGuideline,
  WorkspaceSettings,
} from './types';

type ToastState = {
  kind: 'success' | 'error';
  message: string;
};

type ReviewFormState = {
  name: string;
  type: 'Social Media' | 'Website' | 'Email' | 'Advertisement';
  copy: string;
};

type DemoPreviousState = {
  assets: Asset[];
  guidelines: BrandGuideline[];
  approvals: Approval[];
  activity: ActivityEvent[];
  settings: WorkspaceSettings;
  auditResult: AuditResult | null;
  audits: AuditResult[];
};

const navItems = [
  { label: 'Dashboard', path: '/dashboard', Icon: LayoutDashboard },
  { label: 'Asset Library', path: '/assets', Icon: FolderOpen },
  { label: 'Brand Guidelines', path: '/guidelines', Icon: ShieldCheck },
  { label: 'Campaign Review', path: '/reviews', Icon: Sparkles },
  { label: 'Approvals', path: '/approvals', Icon: CheckCheck },
  { label: 'Activity History', path: '/activity', Icon: History },
  { label: 'Settings', path: '/settings', Icon: Settings },
];

function createDemoAuditHistory(): AuditResult[] {
  return [
    {
      ...runDemoAudit(
        'Spring Launch (Sample)',
        'Social Media',
        'Guaranteed results with our 100% risk-free launch offer.',
        demoGuidelines,
      ),
      id: 'demo-audit-spring-launch',
      createdAt: '2026-10-25T10:00:00.000Z',
    },
    {
      ...runDemoAudit(
        'Q4 Retargeting (Sample)',
        'Email',
        'No risk when you try BrandGuard AI. Get the Pro plan for $99/month.',
        demoGuidelines,
      ),
      id: 'demo-audit-q4-retargeting',
      createdAt: '2026-10-22T14:30:00.000Z',
    },
  ];
}

const activityChartData = [
  { day: 'Mon', reviews: 5 },
  { day: 'Tue', reviews: 8 },
  { day: 'Wed', reviews: 6 },
  { day: 'Thu', reviews: 10 },
  { day: 'Fri', reviews: 7 },
  { day: 'Sat', reviews: 12 },
  { day: 'Sun', reviews: 9 },
];

const riskChartData = [
  { name: 'Low', value: 42, color: '#22c55e' },
  { name: 'Medium', value: 31, color: '#f59e0b' },
  { name: 'High', value: 19, color: '#ef4444' },
];

const statusStyles: Record<string, string> = {
  Approved: 'bg-emerald-100 text-emerald-700',
  Pending: 'bg-amber-100 text-amber-700',
  Flagged: 'bg-red-100 text-red-700',
  High: 'bg-red-100 text-red-700',
  Medium: 'bg-amber-100 text-amber-700',
  Low: 'bg-emerald-100 text-emerald-700',
  resolved: 'bg-blue-100 text-blue-700',
  'Needs verification': 'bg-violet-100 text-violet-700',
  Confirmed: 'bg-red-100 text-red-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
  pending: 'bg-amber-100 text-amber-700',
  updated: 'bg-sky-100 text-sky-700',
  completed: 'bg-emerald-100 text-emerald-700',
};

function App() {
  const [demoMode, setDemoMode] = useState(false);
  const demoPreviousState = useRef<DemoPreviousState | null>(null);
  const [assets, setAssets] = useState<Asset[]>(() => safeReadStorage(STORAGE_KEYS.assets, demoAssets));
  const [guidelines, setGuidelines] = useState<BrandGuideline[]>(() => safeReadStorage(STORAGE_KEYS.guidelines, demoGuidelines));
  const [approvals, setApprovals] = useState<Approval[]>(() => safeReadStorage(STORAGE_KEYS.approvals, demoApprovals));
  const [activity, setActivity] = useState<ActivityEvent[]>(() => safeReadStorage(STORAGE_KEYS.activity, demoActivity));
  const [settings, setSettings] = useState<WorkspaceSettings>(() => safeReadStorage(STORAGE_KEYS.settings, defaultSettings));
  const [auditResult, setAuditResult] = useState<AuditResult | null>(() => safeReadStorage(STORAGE_KEYS.auditResult, null));
  const [audits, setAudits] = useState<AuditResult[]>([]);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(firebaseConfigured);
  const [authError, setAuthError] = useState('');
  const [loadedUid, setLoadedUid] = useState<string | null>(null);
  const [cloudLoading, setCloudLoading] = useState(false);
  const [cloudLoadError, setCloudLoadError] = useState('');
  const [cloudReloadKey, setCloudReloadKey] = useState(0);
  const [assetLoadError, setAssetLoadError] = useState('');

  useEffect(() => {
    if (!firebaseConfigured) return;
    try {
      return listenToAuthState(
        (user) => {
          setAuthUser(user);
          setAuthLoading(false);
          setAuthError('');
        },
        (error) => {
          setAuthError(error.message);
          setAuthLoading(false);
        },
      );
    } catch (error) {
      setAuthError(cloudErrorMessage(error));
      setAuthLoading(false);
      return undefined;
    }
  }, []);

  useEffect(() => {
    if (!firebaseConfigured || !authUser || demoMode) {
      setLoadedUid(null);
      setCloudLoading(false);
      return;
    }
    let active = true;
    setCloudLoading(true);
    setCloudLoadError('');
    void loadWorkspace(authUser).then(async (workspace) => {
      if (!active) return;
      let workspaceAssets: Asset[] = [];
      try {
        workspaceAssets = await listAssetsFromBackend();
        if (active) setAssetLoadError('');
      } catch (error) {
        if (active) setAssetLoadError(`Backend asset service unavailable: ${cloudErrorMessage(error)}`);
      }
      if (!active) return;
      setAssets(workspaceAssets);
      setGuidelines(workspace.guidelines);
      setApprovals(workspace.approvals);
      setActivity(workspace.activity);
      setSettings(workspace.settings);
      setAudits(workspace.audits);
      setAuditResult(workspace.audits[0] ?? null);
      setLoadedUid(authUser.uid);
      setCloudLoading(false);
    }).catch((error: unknown) => {
      if (!active) return;
      setCloudLoadError(cloudErrorMessage(error));
      setCloudLoading(false);
    });
    return () => {
      active = false;
    };
  }, [authUser, cloudReloadKey, demoMode]);

  useEffect(() => {
    if (firebaseConfigured || demoMode) return;
    writeStorage(STORAGE_KEYS.assets, assets);
  }, [assets, demoMode]);

  useEffect(() => {
    if (firebaseConfigured || demoMode) return;
    writeStorage(STORAGE_KEYS.guidelines, guidelines);
  }, [guidelines, demoMode]);

  useEffect(() => {
    if (firebaseConfigured || demoMode) return;
    writeStorage(STORAGE_KEYS.approvals, approvals);
  }, [approvals, demoMode]);

  useEffect(() => {
    if (firebaseConfigured || demoMode) return;
    writeStorage(STORAGE_KEYS.activity, activity);
  }, [activity, demoMode]);

  useEffect(() => {
    if (firebaseConfigured || demoMode) return;
    writeStorage(STORAGE_KEYS.settings, settings);
  }, [settings, demoMode]);

  useEffect(() => {
    if (firebaseConfigured || demoMode) return;
    writeStorage(STORAGE_KEYS.auditResult, auditResult);
  }, [auditResult, demoMode]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 2500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const addActivity = (item: Omit<ActivityEvent, 'id' | 'timestamp'>) => {
    const event: ActivityEvent = {
      ...item,
      id: `event-${Date.now()}-${crypto.randomUUID()}`,
      timestamp: new Date().toISOString(),
    };
    setActivity((current) => [event, ...current]);
    if (firebaseConfigured && authUser && !demoMode) {
      void saveActivity(authUser.uid, event).catch((error: unknown) => {
        setToast({ kind: 'error', message: `Activity could not be saved: ${cloudErrorMessage(error)}` });
      });
    }
  };

  const handleGuidelineSave = async (next: BrandGuideline) => {
    if (firebaseConfigured && authUser && !demoMode) await saveGuideline(authUser.uid, next);
    setGuidelines((current) => {
      const existing = current.some((item) => item.id === next.id);
      if (existing) {
        return current.map((item) => (item.id === next.id ? next : item));
      }
      return [next, ...current];
    });
    addActivity({
      type: 'Brand guideline updated',
      title: next.title,
      status: 'Updated',
      campaignName: 'Brand Guidelines',
    });
    setToast({ kind: 'success', message: demoMode ? 'Demo guideline updated in memory only; it will not be saved.' : 'Brand guideline saved to Firestore.' });
  };

  const handleGuidelineDelete = async (id: string) => {
    const target = guidelines.find((item) => item.id === id);
    if (firebaseConfigured && authUser && !demoMode) await removeGuideline(authUser.uid, id);
    setGuidelines((current) => current.filter((item) => item.id !== id));
    if (target) {
      addActivity({
        type: 'Brand guideline updated',
        title: target.title,
        status: 'Removed',
        campaignName: 'Brand Guidelines',
      });
    }
    setToast({ kind: 'success', message: demoMode ? 'Demo guideline removed in memory only; it will not be saved.' : 'Guideline removed.' });
  };

  const handleApprovalUpdate = async (id: string, status: Approval['status'], comment?: string) => {
    const approval = approvals.find((item) => item.id === id);
    if (!approval) return;
    const updatedApproval = { ...approval, status, comment: comment ?? approval.comment };
    try {
      if (firebaseConfigured && authUser && !demoMode) await saveApproval(authUser.uid, updatedApproval);
    } catch (error) {
      setToast({ kind: 'error', message: `Approval could not be saved: ${cloudErrorMessage(error)}` });
      return;
    }
    setApprovals((current) =>
      current.map((item) =>
        item.id === id
          ? updatedApproval
          : item,
      ),
    );

    addActivity({
      type: status === 'approved' ? 'Campaign approved' : status === 'rejected' ? 'Campaign rejected' : 'Approval updated',
      title: approval.campaignName,
      status: status === 'approved' ? 'Approved' : status === 'rejected' ? 'Rejected' : 'Review pending',
      campaignName: approval.campaignName,
    });

    setToast({
      kind: 'success',
      message: status === 'approved' ? 'Campaign approved.' : status === 'rejected' ? 'Campaign rejected.' : 'Approval updated.',
    });
  };

  const handleAssetUpload = async (file: File) => {
    if (firebaseConfigured && authUser && !demoMode) {
      try {
        const uploaded = await uploadAssetToBackend(file);
        setAssets((current) => [uploaded, ...current]);
        setAssetLoadError('');
        addActivity({
          type: 'Asset uploaded',
          title: uploaded.title,
          status: 'Completed',
          campaignName: uploaded.campaign,
        });
        setToast({ kind: 'success', message: 'Asset uploaded securely and saved.' });
      } catch (error) {
        setToast({ kind: 'error', message: `Upload failed: ${cloudErrorMessage(error)}` });
      }
      return;
    }

    const isImage = file.type.startsWith('image/');
    const title = file.name;
    const newAsset: Asset = {
      id: `asset-${Date.now()}`,
      title,
      fileType: isImage ? 'Image' : file.type.includes('pdf') ? 'PDF' : 'Document',
      campaign: 'New Upload',
      tags: ['uploaded', 'recent'],
      uploadDate: new Date().toISOString().slice(0, 10),
      status: 'Pending',
      previewUrl: isImage ? URL.createObjectURL(file) : '',
      size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
      dimensions: isImage ? 'Uploaded file' : 'n/a',
    };

    setAssets((current) => [newAsset, ...current]);
    addActivity({
      type: 'Asset uploaded',
      title: newAsset.title,
      status: 'Completed',
      campaignName: 'New Upload',
    });
    setToast({ kind: 'success', message: demoMode ? 'Demo asset added in memory only; it will not be saved.' : 'Asset uploaded and saved locally.' });
  };

  const resetDemoData = () => {
    if (firebaseConfigured && !demoMode) {
      setToast({ kind: 'error', message: 'Reset demo data is only available in local demo mode.' });
      return;
    }
    setAssets(demoAssets);
    setGuidelines(demoGuidelines);
    setApprovals(demoApprovals);
    setActivity(demoActivity);
    setSettings(defaultSettings);
    const sampleAudits = demoMode ? createDemoAuditHistory() : [];
    setAudits(sampleAudits);
    setAuditResult(sampleAudits[0] ?? null);
    if (!demoMode) clearStorageKey(STORAGE_KEYS.auditResult);
    setToast({ kind: 'success', message: 'Demo data reset for this session.' });
  };

  const dashboardStats = useMemo(() => {
    const pendingApprovals = approvals.filter((item) => item.status === 'pending').length;
    const approvedAssets = assets.filter((item) => item.status === 'Approved').length;
    const highRiskApprovals = approvals.filter((item) => item.riskLevel === 'High').length;
    return {
      totalAssets: assets.length,
      campaignsReviewed: firebaseConfigured ? audits.length : demoMode ? audits.length : approvals.length + 18,
      pendingApprovals,
      highRiskFindings: firebaseConfigured || demoMode
        ? audits.reduce((total, audit) => total + audit.findings.filter((finding) => finding.severity === 'High').length, 0)
        : highRiskApprovals + 2,
      assetApprovalRate: Math.round((approvedAssets / Math.max(assets.length, 1)) * 100),
    };
  }, [approvals, assets, audits, demoMode]);

  const handleAuditComplete = async (next: AuditResult) => {
    if (firebaseConfigured && authUser && !demoMode) {
      const approval: Approval = {
        id: `approval-${next.id}`,
        auditId: next.id,
        campaignName: next.campaignName,
        submittedBy: authUser.email ?? 'Workspace user',
        submittedAt: next.createdAt,
        riskLevel: next.riskLevel,
        status: 'pending',
        assetCount: 0,
      };
      await saveAuditSubmission(authUser.uid, next, approval);
      setApprovals((current) => [approval, ...current]);
      setAudits((current) => [next, ...current]);
    } else if (demoMode) {
      const approval: Approval = {
        id: `demo-approval-${next.id}`,
        auditId: next.id,
        campaignName: next.campaignName,
        submittedBy: 'Demo user',
        submittedAt: next.createdAt,
        riskLevel: next.riskLevel,
        status: 'pending',
        assetCount: 0,
      };
      setApprovals((current) => [approval, ...current]);
      setAudits((current) => [next, ...current]);
      addActivity({
        type: 'Campaign audit completed',
        title: next.campaignName,
        status: 'Sample',
        campaignName: next.campaignName,
      });
    }
    setAuditResult(next);
  };

  const handleFindingStatusChange = async (findingId: string, status: AuditResult['findings'][number]['status']) => {
    if (!auditResult) return;
    const updatedAudit = {
      ...auditResult,
      findings: auditResult.findings.map((finding) =>
        finding.id === findingId ? { ...finding, status } : finding,
      ),
    };
    if (firebaseConfigured && authUser && !demoMode) await saveAudit(authUser.uid, updatedAudit);
    setAuditResult(updatedAudit);
    setAudits((current) => current.map((audit) => audit.id === updatedAudit.id ? updatedAudit : audit));
  };

  const handleSettingsChange = async (next: WorkspaceSettings) => {
    if (firebaseConfigured && authUser && !demoMode) {
      try {
        await saveSettings(authUser.uid, authUser, next);
      } catch (error) {
        setToast({ kind: 'error', message: `Settings could not be saved: ${cloudErrorMessage(error)}` });
        return;
      }
    }
    setSettings(next);
  };

  const handleSignOut = async () => {
    try {
      await logout();
    } catch (error) {
      setToast({ kind: 'error', message: `Sign out failed: ${cloudErrorMessage(error)}` });
    }
  };

  const handleTryDemo = () => {
    demoPreviousState.current = { assets, guidelines, approvals, activity, settings, auditResult, audits };
    const sampleAudits = createDemoAuditHistory();
    setAssets(demoAssets.map((item) => ({ ...item, tags: [...item.tags] })));
    setGuidelines(demoGuidelines.map((item) => ({ ...item })));
    setApprovals(demoApprovals.map((item) => ({ ...item })));
    setActivity(demoActivity.map((item) => ({ ...item })));
    setSettings({ ...defaultSettings });
    setAudits(sampleAudits);
    setAuditResult(sampleAudits[0]);
    setAssetLoadError('');
    setCloudLoadError('');
    setToast(null);
    setDemoMode(true);
  };

  const handleExitDemo = () => {
    const previousState = demoPreviousState.current;
    if (previousState) {
      setAssets(previousState.assets);
      setGuidelines(previousState.guidelines);
      setApprovals(previousState.approvals);
      setActivity(previousState.activity);
      setSettings(previousState.settings);
      setAuditResult(previousState.auditResult);
      setAudits(previousState.audits);
      demoPreviousState.current = null;
    }
    setDemoMode(false);
    setToast(null);
  };

  const handleAssetStateChange: Dispatch<SetStateAction<Asset[]>> = (action) => {
    const next = typeof action === 'function' ? action(assets) : action;
    if (firebaseConfigured && authUser && !demoMode) {
      const nextById = new Map(next.map((asset) => [asset.id, asset]));
      for (const asset of assets) {
        if (!nextById.has(asset.id)) {
          void deleteAssetFromBackend(asset.id).then(() => removeAsset(authUser.uid, asset.id)).catch((error: unknown) => {
            setToast({ kind: 'error', message: `Asset could not be removed: ${cloudErrorMessage(error)}` });
          });
        }
      }
      for (const asset of next) {
        if (JSON.stringify(assets.find((item) => item.id === asset.id)) !== JSON.stringify(asset)) {
          void updateAssetInBackend(asset).catch((error: unknown) => {
            setToast({ kind: 'error', message: `Asset metadata could not be saved: ${cloudErrorMessage(error)}` });
          });
        }
      }
    }
    setAssets(next);
  };

  if (firebaseConfigState !== 'configured') {
    if (!demoMode) return <AuthScreen firebaseConfigState={firebaseConfigState} onTryDemo={handleTryDemo} />;
  }
  if (firebaseConfigured && authLoading) {
    return <LoadingScreen message="Checking your sign-in…" />;
  }
  if (firebaseConfigured && authError) {
    return <ConfigurationNotice message={authError} />;
  }
  if (!authUser && !demoMode) {
    return <AuthScreen firebaseConfigState={firebaseConfigState} onTryDemo={handleTryDemo} />;
  }
  if (firebaseConfigured && !demoMode && cloudLoading) {
    return <LoadingScreen message="Loading your secure workspace…" />;
  }
  if (firebaseConfigured && !demoMode && cloudLoadError) {
    return (
      <ConfigurationNotice
        message={`Unable to load your cloud workspace: ${cloudLoadError}`}
        actionLabel="Retry"
        onAction={() => {
          setCloudLoadError('');
          setCloudReloadKey((current) => current + 1);
        }}
      />
    );
  }
  if (firebaseConfigured && !demoMode && authUser && loadedUid !== authUser.uid) {
    return <LoadingScreen message="Loading your secure workspace…" />;
  }

  return (
    <BrowserRouter>
      <AppRouter
        assets={assets}
        approvals={approvals}
        activity={activity}
        auditResult={auditResult}
        dashboardStats={dashboardStats}
        guidelines={guidelines}
        settings={settings}
        onApprovalUpdate={handleApprovalUpdate}
        onAssetUpload={handleAssetUpload}
        onGuidelineDelete={handleGuidelineDelete}
        onGuidelineSave={handleGuidelineSave}
        onAuditComplete={handleAuditComplete}
        onResetDemo={resetDemoData}
        onSettingsChange={handleSettingsChange}
        toast={toast}
        addActivity={addActivity}
        setAssets={handleAssetStateChange}
        audits={audits}
        authUser={firebaseConfigured && !demoMode ? authUser : null}
        onSignOut={firebaseConfigured && !demoMode ? () => void handleSignOut() : undefined}
        demoMode={demoMode}
        onExitDemo={demoMode ? handleExitDemo : undefined}
        firebaseEnabled={firebaseConfigured && !demoMode}
        onSelectAudit={setAuditResult}
        onFindingStatusChange={handleFindingStatusChange}
        assetLoadError={assetLoadError}
      />
    </BrowserRouter>
  );
}

function AppRouter({
  assets,
  approvals,
  activity,
  auditResult,
  dashboardStats,
  guidelines,
  settings,
  onApprovalUpdate,
  onAssetUpload,
  onGuidelineDelete,
  onGuidelineSave,
  onAuditComplete,
  onResetDemo,
  onSettingsChange,
  toast,
  addActivity,
  setAssets,
  audits,
  authUser,
  onSignOut,
  demoMode,
  onExitDemo,
  firebaseEnabled,
  onSelectAudit,
  onFindingStatusChange,
  assetLoadError,
}: {
  assets: Asset[];
  approvals: Approval[];
  activity: ActivityEvent[];
  auditResult: AuditResult | null;
  dashboardStats: {
    totalAssets: number;
    campaignsReviewed: number;
    pendingApprovals: number;
    highRiskFindings: number;
    assetApprovalRate: number;
  };
  guidelines: BrandGuideline[];
  settings: WorkspaceSettings;
  onApprovalUpdate: (id: string, status: Approval['status'], comment?: string) => void | Promise<void>;
  onAssetUpload: (file: File) => void | Promise<void>;
  onGuidelineDelete: (id: string) => void | Promise<void>;
  onGuidelineSave: (next: BrandGuideline) => void | Promise<void>;
  onAuditComplete: (next: AuditResult) => void | Promise<void>;
  onResetDemo: () => void;
  onSettingsChange: (next: WorkspaceSettings) => void | Promise<void>;
  toast: ToastState | null;
  addActivity: (item: Omit<ActivityEvent, 'id' | 'timestamp'>) => void;
  setAssets: Dispatch<SetStateAction<Asset[]>>;
  audits: AuditResult[];
  authUser: User | null;
  onSignOut?: () => void;
  demoMode: boolean;
  onExitDemo?: () => void;
  firebaseEnabled: boolean;
  onSelectAudit: (audit: AuditResult) => void;
  onFindingStatusChange: (findingId: string, status: AuditResult['findings'][number]['status']) => Promise<void>;
  assetLoadError: string;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [search, setSearch] = useState('');

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} fixed inset-y-0 left-0 z-30 w-72 border-r border-slate-200 bg-white p-5 transition-transform md:static md:translate-x-0`}>
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm shadow-blue-200">
                <ShieldCheck size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-semibold text-slate-900">BrandGuard AI</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">2.0</span>
                </div>
              </div>
            </div>
            <button type="button" className="rounded-lg border border-slate-200 p-2 md:hidden" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
              <X size={16} />
            </button>
          </div>

          <nav className="space-y-1">
            {navItems.map(({ label, path, Icon }) => (
              <NavLink
                key={label}
                to={path}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                    isActive ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
                onClick={() => setSidebarOpen(false)}
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-8 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Sparkles size={16} className="text-blue-600" />
              {demoMode ? 'Demo workspace' : firebaseEnabled ? 'Secure workspace' : 'Demo compliance'}
            </div>
            <p className="text-sm leading-6 text-slate-600">
              {demoMode
                ? 'Sample data only. Your changes remain temporary and are not saved.'
                : firebaseEnabled
                ? 'Guidelines, audits, approvals, and activity are scoped to your account.'
                : 'Rule-based brand checks are active and saved in localStorage for this session.'}
            </p>
          </div>
        </aside>

        <div className="flex-1">
          <TopBar
            search={search}
            setSearch={setSearch}
            settings={settings}
            onSidebarToggle={() => setSidebarOpen((value) => !value)}
            userEmail={authUser?.email}
            onSignOut={onSignOut}
            demoMode={demoMode}
            onExitDemo={onExitDemo}
          />
          <main className="min-h-screen bg-slate-100 p-4 md:p-6">
            {demoMode && (
              <div role="status" className="mb-5 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-950 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-semibold">Demo workspace — sample data</p>
                  <p className="mt-1 text-sm leading-5">Changes are temporary in this browser session and are not saved to Firebase or the backend.</p>
                </div>
                <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide">Demo mode</span>
              </div>
            )}
            <Routes>
              <Route
                path="/"
                element={<DashboardPage approvals={approvals} activity={activity} dashboardStats={dashboardStats} audits={audits} firebaseEnabled={firebaseEnabled} demoMode={demoMode} />}
              />
              <Route
                path="/dashboard"
                element={<DashboardPage approvals={approvals} activity={activity} dashboardStats={dashboardStats} audits={audits} firebaseEnabled={firebaseEnabled} demoMode={demoMode} />}
              />
              <Route
                path="/assets"
                element={<AssetsPage assets={assets} setAssets={setAssets} onAssetUpload={onAssetUpload} search={search} setSearch={setSearch} assetLoadError={assetLoadError} />}
              />
              <Route
                path="/guidelines"
                element={<GuidelinesPage guidelines={guidelines} onSave={onGuidelineSave} onDelete={onGuidelineDelete} />}
              />
              <Route
                path="/reviews"
                element={<CampaignReviewPage guidelines={guidelines} onAuditComplete={onAuditComplete} addActivity={addActivity} />}
              />
              <Route
                path="/results"
                element={
                  <ReviewResultsPage
                    auditResult={auditResult}
                    audits={audits}
                    onSelectAudit={onSelectAudit}
                    onFindingStatusChange={onFindingStatusChange}
                  />
                }
              />
              <Route
                path="/approvals"
                element={<ApprovalsPage approvals={approvals} onApprovalUpdate={onApprovalUpdate} />}
              />
              <Route
                path="/activity"
                element={<ActivityPage activity={activity} />}
              />
              <Route
                path="/settings"
                element={<SettingsPage settings={settings} onChange={onSettingsChange} onResetDemo={onResetDemo} firebaseEnabled={firebaseEnabled} />}
              />
            </Routes>
          </main>
        </div>
      </div>

      {toast && (
        <div className="fixed bottom-5 right-5 z-50 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-lg">
          <div className="flex items-center gap-3">
            <div className={`rounded-full p-1.5 ${toast.kind === 'success' ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
              {toast.kind === 'success' ? <Check size={14} /> : <CircleAlert size={14} />}
            </div>
            <span className="text-sm font-medium text-slate-700">{toast.message}</span>
          </div>
        </div>
      )}

      {!sidebarOpen && (
        <button
          type="button"
          className="fixed left-4 top-4 z-40 rounded-lg border border-slate-200 bg-white p-2 shadow-sm md:hidden"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open sidebar"
        >
          <Menu size={18} />
        </button>
      )}
    </div>
  );
}

function TopBar({
  search,
  setSearch,
  settings,
  onSidebarToggle,
  userEmail,
  onSignOut,
  demoMode,
  onExitDemo,
}: {
  search: string;
  setSearch: (value: string) => void;
  settings: WorkspaceSettings;
  onSidebarToggle: () => void;
  userEmail?: string | null;
  onSignOut?: () => void;
  demoMode: boolean;
  onExitDemo?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-4 px-4 py-3 md:px-6">
        <div className="flex items-center gap-3">
          <button type="button" className="rounded-lg border border-slate-200 p-2 md:hidden" aria-label="Toggle menu" onClick={onSidebarToggle}>
            <Menu size={18} />
          </button>
          <div className="hidden items-center gap-2 text-sm text-slate-500 md:flex">
            <span>Workspace</span>
            <ChevronDown size={14} />
          </div>
        </div>

        <div className="flex flex-1 items-center justify-end gap-3">
          <label className="relative hidden w-full max-w-md md:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search campaigns, assets, and guidelines"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:bg-white"
            />
          </label>

          <button type="button" onClick={() => setSearch('approval')} className="relative rounded-xl border border-slate-200 bg-white p-2.5 text-slate-600" aria-label="Notifications">
            <Bell size={18} />
            <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-blue-600" />
          </button>

          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-2 py-1.5">
            <div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-slate-200">
              <img src={settings.logoUrl} alt="User avatar" className="h-full w-full object-cover" />
            </div>
            <div className="hidden text-left md:block">
              <div className="max-w-48 truncate text-sm font-medium text-slate-800">{userEmail ?? 'Alicia Reed'}</div>
              <div className="text-[11px] text-slate-500">{userEmail ? 'Signed in' : 'Brand lead'}</div>
            </div>
          </div>
          {demoMode && onExitDemo && (
            <button type="button" onClick={onExitDemo} className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100">
              <LogOut size={16} /><span>Exit Demo</span>
            </button>
          )}
          {onSignOut && !demoMode && (
            <button type="button" onClick={onSignOut} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50" aria-label="Sign out">
              <LogOut size={16} /><span className="hidden lg:inline">Sign out</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function DashboardPage({
  approvals,
  activity,
  dashboardStats,
  audits,
  firebaseEnabled,
  demoMode,
}: {
  approvals: Approval[];
  activity: ActivityEvent[];
  dashboardStats: {
    totalAssets: number;
    campaignsReviewed: number;
    pendingApprovals: number;
    highRiskFindings: number;
    assetApprovalRate: number;
  };
  audits: AuditResult[];
  firebaseEnabled: boolean;
  demoMode: boolean;
}) {
  const navigate = useNavigate();
  const usesAuditData = firebaseEnabled || demoMode;
  const recentReviews = approvals.slice(0, 4).map((item) => ({
    name: item.campaignName,
    assets: item.assetCount,
    riskLevel: item.riskLevel,
    date: item.submittedAt,
    status: item.status,
  }));
  const displayedRiskData = firebaseEnabled || demoMode
    ? ([
        { name: 'Low', value: audits.filter((audit) => audit.riskLevel === 'Low').length, color: '#22c55e' },
        { name: 'Medium', value: audits.filter((audit) => audit.riskLevel === 'Medium').length, color: '#f59e0b' },
        { name: 'High', value: audits.filter((audit) => audit.riskLevel === 'High').length, color: '#ef4444' },
      ] as const)
    : riskChartData;
  const displayedActivityData = firebaseEnabled || demoMode
    ? Array.from(new Set(audits.map((audit) => audit.createdAt.slice(0, 10))))
        .sort()
        .slice(-7)
        .map((date) => ({
          day: date.slice(5),
          reviews: audits.filter((audit) => audit.createdAt.slice(0, 10) === date).length,
        }))
    : activityChartData;

  const summaryCards = [
    {
      label: 'Total Assets',
      value: dashboardStats.totalAssets,
      description: `${dashboardStats.assetApprovalRate}% approved`,
      icon: FolderOpen,
      accent: 'bg-blue-100 text-blue-700',
    },
    {
      label: 'Campaigns Reviewed',
      value: dashboardStats.campaignsReviewed,
      description: demoMode ? 'Sample audit history' : firebaseEnabled ? 'Audits in your workspace' : 'Across 7 active tracks',
      icon: FileText,
      accent: 'bg-violet-100 text-violet-700',
    },
    {
      label: 'Pending Approvals',
      value: dashboardStats.pendingApprovals,
      description: 'Awaiting review decisions',
      icon: CheckCheck,
      accent: 'bg-amber-100 text-amber-700',
    },
    {
      label: 'High-Risk Findings',
      value: dashboardStats.highRiskFindings,
      description: 'Needs immediate attention',
      icon: AlertTriangle,
      accent: 'bg-red-100 text-red-700',
    },
  ];

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-slate-500">{demoMode ? 'Sample dashboard' : 'Good morning'}</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-900">Here’s your brand safety overview.</h1>
        </div>
        <div className="flex gap-3">
          <button type="button" onClick={() => navigate('/reviews')} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm shadow-blue-200 transition hover:bg-blue-500">Review Campaign</button>
          <button type="button" onClick={() => navigate('/assets')} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50">Upload Assets</button>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(({ label, value, description, icon: Icon, accent }) => (
          <StatCard key={label} label={label} value={value} description={description} accent={accent} icon={Icon} />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.8fr_1fr]">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Campaign review activity</h2>
              <p className="text-sm text-slate-500">{demoMode ? 'Sample audits grouped by date' : firebaseEnabled ? 'Audits grouped by recorded date' : 'Last 7-day performance'}</p>
            </div>
            {!usesAuditData && <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">+18.4%</span>}
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={displayedActivityData}>
                <defs>
                  <linearGradient id="fillPrimary" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#2563eb" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#2563eb" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <Tooltip />
                <Area type="monotone" dataKey="reviews" stroke="#2563eb" fill="url(#fillPrimary)" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Risk distribution</h2>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={displayedRiskData} innerRadius={46} outerRadius={72} dataKey="value" paddingAngle={2}>
                  {displayedRiskData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-2">
            {displayedRiskData.map((item) => (
              <div key={item.name} className="flex items-center justify-between text-sm text-slate-600">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.name}
                </div>
                <span className="font-medium text-slate-800">{item.value}{usesAuditData ? '' : '%'}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.8fr_1fr]">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Recent Reviews</h2>
            <button type="button" onClick={() => navigate('/results')} className="text-sm font-medium text-blue-700">View all</button>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="pb-3 font-medium">Campaign</th>
                  <th className="pb-3 font-medium">Assets</th>
                  <th className="pb-3 font-medium">Risk</th>
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentReviews.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-sm text-slate-500">No campaign audits have been submitted yet.</td>
                  </tr>
                )}
                {recentReviews.map((review) => (
                  <tr key={review.name} className="border-t border-slate-200 text-slate-700">
                    <td className="py-3 font-medium text-slate-800">{review.name}</td>
                    <td className="py-3">{review.assets}</td>
                    <td className="py-3">
                      <StatusBadge value={review.riskLevel} />
                    </td>
                    <td className="py-3">{review.date}</td>
                    <td className="py-3">
                      <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${statusStyles[review.status] || 'bg-slate-100 text-slate-700'}`}>
                        {review.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Needs Attention</h2>
            <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Live</span>
          </div>
          <div className="space-y-4">
            {activity.slice(0, 3).map((item) => (
              <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium text-slate-800">{item.title}</div>
                  <StatusBadge value={item.status === 'Completed' ? 'Low' : item.status === 'Updated' ? 'Medium' : 'High'} />
                </div>
                <div className="mt-2 text-sm text-slate-500">{item.type}</div>
              </div>
            ))}
          </div>

          <div className="mt-6 space-y-3">
            <button type="button" onClick={() => navigate('/assets')} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white"><Upload size={16} /> Upload asset</button>
            <button type="button" onClick={() => navigate('/guidelines')} className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700"><PenSquare size={16} /> Edit guidelines</button>
            <button type="button" onClick={() => navigate('/reviews')} className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700"><FileText size={16} /> Start review</button>
          </div>
        </aside>
      </section>
    </div>
  );
}

function AssetsPage({
  assets,
  setAssets,
  onAssetUpload,
  search,
  setSearch,
  assetLoadError,
}: {
  assets: Asset[];
  setAssets: Dispatch<SetStateAction<Asset[]>>;
  onAssetUpload: (file: File) => void | Promise<void>;
  search: string;
  setSearch: (value: string) => void;
  assetLoadError: string;
}) {
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [typeFilter, setTypeFilter] = useState('All');
  const [campaignFilter, setCampaignFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [sortBy, setSortBy] = useState('newest');
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [tagDraft, setTagDraft] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const uploadSelectedFile = async (file: File) => {
    setIsUploading(true);
    try {
      await onAssetUpload(file);
    } finally {
      setIsUploading(false);
    }
  };

  const filteredAssets = useMemo(() => {
    const query = search.toLowerCase();
    return [...assets]
      .filter((asset) => {
        const matchesQuery = !query || asset.title.toLowerCase().includes(query) || asset.tags.some((tag) => tag.toLowerCase().includes(query));
        const matchesType = typeFilter === 'All' || asset.fileType === typeFilter;
        const matchesCampaign = campaignFilter === 'All' || asset.campaign === campaignFilter;
        const matchesStatus = statusFilter === 'All' || asset.status === statusFilter;
        return matchesQuery && matchesType && matchesCampaign && matchesStatus;
      })
      .sort((a, b) => {
        if (sortBy === 'oldest') return new Date(a.uploadDate).getTime() - new Date(b.uploadDate).getTime();
        if (sortBy === 'alphabetical') return a.title.localeCompare(b.title);
        return new Date(b.uploadDate).getTime() - new Date(a.uploadDate).getTime();
      });
  }, [assets, campaignFilter, search, sortBy, statusFilter, typeFilter]);

  const addTag = () => {
    if (!selectedAsset || !tagDraft.trim()) return;
    const value = tagDraft.trim();
    setAssets((current) =>
      current.map((asset) =>
        asset.id === selectedAsset.id
          ? { ...asset, tags: Array.from(new Set([...asset.tags, value])) }
          : asset,
      ),
    );
    setSelectedAsset((current) => (current ? { ...current, tags: Array.from(new Set([...current.tags, value])) } : current));
    setTagDraft('');
  };

  const removeTag = (tag: string) => {
    if (!selectedAsset) return;
    const nextTags = selectedAsset.tags.filter((item) => item !== tag);
    setAssets((current) => current.map((asset) => (asset.id === selectedAsset.id ? { ...asset, tags: nextTags } : asset)));
    setSelectedAsset((current) => (current ? { ...current, tags: nextTags } : current));
  };

  const fileTypes = ['All', ...new Set(assets.map((asset) => asset.fileType))];
  const campaigns = ['All', ...new Set(assets.map((asset) => asset.campaign))];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900">Asset Library</h1>
          <p className="text-sm text-slate-500">{filteredAssets.length} total assets</p>
        </div>
        <div className="flex gap-3">
          <button type="button" disabled={isUploading} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-60" onClick={() => fileInputRef.current?.click()}>
            <Upload size={16} /> {isUploading ? 'Uploading…' : 'Upload'}
          </button>
          <input ref={fileInputRef} type="file" className="hidden" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void uploadSelectedFile(file);
            event.target.value = '';
          }} />
        </div>
      </div>

      {assetLoadError && <p role="alert" className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">{assetLoadError}</p>}

      <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full lg:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 text-sm text-slate-700 outline-none" placeholder="Search assets or tags" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={`rounded-xl border p-2 ${view === 'grid' ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`} onClick={() => setView('grid')}><Grid2x2 size={16} /></button>
            <button type="button" className={`rounded-xl border p-2 ${view === 'list' ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`} onClick={() => setView('list')}><ListFilter size={16} /></button>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
            {fileTypes.map((type) => (<option key={type} value={type}>{type}</option>))}
          </select>
          <select value={campaignFilter} onChange={(event) => setCampaignFilter(event.target.value)} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
            {campaigns.map((campaign) => (<option key={campaign} value={campaign}>{campaign}</option>))}
          </select>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
            <option value="All">All statuses</option>
            <option value="Approved">Approved</option>
            <option value="Pending">Pending</option>
            <option value="Flagged">Flagged</option>
          </select>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="alphabetical">Alphabetical</option>
          </select>
        </div>
      </div>

      {filteredAssets.length ? (
        <div className={view === 'grid' ? 'grid gap-4 md:grid-cols-2 xl:grid-cols-3' : 'space-y-3'}>
          {filteredAssets.map((asset) => (
            <div key={asset.id} className={`rounded-3xl border border-slate-200 bg-white p-4 shadow-sm ${view === 'list' ? 'flex items-center gap-4' : ''}`}>
              <div className={`${view === 'list' ? 'h-20 w-20' : 'h-40'} overflow-hidden rounded-2xl bg-slate-100`}>
                {asset.previewUrl ? (
                  <img src={asset.previewUrl} alt={asset.title} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-slate-400">
                    {asset.fileType === 'PDF' ? <FileText size={32} /> : <FileImage size={32} />}
                  </div>
                )}
              </div>

              <div className={`${view === 'list' ? 'flex-1' : 'mt-4'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-slate-900">{asset.title}</h3>
                    <p className="text-xs text-slate-500">{asset.fileType} • {asset.campaign}</p>
                  </div>
                  <StatusBadge value={asset.status} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {asset.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600">#{tag}</span>
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
                  <span>{asset.uploadDate}</span>
                  <button type="button" className="font-medium text-blue-700" onClick={() => setSelectedAsset(asset)}>View details</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">No assets match the current filters.</div>
      )}

      {selectedAsset && (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/20">
          <div className="h-full w-full max-w-md overflow-y-auto border-l border-slate-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-900">{selectedAsset.title}</h2>
              <button type="button" className="rounded-lg border border-slate-200 p-2" onClick={() => setSelectedAsset(null)}><X size={16} /></button>
            </div>

            <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
              {selectedAsset.previewUrl ? (
                <img src={selectedAsset.previewUrl} alt={selectedAsset.title} className="h-52 w-full object-cover" />
              ) : (
                <div className="flex h-52 items-center justify-center text-slate-400">
                  {selectedAsset.fileType === 'PDF' ? <FileText size={38} /> : <FileImage size={38} />}
                </div>
              )}
            </div>

            <div className="mt-5 space-y-3 text-sm text-slate-600">
              <p><span className="font-medium text-slate-800">Campaign:</span> {selectedAsset.campaign}</p>
              <p><span className="font-medium text-slate-800">Type:</span> {selectedAsset.fileType}</p>
              <p><span className="font-medium text-slate-800">Uploaded:</span> {selectedAsset.uploadDate}</p>
              <p><span className="font-medium text-slate-800">Status:</span> {selectedAsset.status}</p>
            </div>

            <div className="mt-5">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-800"><Tag size={14} /> Tags</div>
              <div className="flex flex-wrap gap-2">
                {selectedAsset.tags.map((tag) => (
                  <span key={tag} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                    #{tag}
                    <button type="button" onClick={() => removeTag(tag)} className="text-slate-400 hover:text-slate-900"><X size={12} /></button>
                  </span>
                ))}
              </div>
              <div className="mt-3 flex gap-2">
                <input value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} placeholder="Add tag" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-blue-300" />
                <button type="button" onClick={addTag} className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white">Add</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function GuidelinesPage({
  guidelines,
  onSave,
  onDelete,
}: {
  guidelines: BrandGuideline[];
  onSave: (next: BrandGuideline) => void | Promise<void>;
  onDelete: (id: string) => void | Promise<void>;
}) {
  const [selected, setSelected] = useState<BrandGuideline | null>(null);
  const [form, setForm] = useState({ category: 'Brand Overview', title: '', description: '', value: '' });
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const closeModal = () => {
    setIsModalOpen(false);
    setSelected(null);
    setSaveError('');
    setForm({ category: 'Brand Overview', title: '', description: '', value: '' });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (isSaving || !form.title.trim() || !form.value.trim()) return;
    const next: BrandGuideline = {
      id: selected?.id ?? `guideline-${Date.now()}`,
      category: form.category,
      title: form.title.trim(),
      description: form.description.trim() || 'Brand guideline',
      value: form.value.trim(),
      demo: true,
    };
    setSaveError('');
    setIsSaving(true);
    try {
      await onSave(next);
      closeModal();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Unable to save this guideline. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const grouped = useMemo(() => {
    return guidelines.reduce<Record<string, BrandGuideline[]>>((acc, item) => {
      acc[item.category] = [...(acc[item.category] || []), item];
      return acc;
    }, {});
  }, [guidelines]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900">Brand Guidelines</h1>
          <p className="text-sm text-slate-500">Demo data is stored locally and can be edited in this workspace.</p>
        </div>
        <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white" onClick={() => {
          setSelected(null);
          setForm({ category: 'Brand Overview', title: '', description: '', value: '' });
          setSaveError('');
          setIsModalOpen(true);
        }}>
          <Plus size={16} /> Add Rule
        </button>
      </div>

      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">{category}</h2>
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="font-medium text-slate-800">{item.title}</div>
                  <div className="mt-1 text-sm text-slate-500">{item.description}</div>
                  <div className="mt-2 text-sm font-medium text-slate-700">{item.value}</div>
                </div>
                <div className="flex gap-2">
                  <button type="button" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700" onClick={() => {
                    setSelected(item);
                    setForm({
                      category: item.category,
                      title: item.title,
                      description: item.description,
                      value: item.value,
                    });
                    setSaveError('');
                    setIsModalOpen(true);
                  }}>Edit</button>
                  <button
                    type="button"
                    className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700"
                    onClick={() => {
                      setDeleteError('');
                      void Promise.resolve(onDelete(item.id)).catch((error: unknown) => {
                        setDeleteError(error instanceof Error ? error.message : 'Unable to delete this guideline.');
                      });
                    }}
                  >
                    <Trash2 size={14} className="inline" /> Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {deleteError && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{deleteError}</p>}
      {guidelines.length === 0 && (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <h2 className="font-semibold text-slate-900">No guidelines yet</h2>
          <p className="mt-1 text-sm text-slate-500">Add your first rule to start checking campaign content.</p>
        </div>
      )}

      {isModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="guideline-modal-title"
            className="max-h-[calc(100dvh-2rem)] w-full max-w-2xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-5 shadow-2xl sm:p-7"
          >
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 id="guideline-modal-title" className="text-xl font-semibold text-slate-900">
                  {selected ? 'Edit Rule' : 'Add Rule'}
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selected ? 'Update this brand guideline.' : 'Create a new brand guideline.'}
                </p>
              </div>
              <button
                type="button"
                aria-label="Close dialog"
                onClick={closeModal}
                className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="grid gap-4 md:grid-cols-2">
                <select value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
                  {['Brand Overview', 'Logo and Visual Identity', 'Brand Colors', 'Typography', 'Voice and Tone', 'Approved Product Facts', 'Pricing and Offers', 'Prohibited Terms', 'Approved Claims'].map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
                <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="Rule title" aria-label="Rule title" required className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
                <div className="md:col-span-2">
                  <input value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="Description" aria-label="Description" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
                </div>
                <div className="md:col-span-2">
                  <textarea value={form.value} onChange={(event) => setForm((current) => ({ ...current, value: event.target.value }))} placeholder="Approved rule or value" aria-label="Rule text" required className="min-h-28 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
                </div>
              </div>
              {saveError && <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{saveError}</p>}
              <div className="mt-5 flex flex-col-reverse justify-end gap-3 sm:flex-row">
                <button type="button" className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700" onClick={closeModal}>Cancel</button>
                <button type="submit" disabled={isSaving} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-wait disabled:opacity-60">{isSaving ? 'Saving…' : selected ? 'Save Changes' : 'Add Rule'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

function CampaignReviewPage({
  guidelines,
  onAuditComplete,
  addActivity,
}: {
  guidelines: BrandGuideline[];
  onAuditComplete: (next: AuditResult) => void | Promise<void>;
  addActivity: (item: Omit<ActivityEvent, 'id' | 'timestamp'>) => void;
}) {
  const navigate = useNavigate();
  const [form, setForm] = useState<ReviewFormState>({
    name: 'Spring Launch',
    type: 'Social Media',
    copy: 'Launch BrandGuard AI today. Guaranteed results with no risk. 20% off until 30 November 2025. Discover the best-in-class brand protection platform.',
  });
  const [isReviewing, setIsReviewing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState('');

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.name.trim() || !form.copy.trim()) return;

    setIsReviewing(true);
    setReviewError('');
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      const result = {
        ...runDemoAudit(form.name.trim(), form.type, form.copy, guidelines),
        submittedContent: form.copy.trim(),
      };
      await onAuditComplete(result);
      addActivity({
        type: 'Campaign audit completed',
        title: form.name.trim(),
        status: 'Reviewed',
        campaignName: form.name.trim(),
      });
      navigate('/results');
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Unable to save the audit. Please try again.');
    } finally {
      setIsReviewing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Campaign Review</h1>
        <p className="text-sm text-slate-500">Run a deterministic demo brand audit against your active guidelines.</p>
      </div>

      <form onSubmit={handleSubmit} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Campaign name</label>
            <input value={form.name} required onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-blue-300" placeholder="Spring Launch" />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Campaign type</label>
            <select value={form.type} onChange={(event) => setForm((current) => ({ ...current, type: event.target.value as ReviewFormState['type'] }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-blue-300">
              <option value="Social Media">Social Media</option>
              <option value="Website">Website</option>
              <option value="Email">Email</option>
              <option value="Advertisement">Advertisement</option>
            </select>
          </div>
          <div className="lg:col-span-2">
            <label className="mb-2 block text-sm font-medium text-slate-700">Marketing copy</label>
            <textarea value={form.copy} required onChange={(event) => setForm((current) => ({ ...current, copy: event.target.value }))} className="min-h-52 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-blue-300" placeholder="Paste marketing copy here" />
          </div>
          <div className="lg:col-span-2">
            <label className="mb-2 block text-sm font-medium text-slate-700">Asset preview</label>
            <div className="flex flex-col gap-3 md:flex-row md:items-center">
              <input type="file" accept="image/*" onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) setPreviewUrl(URL.createObjectURL(file));
              }} className="block w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700" />
            </div>
            {previewUrl && <img src={previewUrl} alt="Preview" className="mt-3 h-40 w-full rounded-2xl object-cover" />}
          </div>
        </div>

        {reviewError && <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{reviewError}</p>}
        <div className="mt-5 flex justify-end">
          <button type="submit" disabled={isReviewing} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-blue-300">
            {isReviewing ? 'Running audit...' : 'Run Brand Audit'}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </div>
  );
}

function ReviewResultsPage({
  auditResult,
  audits,
  onSelectAudit,
  onFindingStatusChange,
}: {
  auditResult: AuditResult | null;
  audits: AuditResult[];
  onSelectAudit: (audit: AuditResult) => void;
  onFindingStatusChange: (findingId: string, status: AuditResult['findings'][number]['status']) => void | Promise<void>;
}) {
  const [copyStatus, setCopyStatus] = useState('');
  const [findingError, setFindingError] = useState('');
  const [savingFinding, setSavingFinding] = useState<string | null>(null);

  if (!auditResult) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
        No audit result has been saved yet. Run a campaign review to see the findings here.
      </div>
    );
  }

  const handleCopy = async () => {
    const suggestions = auditResult.findings.map((item) => item.suggestion).join('\n');
    try {
      await navigator.clipboard.writeText(suggestions);
      setCopyStatus('Copied');
    } catch {
      setCopyStatus('Clipboard unavailable');
    }
  };

  const updateFinding = async (findingId: string, status: AuditResult['findings'][number]['status']) => {
    setFindingError('');
    setSavingFinding(findingId);
    try {
      await onFindingStatusChange(findingId, status);
    } catch (error) {
      setFindingError(error instanceof Error ? error.message : 'Unable to save finding status.');
    } finally {
      setSavingFinding(null);
    }
  };

  return (
    <div className="space-y-6">
      {audits.length > 1 && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Audit history</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {audits.map((audit) => (
              <button
                type="button"
                key={audit.id}
                onClick={() => onSelectAudit(audit)}
                className={`rounded-xl border px-3 py-2 text-left text-sm ${
                  audit.id === auditResult.id ? 'border-blue-200 bg-blue-50 text-blue-800' : 'border-slate-200 bg-white text-slate-700'
                }`}
              >
                <span className="block font-medium">{audit.campaignName}</span>
                <span className="mt-0.5 block text-xs text-slate-500">{new Date(audit.createdAt).toLocaleString()}</span>
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Rule-based audit</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-900">{auditResult.campaignName}</h1>
          </div>
          <div className="rounded-2xl bg-slate-50 px-4 py-3 text-right">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Overall risk score</div>
            <div className="text-3xl font-semibold text-slate-900">{auditResult.overallScore}</div>
          </div>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-4">
          <MetricTile label="Risk category" value={auditResult.riskLevel} />
          <MetricTile label="High" value={auditResult.findings.filter((item) => item.severity === 'High').length} />
          <MetricTile label="Medium" value={auditResult.findings.filter((item) => item.severity === 'Medium').length} />
          <MetricTile label="Low" value={auditResult.findings.filter((item) => item.severity === 'Low').length} />
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Detailed findings</h2>
        {findingError && <p role="alert" className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{findingError}</p>}
        <div className="mt-4 space-y-4">
          {auditResult.findings.map((finding) => (
            <div key={finding.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <StatusBadge value={finding.severity} />
                    <span className="text-base font-semibold text-slate-900">{finding.title}</span>
                  </div>
                  <p className="mt-2 text-sm text-slate-600">{finding.description}</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" disabled={savingFinding === finding.id} onClick={() => void updateFinding(finding.id, 'Resolved')} className={`rounded-xl border px-3 py-2 text-sm font-medium ${finding.status === 'Resolved' ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-700'}`}>
                    Resolved
                  </button>
                  <button type="button" disabled={savingFinding === finding.id} onClick={() => void updateFinding(finding.id, 'Needs review')} className={`rounded-xl border px-3 py-2 text-sm font-medium ${finding.status === 'Needs review' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-slate-200 bg-white text-slate-700'}`}>
                    Needs review
                  </button>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Evidence</div>
                  <p className="mt-2 text-sm text-slate-700">{finding.evidence}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Suggested correction</div>
                  <p className="mt-2 text-sm text-slate-700">{finding.suggestion}</p>
                </div>
              </div>
              <div className="mt-4 text-sm text-slate-600">
                <span className="font-medium text-slate-800">Rule:</span> {finding.rule}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Recommendations</h2>
        <ul className="mt-4 space-y-2 text-sm text-slate-600">
          {auditResult.recommendations.map((item) => (
            <li key={item} className="flex items-start gap-2"><CheckCheck size={16} className="mt-0.5 text-blue-600" /> {item}</li>
          ))}
        </ul>
        <div className="mt-6 flex flex-wrap gap-3">
          <button type="button" onClick={handleCopy} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700"><Copy size={16} /> {copyStatus || 'Copy suggestions'}</button>
          <span className="inline-flex items-center rounded-xl bg-emerald-50 px-4 py-2.5 text-sm font-medium text-emerald-700">Audit saved to workspace</span>
        </div>
      </div>
    </div>
  );
}

function ApprovalsPage({ approvals, onApprovalUpdate }: { approvals: Approval[]; onApprovalUpdate: (id: string, status: Approval['status'], comment?: string) => void }) {
  const [tab, setTab] = useState<'All' | 'Pending' | 'Approved' | 'Rejected'>('All');
  const [query, setQuery] = useState('');
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null);
  const [comment, setComment] = useState('');

  const filtered = approvals.filter((approval) => {
    const matchesTab = tab === 'All' || approval.status === tab.toLowerCase();
    const matchesQuery = !query || approval.campaignName.toLowerCase().includes(query.toLowerCase()) || approval.submittedBy.toLowerCase().includes(query.toLowerCase());
    return matchesTab && matchesQuery;
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Approvals</h1>
        <p className="text-sm text-slate-500">Approval decisions remain human-controlled and are saved with the workspace data.</p>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">
            {['All', 'Pending', 'Approved', 'Rejected'].map((value) => (
              <button type="button" key={value} onClick={() => setTab(value as 'All' | 'Pending' | 'Approved' | 'Rejected')} className={`rounded-xl px-3 py-2 text-sm font-medium ${tab === value ? 'bg-blue-600 text-white' : 'border border-slate-200 bg-white text-slate-700'}`}>
                {value}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search approval" className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm text-slate-700 outline-none md:w-64" />
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <h2 className="font-semibold text-slate-900">No approvals to show</h2>
            <p className="mt-1 text-sm text-slate-500">Campaign audits will appear here when they are submitted for review.</p>
          </div>
        )}
        {filtered.map((approval) => (
          <div key={approval.id} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-lg font-semibold text-slate-900">{approval.campaignName}</div>
                <div className="mt-1 text-sm text-slate-500">Submitted by {approval.submittedBy} • {approval.submittedAt}</div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge value={approval.riskLevel} />
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusStyles[approval.status] || 'bg-slate-100 text-slate-700'}`}>{approval.status}</span>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700" onClick={() => setSelectedApproval(approval)}>Inspect</button>
              <button type="button" className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-medium text-white" onClick={() => onApprovalUpdate(approval.id, 'approved')}>Approve</button>
              <button type="button" className="rounded-xl bg-red-600 px-3 py-2 text-sm font-medium text-white" onClick={() => onApprovalUpdate(approval.id, 'rejected', 'Please revise the final copy and pricing details.')}>Reject</button>
              <button type="button" className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700" onClick={() => onApprovalUpdate(approval.id, 'pending', 'Revision requested by compliance team.')}>Request changes</button>
            </div>
          </div>
        ))}
      </div>

      {selectedApproval && (
        <Modal title="Approval review" onClose={() => setSelectedApproval(null)}>
          <div className="space-y-4">
            <div className="rounded-2xl bg-slate-50 p-3 text-sm text-slate-600">
              <div><span className="font-medium text-slate-800">Campaign:</span> {selectedApproval.campaignName}</div>
              <div className="mt-1"><span className="font-medium text-slate-800">Submitted by:</span> {selectedApproval.submittedBy}</div>
            </div>
            <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add a note for the review" className="min-h-24 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
            <div className="flex justify-end gap-3">
              <button type="button" className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700" onClick={() => setSelectedApproval(null)}>Close</button>
              <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white" onClick={() => { onApprovalUpdate(selectedApproval.id, 'approved', comment); setSelectedApproval(null); }}>Save decision</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ActivityPage({ activity }: { activity: ActivityEvent[] }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Activity History</h1>
        <p className="text-sm text-slate-500">Recent asset, guideline, audit, and approval activity.</p>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="pb-3 font-medium">Timestamp</th>
                <th className="pb-3 font-medium">Event</th>
                <th className="pb-3 font-medium">Campaign</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {activity.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-sm text-slate-500">No activity has been recorded yet.</td>
                </tr>
              )}
              {activity.map((event) => (
                <tr key={event.id} className="border-t border-slate-200">
                  <td className="py-3 text-slate-600">{new Date(event.timestamp).toLocaleString()}</td>
                  <td className="py-3 font-medium text-slate-800">{event.type}</td>
                  <td className="py-3 text-slate-600">{event.campaignName || 'General'}</td>
                  <td className="py-3"><span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${statusStyles[event.status.toLowerCase()] || 'bg-slate-100 text-slate-700'}`}>{event.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SettingsPage({
  settings,
  onChange,
  onResetDemo,
  firebaseEnabled,
}: {
  settings: WorkspaceSettings;
  onChange: (next: WorkspaceSettings) => void;
  onResetDemo: () => void;
  firebaseEnabled: boolean;
}) {
  const [form, setForm] = useState(settings);

  useEffect(() => {
    setForm(settings);
  }, [settings]);

  const update = (key: keyof WorkspaceSettings, value: WorkspaceSettings[keyof WorkspaceSettings]) => {
    const next = { ...form, [key]: value };
    setForm(next);
    onChange(next);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-500">Workspace profile, notifications, and review preferences.</p>
        </div>
        {!firebaseEnabled && <button type="button" onClick={onResetDemo} className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-700">Reset demo data</button>}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Workspace profile</h2>
          <div className="mt-4 space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">Workspace name</label>
              <input value={form.workspaceName} onChange={(event) => update('workspaceName', event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">Brand name</label>
              <input value={form.brandName} onChange={(event) => update('brandName', event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">Brand logo URL</label>
              <input value={form.logoUrl} onChange={(event) => update('logoUrl', event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none" />
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Notification preferences</h2>
          <div className="mt-4 space-y-4 text-sm text-slate-700">
            <ToggleRow label="Approval notifications" checked={form.notifications.approvals} onChange={(value) => update('notifications', { ...form.notifications, approvals: value })} />
            <ToggleRow label="Guideline changes" checked={form.notifications.guidelineChanges} onChange={(value) => update('notifications', { ...form.notifications, guidelineChanges: value })} />
            <ToggleRow label="Audit result alerts" checked={form.notifications.auditResults} onChange={(value) => update('notifications', { ...form.notifications, auditResults: value })} />
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2">
          <h2 className="text-lg font-semibold text-slate-900">Review preferences</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">Default risk threshold</label>
              <select value={form.reviewPreferences.defaultRiskThreshold} onChange={(event) => update('reviewPreferences', { ...form.reviewPreferences, defaultRiskThreshold: event.target.value })} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
              </select>
            </div>
            <div className="flex items-center pt-8">
              <ToggleRow label="Require manual review" checked={form.reviewPreferences.requireManualReview} onChange={(value) => update('reviewPreferences', { ...form.reviewPreferences, requireManualReview: value })} />
            </div>
            <div className="flex items-center pt-8">
              <ToggleRow label="Auto-save results" checked={form.reviewPreferences.autoSaveResults} onChange={(value) => update('reviewPreferences', { ...form.reviewPreferences, autoSaveResults: value })} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function StatCard({
  label,
  value,
  description,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number;
  description: string;
  icon: typeof FolderOpen;
  accent: string;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${accent}`}>
          <Icon size={18} />
        </div>
      </div>
      <div className="mt-5 text-sm text-slate-500">{label}</div>
      <div className="mt-2 text-3xl font-semibold text-slate-900">{value}</div>
      <div className="mt-2 text-xs text-slate-500">{description}</div>
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const tone = statusStyles[value] || 'bg-slate-100 text-slate-700';
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium ${tone}`}>{value}</span>;
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (next: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3">
      <span className="text-sm text-slate-700">{label}</span>
      <button type="button" onClick={() => onChange(!checked)} className={`relative h-6 w-11 rounded-full transition ${checked ? 'bg-blue-600' : 'bg-slate-200'}`} aria-label={label}>
        <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${checked ? 'left-6' : 'left-1'}`} />
      </button>
    </label>
  );
}

function LoadingScreen({ message }: { message: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 text-sm font-medium text-slate-700 shadow-sm">
        {message}
      </div>
    </main>
  );
}

function ConfigurationNotice({
  message,
  actionLabel,
  onAction,
}: {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <section className="w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-6 shadow-xl">
        <div className="flex items-start gap-3">
          <CircleAlert className="mt-0.5 shrink-0 text-amber-600" size={20} />
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Workspace setup needed</h1>
            <p role="alert" className="mt-2 text-sm leading-6 text-slate-600">{message}</p>
            {actionLabel && onAction && (
              <button type="button" onClick={onAction} className="mt-4 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white">
                {actionLabel}
              </button>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 p-4">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 p-2"><X size={14} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default App;
