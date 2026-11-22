import { useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, FormEvent, KeyboardEvent, ReactNode, SetStateAction } from 'react';
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
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
  BarChart3,
  Check,
  CheckCheck,
  ChevronDown,
  CircleAlert,
  Clock3,
  Copy,
  FileImage,
  FileText,
  FolderOpen,
  Grid2x2,
  History,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
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
  Video,
  X,
} from 'lucide-react';
import { defaultSettings, demoActivity, demoApprovals, demoAssets, demoGuidelines } from './data/demoData';
import { runDemoAudit } from './lib/auditEngine';
import { STORAGE_KEYS, clearStorageKey, safeReadStorage, writeStorage } from './lib/storage';
import AuthScreen from './components/AuthScreen';
import ConsistencyDashboard from './components/ConsistencyDashboard';
import GuidelineImportSection from './components/GuidelineImportSection';
import {
  acceptWorkspaceInvitation,
  assignApprovalReviewer,
  backendErrorMessage,
  deleteAssetFromBackend,
  listAssetsFromBackend,
  createWorkspace,
  inviteWorkspaceMember,
  updateWorkspaceMemberRole,
  type ApiAppRole,
  getStoredWorkspaceId,
  listWorkspaceData,
  listWorkspaceMembers,
  setActiveWorkspaceId,
  searchWorkspace,
  updateAssetInBackend,
  uploadAssetToBackend,
  listVideoReviews,
  uploadVideoForReview,
  resetDemoWorkspace,
  requestDemoToken,
  type ApiGlobalSearchResult,
  type ApiGuideline,
  type ApiWorkspace,
  type ApiWorkspaceInvitation,
  type ApiWorkspaceMember,
  type ApiVideoReview,
} from './lib/backend';
import {
  createAudit,
  loadWorkspace,
  loadWorkspaceActivity,
  listWorkspaceApprovals,
  removeGuideline,
  saveActivity,
  saveApproval,
  saveGuideline,
  updateFindingStatus,
  updateWorkspaceSettings,
  mapApiGuideline,
} from './lib/workspace';
import {
  firebaseConfigState,
  firebaseConfigured,
  listenToAuthState,
  loginWithCustomToken,
  logout,
} from './lib/firebase';
import type {
  ActivityEvent,
  Approval,
  Asset,
  AuditSubmission,
  AuditResult,
  BrandGuideline,
  WorkspaceSettings,
} from './types';

type ToastState = {
  kind: 'success' | 'error';
  message: string;
};
const demoRoleOptions: { role: ApiAppRole; label: string }[] = [
  { role: 'creator', label: 'Creator Demo' },
  { role: 'reviewer', label: 'Reviewer Demo' },
  { role: 'agency_partner', label: 'Agency Partner Demo' },
  { role: 'brand_admin', label: 'Brand Admin Demo' },
];

type GlobalSearchItem = {
  category: ApiGlobalSearchResult['category'];
  id: string;
  name: string;
  description: string;
  searchText?: string;
};

type ReviewFormState = {
  name: string;
  type: 'Social Media' | 'Website' | 'Email' | 'Advertisement';
  copy: string;
};

const navItems = [
  { label: 'Dashboard', path: '/dashboard', Icon: LayoutDashboard },
  { label: 'Asset Library', path: '/assets', Icon: FolderOpen },
  { label: 'Brand Guidelines', path: '/guidelines', Icon: ShieldCheck },
  { label: 'Campaign Review', path: '/reviews', Icon: Sparkles },
  { label: 'Video Review', path: '/video-review', Icon: Video },
  { label: 'Consistency Intelligence', path: '/consistency', Icon: BarChart3 },
  { label: 'Approvals', path: '/approvals', Icon: CheckCheck },
  { label: 'Activity History', path: '/activity', Icon: History },
  { label: 'Settings', path: '/settings', Icon: Settings },
];

const roleNavigation: Record<ApiAppRole, string[]> = {
  creator: ['/dashboard', '/assets', '/reviews', '/video-review', '/settings'],
  reviewer: ['/dashboard', '/assets', '/approvals', '/settings'],
  agency_partner: ['/dashboard', '/assets', '/reviews', '/video-review', '/settings'],
  brand_admin: navItems.map((item) => item.path),
};

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
  changes_requested: 'bg-violet-100 text-violet-700',
  updated: 'bg-sky-100 text-sky-700',
  completed: 'bg-emerald-100 text-emerald-700',
};

function App() {
  const [demoMode] = useState(false);
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
  const [isEvaluatorDemo, setIsEvaluatorDemo] = useState(false);
  const [appRole, setAppRole] = useState<ApiAppRole>(firebaseConfigured ? 'creator' : 'brand_admin');
  const [demoRoleSwitching, setDemoRoleSwitching] = useState(false);
  const [loadedWorkspaceKey, setLoadedWorkspaceKey] = useState<string | null>(null);
  const [cloudLoadError, setCloudLoadError] = useState<{ key: string; message: string } | null>(null);
  const [cloudReloadKey, setCloudReloadKey] = useState(0);
  const approvalSubmissionIds = useRef(new Set<string>());
  const [assetLoadError, setAssetLoadError] = useState('');
  const activeWorkspaceKey = authUser
    ? `${authUser.uid}:${authUser.metadata.lastSignInTime ?? ''}:${cloudReloadKey}`
    : '';
  const currentCloudLoadError =
    cloudLoadError?.key === activeWorkspaceKey ? cloudLoadError.message : '';
  const cloudLoading =
    firebaseConfigured &&
    !demoMode &&
    Boolean(authUser) &&
    loadedWorkspaceKey !== activeWorkspaceKey &&
    !currentCloudLoadError;

  useEffect(() => {
    if (!firebaseConfigured) return;
    let active = true;
    try {
      const unsubscribe = listenToAuthState(
        (user) => {
          setAppRole('creator');
          setIsEvaluatorDemo(false);
          setAuthUser(user);
          setAuthLoading(false);
          setAuthError('');
        },
        (error) => {
          setAuthError(error.message);
          setAuthLoading(false);
        },
      );
      return () => {
        active = false;
        unsubscribe();
      };
    } catch (error) {
      const message = backendErrorMessage(error);
      queueMicrotask(() => {
        if (!active) return;
        setAuthError(message);
        setAuthLoading(false);
      });
      return () => {
        active = false;
      };
    }
  }, []);

  useEffect(() => {
    if (!authUser) return;
    let active = true;
    void authUser.getIdTokenResult().then(({ claims }) => {
      if (active) setIsEvaluatorDemo(claims.brandguard_demo === true);
    }).catch((error: unknown) => {
      if (!active) return;
      setIsEvaluatorDemo(false);
      setToast({
        kind: 'error',
        message: `Demo account status could not be verified: ${backendErrorMessage(error)}`,
      });
    });

    return () => {
      active = false;
    };
  }, [authUser]);

  useEffect(() => {
    if (!firebaseConfigured || !authUser || demoMode) {
      return;
    }
    let active = true;
    void loadWorkspace().then(async (workspace) => {
      if (!active) return;
      let workspaceAssets: Asset[] = [];
      try {
        workspaceAssets = await listAssetsFromBackend();
        if (active) setAssetLoadError('');
      } catch (error) {
        if (active) setAssetLoadError(`Backend asset service unavailable: ${backendErrorMessage(error)}`);
      }
      if (!active) return;
      setAssets(workspaceAssets);
      setGuidelines(workspace.guidelines);
      setApprovals(workspace.approvals);
      setActivity(workspace.activity);
      setSettings(workspace.settings);
      setAudits(workspace.audits);
      setAuditResult(workspace.audits[0] ?? null);
      setAppRole(workspace.appRole);
      setLoadedWorkspaceKey(activeWorkspaceKey);
    }).catch((error: unknown) => {
      if (!active) return;
      setCloudLoadError({
        key: activeWorkspaceKey,
        message: backendErrorMessage(error),
      });
    });
    return () => {
      active = false;
    };
  }, [activeWorkspaceKey, authUser, cloudReloadKey, demoMode]);

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
    if (firebaseConfigured && authUser && !demoMode) {
      void saveActivity(item).then((event) => {
        setActivity((current) => [event, ...current]);
      }).catch((error: unknown) => {
        setToast({ kind: 'error', message: `Activity could not be saved: ${backendErrorMessage(error)}` });
      });
      return;
    }
    const event: ActivityEvent = {
      ...item,
      id: `event-${Date.now()}-${crypto.randomUUID()}`,
      timestamp: new Date().toISOString(),
    };
    setActivity((current) => [event, ...current]);
  };

  const handleGuidelineSave = async (next: BrandGuideline) => {
    const saved = firebaseConfigured && authUser && !demoMode ? await saveGuideline(next) : next;
    setGuidelines((current) => {
      const existing = current.some((item) => item.id === next.id);
      if (existing) {
        return current.map((item) => (item.id === next.id ? saved : item));
      }
      return [saved, ...current];
    });
    addActivity({
      type: 'Brand guideline updated',
      title: saved.title,
      status: 'Updated',
      campaignName: 'Brand Guidelines',
    });
    setToast({
      kind: 'success',
      message: demoMode ? 'Demo guideline updated in memory only; it will not be saved.' : 'Brand guideline saved.',
    });
  };

  const handleGuidelineDelete = async (id: string) => {
    const target = guidelines.find((item) => item.id === id);
    if (firebaseConfigured && authUser && !demoMode) await removeGuideline(id);
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

  const handleGuidelinesImported = async (imported: ApiGuideline[], filename: string) => {
    const mapped = imported.map(mapApiGuideline);
    setGuidelines((current) => [...mapped, ...current]);
    setToast({
      kind: 'success',
      message: `Saved ${mapped.length} approved rule${mapped.length === 1 ? '' : 's'} from ${filename}.`,
    });
  };

  const handleApprovalUpdate = async (id: string, status: Approval['status'], comment?: string): Promise<boolean> => {
    const approval = approvals.find((item) => item.id === id);
    if (!approval || approval.status !== 'pending' || approvalSubmissionIds.current.has(id)) return false;
    approvalSubmissionIds.current.add(id);
    const updatedApproval = { ...approval, status, comment: comment ?? approval.comment };
    try {
      if (firebaseConfigured && authUser && !demoMode) {
        const savedApproval = await saveApproval(updatedApproval);
        setApprovals((current) => current.map((item) => item.id === id ? savedApproval : item));
        try {
          setApprovals(await listWorkspaceApprovals());
        } catch (error) {
          setToast({
            kind: 'error',
            message: `Approval saved, but approvals could not be refreshed: ${backendErrorMessage(error)}`,
          });
          return true;
        }
      } else {
        setApprovals((current) => current.map((item) => item.id === id ? updatedApproval : item));
      }
    } catch (error) {
      setToast({ kind: 'error', message: `Approval could not be saved: ${backendErrorMessage(error)}` });
      return false;
    } finally {
      approvalSubmissionIds.current.delete(id);
    }

    let activityRefreshError = '';
    if (firebaseConfigured && authUser && !demoMode) {
      try {
        setActivity(await loadWorkspaceActivity());
      } catch (error) {
        activityRefreshError = backendErrorMessage(error);
      }
    }

    if (demoMode) {
      addActivity({
        type: status === 'approved' ? 'Campaign approved' : status === 'rejected' ? 'Campaign rejected' : 'Approval updated',
        title: approval.campaignName,
        status: status === 'approved' ? 'Approved' : status === 'rejected' ? 'Rejected' : 'Review pending',
        campaignName: approval.campaignName,
      });
    }

    setToast({
      kind: activityRefreshError ? 'error' : 'success',
      message: activityRefreshError
        ? `Approval saved, but activity could not be refreshed: ${activityRefreshError}`
        : status === 'approved'
          ? 'Campaign approved.'
          : status === 'rejected'
            ? 'Campaign rejected.'
            : 'Changes requested.',
    });
    return true;
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
        setToast({ kind: 'error', message: `Upload failed: ${backendErrorMessage(error)}` });
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
    if (firebaseConfigured && isEvaluatorDemo) {
      void resetDemoWorkspace()
        .then(() => {
          setCloudReloadKey((current) => current + 1);
          setToast({ kind: 'success', message: 'Demo workspace reset to fresh sample data.' });
        })
        .catch((error: unknown) => {
          setToast({ kind: 'error', message: backendErrorMessage(error) });
        });
      return;
    }
    if (firebaseConfigured && !demoMode) return;
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

  const handleAuditComplete = async (submission: AuditSubmission) => {
    if (firebaseConfigured && authUser && !demoMode) {
      const saved = await createAudit(submission, guidelines);
      setApprovals((current) => [saved.approval, ...current]);
      setAudits((current) => [saved.audit, ...current]);
      setAuditResult(saved.audit);
      try {
        setActivity(await loadWorkspaceActivity());
      } catch (error) {
        setToast({ kind: 'error', message: `Audit saved, but activity could not be refreshed: ${backendErrorMessage(error)}` });
      }
      return;
    }

    if (demoMode) {
      const next: AuditResult = {
        ...runDemoAudit(
          submission.campaignName,
          submission.campaignType,
          submission.submittedContent,
          guidelines,
        ),
        submittedContent: submission.submittedContent,
      };
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
      setAuditResult(next);
    }
  };

  const handleFindingStatusChange = async (findingId: string, status: AuditResult['findings'][number]['status']) => {
    if (!auditResult) return;
    const updatedAudit = firebaseConfigured && authUser && !demoMode
      ? await updateFindingStatus(auditResult.id, findingId, status, guidelines)
      : {
          ...auditResult,
          findings: auditResult.findings.map((finding) =>
            finding.id === findingId ? { ...finding, status } : finding,
          ),
        };
    setAuditResult(updatedAudit);
    setAudits((current) => current.map((audit) => audit.id === updatedAudit.id ? updatedAudit : audit));
    if (firebaseConfigured && authUser && !demoMode) {
      try {
        setActivity(await loadWorkspaceActivity());
      } catch (error) {
        setToast({ kind: 'error', message: `Finding updated, but activity could not be refreshed: ${backendErrorMessage(error)}` });
      }
    }
  };

  const handleSettingsChange = async (next: WorkspaceSettings) => {
    if (firebaseConfigured && authUser && !demoMode) {
      try {
        await updateWorkspaceSettings(next);
      } catch (error) {
        setToast({ kind: 'error', message: `Settings could not be saved: ${backendErrorMessage(error)}` });
        return;
      }
    }
    setSettings(next);
  };

  const handleDemoRoleSwitch = async (role: ApiAppRole) => {
    setDemoRoleSwitching(true);
    try {
      const customToken = await requestDemoToken(role);
      await loginWithCustomToken(customToken);
    } catch (error) {
      setToast({ kind: 'error', message: `Demo role could not be changed: ${backendErrorMessage(error)}` });
    } finally {
      setDemoRoleSwitching(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await logout();
    } catch (error) {
      setToast({ kind: 'error', message: `Sign out failed: ${backendErrorMessage(error)}` });
    }
  };

  const handleAssetStateChange: Dispatch<SetStateAction<Asset[]>> = (action) => {
    const next = typeof action === 'function' ? action(assets) : action;
    if (firebaseConfigured && authUser && !demoMode) {
      const nextById = new Map(next.map((asset) => [asset.id, asset]));
      for (const asset of assets) {
        if (!nextById.has(asset.id)) {
          void deleteAssetFromBackend(asset.id).catch((error: unknown) => {
            setToast({ kind: 'error', message: `Asset could not be removed: ${backendErrorMessage(error)}` });
          });
        }
      }
      for (const asset of next) {
        if (JSON.stringify(assets.find((item) => item.id === asset.id)) !== JSON.stringify(asset)) {
          void updateAssetInBackend(asset).catch((error: unknown) => {
            setToast({ kind: 'error', message: `Asset metadata could not be saved: ${backendErrorMessage(error)}` });
          });
        }
      }
    }
    setAssets(next);
  };

  if (firebaseConfigState !== 'configured') {
    if (!demoMode) return <AuthScreen firebaseConfigState={firebaseConfigState} />;
  }
  if (firebaseConfigured && authLoading) {
    return <LoadingScreen message="Checking your sign-in…" />;
  }
  if (firebaseConfigured && authError) {
    return <ConfigurationNotice message={authError} />;
  }
  if (!authUser && !demoMode) {
    return <AuthScreen firebaseConfigState={firebaseConfigState} />;
  }
  if (firebaseConfigured && !demoMode && cloudLoading) {
    return <LoadingScreen message="Loading your secure workspace…" />;
  }
  if (firebaseConfigured && !demoMode && currentCloudLoadError) {
    return (
      <ConfigurationNotice
        message={`Unable to load your cloud workspace: ${currentCloudLoadError}`}
        actionLabel="Retry"
        onAction={() => setCloudReloadKey((current) => current + 1)}
      />
    );
  }
  if (firebaseConfigured && !demoMode && authUser && loadedWorkspaceKey !== activeWorkspaceKey) {
    return <LoadingScreen message="Loading your secure workspace…" />;
  }

  return (
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
      onGuidelinesImported={handleGuidelinesImported}
      onAuditComplete={handleAuditComplete}
      onResetDemo={resetDemoData}
      onSettingsChange={handleSettingsChange}
      toast={toast}
      setAssets={handleAssetStateChange}
      audits={audits}
      authUser={firebaseConfigured && !demoMode ? authUser : null}
      onSignOut={firebaseConfigured && !demoMode ? () => void handleSignOut() : undefined}
      onSwitchDemoRole={isEvaluatorDemo ? (role) => void handleDemoRoleSwitch(role) : undefined}
      demoRoleSwitching={demoRoleSwitching}
      demoMode={demoMode}
      isEvaluatorDemo={isEvaluatorDemo}
      firebaseEnabled={firebaseConfigured && !demoMode}
      appRole={appRole}
      onSelectAudit={setAuditResult}
      onFindingStatusChange={handleFindingStatusChange}
      assetLoadError={assetLoadError}
    />
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
  onGuidelinesImported,
  onAuditComplete,
  onResetDemo,
  onSettingsChange,
  toast,
  setAssets,
  audits,
  authUser,
  onSignOut,
  onSwitchDemoRole,
  demoRoleSwitching,
  demoMode,
  isEvaluatorDemo,
  firebaseEnabled,
  appRole,
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
  onApprovalUpdate: (id: string, status: Approval['status'], comment?: string) => Promise<boolean>;
  onAssetUpload: (file: File) => void | Promise<void>;
  onGuidelineDelete: (id: string) => void | Promise<void>;
  onGuidelineSave: (next: BrandGuideline) => void | Promise<void>;
  onGuidelinesImported: (guidelines: ApiGuideline[], filename: string) => Promise<void>;
  onAuditComplete: (submission: AuditSubmission) => void | Promise<void>;
  onResetDemo: () => void;
  onSettingsChange: (next: WorkspaceSettings) => void | Promise<void>;
  toast: ToastState | null;
  setAssets: Dispatch<SetStateAction<Asset[]>>;
  audits: AuditResult[];
  authUser: User | null;
  onSignOut?: () => void;
  onSwitchDemoRole?: (role: ApiAppRole) => void;
  demoRoleSwitching: boolean;
  demoMode: boolean;
  isEvaluatorDemo: boolean;
  firebaseEnabled: boolean;
  appRole: ApiAppRole;
  onSelectAudit: (audit: AuditResult) => void;
  onFindingStatusChange: (findingId: string, status: AuditResult['findings'][number]['status']) => Promise<void>;
  assetLoadError: string;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedAssetSearchId, setSelectedAssetSearchId] = useState<string | null>(null);
  const [selectedGuidelineSearchId, setSelectedGuidelineSearchId] = useState<string | null>(null);
  const navigate = useNavigate();

  const localSearchItems = useMemo<GlobalSearchItem[]>(() => [
    ...audits.map((audit) => ({
      category: 'Campaign' as const,
      id: audit.id,
      name: audit.campaignName,
      description: `${audit.campaignType} campaign · ${audit.riskLevel} risk`,
      searchText: audit.submittedContent ?? '',
    })),
    ...assets.map((asset) => ({
      category: 'Asset' as const,
      id: asset.id,
      name: asset.title,
      description: [asset.campaign, ...asset.tags].filter(Boolean).join(' · '),
      searchText: `${asset.fileType} ${asset.campaign} ${asset.tags.join(' ')}`,
    })),
    ...guidelines.map((guideline) => ({
      category: 'Guideline' as const,
      id: guideline.id,
      name: guideline.title,
      description: guideline.description || guideline.category,
      searchText: `${guideline.category} ${guideline.value}`,
    })),
  ], [assets, audits, guidelines]);

  const selectSearchResult = (result: GlobalSearchItem) => {
    setSearch('');
    if (result.category === 'Campaign') {
      setSelectedAssetSearchId(null);
      setSelectedGuidelineSearchId(null);
      const auditId = result.id.startsWith('audit-') || result.id.startsWith('demo-') ? result.id : `audit-${result.id}`;
      const audit = audits.find((item) => item.id === auditId);
      if (audit) {
        onSelectAudit(audit);
        navigate('/results');
      }
      return;
    }

    if (result.category === 'Asset') {
      setSelectedGuidelineSearchId(null);
      setSelectedAssetSearchId(result.id.startsWith('asset-') ? result.id : `asset-${result.id}`);
      navigate('/assets');
      return;
    }

    setSelectedAssetSearchId(null);
    setSelectedGuidelineSearchId(result.id.startsWith('guideline-') ? result.id : `guideline-${result.id}`);
    navigate('/guidelines');
  };

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
            {navItems.filter(({ path }) => roleNavigation[appRole].includes(path)).map(({ label, path, Icon }) => (
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
            localSearchItems={localSearchItems}
            firebaseEnabled={firebaseEnabled}
            onSelectSearchResult={selectSearchResult}
            settings={settings}
            onSidebarToggle={() => setSidebarOpen((value) => !value)}
            userEmail={authUser?.email}
            onSignOut={onSignOut}
            onSwitchDemoRole={onSwitchDemoRole}
            demoRoleSwitching={demoRoleSwitching}
            appRole={appRole}
            demoMode={demoMode}
            isEvaluatorDemo={isEvaluatorDemo}
          />
          <main className="min-h-screen bg-slate-100 p-4 md:p-6">
            {(demoMode || isEvaluatorDemo) && (
              <div role="status" className="mb-5 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-950 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-semibold">Demonstration workspace — sample data</p>
                  <p className="mt-1 text-sm leading-5">
                    {isEvaluatorDemo
                      ? 'Sample records are labeled as demonstrations and belong only to this dedicated Firebase account.'
                      : 'Changes are temporary in this browser session and are not saved to Firebase or the backend.'}
                  </p>
                </div>
                <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide">DEMO MODE</span>
              </div>
            )}
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route
                path="/dashboard"
                element={<DashboardPage appRole={appRole} approvals={approvals} activity={activity} dashboardStats={dashboardStats} audits={audits} firebaseEnabled={firebaseEnabled} demoMode={demoMode} />}
              />
              <Route
                path="/assets"
                element={<AssetsPage assets={assets} setAssets={setAssets} onAssetUpload={onAssetUpload} canUploadAssets={['creator', 'agency_partner', 'brand_admin'].includes(appRole)} canManageAssets={['agency_partner', 'brand_admin'].includes(appRole)} search={search} setSearch={setSearch} assetLoadError={assetLoadError} selectedAssetSearchId={selectedAssetSearchId} onAssetSelectionChange={setSelectedAssetSearchId} />}
              />
              <Route
                path="/guidelines"
                element={appRole === 'brand_admin' ? <GuidelinesPage guidelines={guidelines} firebaseEnabled={firebaseEnabled} canManageGuidelines onSave={onGuidelineSave} onDelete={onGuidelineDelete} onImportSaved={onGuidelinesImported} selectedSearchId={selectedGuidelineSearchId} /> : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/reviews"
                element={['creator', 'agency_partner', 'brand_admin'].includes(appRole) ? <CampaignReviewPage isDemoMode={demoMode} onAuditComplete={onAuditComplete} /> : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/video-review"
                element={['creator', 'agency_partner', 'brand_admin'].includes(appRole) ? <VideoReviewPage firebaseEnabled={firebaseEnabled} /> : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/consistency"
                element={appRole === 'brand_admin' ? <ConsistencyDashboard firebaseEnabled={firebaseEnabled} /> : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/results"
                element={roleNavigation[appRole].some((path) => ['/reviews', '/approvals'].includes(path)) ? (
                  <ReviewResultsPage
                    isDemoMode={demoMode}
                    auditResult={auditResult}
                    audits={audits}
                    onSelectAudit={onSelectAudit}
                    onFindingStatusChange={onFindingStatusChange}
                  />
                ) : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/approvals"
                element={['reviewer', 'brand_admin'].includes(appRole) ? <ApprovalsPage appRole={appRole} approvals={approvals} audits={audits} onSelectAudit={onSelectAudit} onApprovalUpdate={onApprovalUpdate} /> : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/activity"
                element={appRole === 'brand_admin' ? <ActivityPage activity={activity} /> : <Navigate to="/dashboard" replace />}
              />
              <Route
                path="/settings"
                element={<SettingsPage settings={settings} onChange={onSettingsChange} onResetDemo={onResetDemo} firebaseEnabled={firebaseEnabled} appRole={appRole} />}
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
  localSearchItems,
  firebaseEnabled,
  onSelectSearchResult,
  settings,
  onSidebarToggle,
  userEmail,
  onSignOut,
  onSwitchDemoRole,
  demoRoleSwitching,
  appRole,
  demoMode,
  isEvaluatorDemo,
}: {
  search: string;
  setSearch: (value: string) => void;
  localSearchItems: GlobalSearchItem[];
  firebaseEnabled: boolean;
  onSelectSearchResult: (result: GlobalSearchItem) => void;
  settings: WorkspaceSettings;
  onSidebarToggle: () => void;
  userEmail?: string | null;
  onSignOut?: () => void;
  onSwitchDemoRole?: (role: ApiAppRole) => void;
  demoRoleSwitching: boolean;
  appRole: ApiAppRole;
  demoMode: boolean;
  isEvaluatorDemo: boolean;
}) {
  const [results, setResults] = useState<GlobalSearchItem[]>([]);
  const [searchState, setSearchState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [completedQuery, setCompletedQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [activeResultIndex, setActiveResultIndex] = useState(-1);
  const [retrySearch, setRetrySearch] = useState(0);
  const [searchError, setSearchError] = useState('');
  const searchContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const query = search.trim();
    if (!query) return;

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const runSearch = async () => {
        try {
          const matches = firebaseEnabled
            ? (await searchWorkspace(query, controller.signal)).map((item) => ({
                ...item,
                id: String(item.id),
              }))
            : localSearchItems
                .filter((item) => `${item.name} ${item.description} ${item.searchText ?? ''}`.toLowerCase().includes(query.toLowerCase()))
                .slice(0, 15);
          if (!controller.signal.aborted) {
            setResults(matches);
            setSearchState('ready');
            setCompletedQuery(query);
          }
        } catch (error) {
          if (!controller.signal.aborted) {
            setSearchError(backendErrorMessage(error));
            setSearchState('error');
            setCompletedQuery(query);
          }
        }
      };
      void runSearch();
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [firebaseEnabled, localSearchItems, retrySearch, search]);

  useEffect(() => {
    if (!isSearchOpen) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (event.target instanceof Node && !searchContainerRef.current?.contains(event.target)) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => document.removeEventListener('mousedown', closeOnOutsideClick);
  }, [isSearchOpen]);

  const selectResult = (result: GlobalSearchItem) => {
    setIsSearchOpen(false);
    setActiveResultIndex(-1);
    onSelectSearchResult(result);
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setIsSearchOpen(false);
      return;
    }
    if (event.key === 'ArrowDown' && results.length) {
      event.preventDefault();
      setIsSearchOpen(true);
      setActiveResultIndex((current) => (current + 1) % results.length);
    } else if (event.key === 'ArrowUp' && results.length) {
      event.preventDefault();
      setIsSearchOpen(true);
      setActiveResultIndex((current) => (current <= 0 ? results.length - 1 : current - 1));
    } else if (event.key === 'Enter' && activeResultIndex >= 0) {
      event.preventDefault();
      selectResult(results[activeResultIndex]);
    }
  };
  const currentSearchState = !search.trim()
    ? 'idle'
    : completedQuery !== search.trim()
      ? 'loading'
      : searchState;

  return (
    <header className={`sticky top-0 ${isSearchOpen ? 'z-[70]' : 'z-20'} border-b border-slate-200 bg-white/90 backdrop-blur-sm`}>
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
          <div ref={searchContainerRef} className="relative hidden w-full max-w-md md:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setIsSearchOpen(true);
                setActiveResultIndex(-1);
              }}
              onFocus={() => {
                if (search.trim()) setIsSearchOpen(true);
              }}
              onKeyDown={handleSearchKeyDown}
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={isSearchOpen && Boolean(search.trim())}
              aria-controls="global-search-results"
              aria-activedescendant={activeResultIndex >= 0 ? `global-search-result-${activeResultIndex}` : undefined}
              placeholder="Search campaigns, assets, and guidelines"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:bg-white"
            />
            {isSearchOpen && search.trim() && (
              <div id="global-search-results" role="listbox" className="absolute left-0 right-0 top-full z-50 mt-2 max-h-96 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-xl">
                {currentSearchState === 'loading' && (
                  <div role="status" className="flex items-center gap-2 px-3 py-3 text-sm text-slate-500">
                    <LoaderCircle size={16} className="animate-spin" /> Searching…
                  </div>
                )}
                {currentSearchState === 'error' && (
                  <div className="px-3 py-3 text-sm text-red-700">
                    <p role="alert">Search failed. {searchError}</p>
                    <button type="button" className="mt-2 font-medium text-blue-700 hover:text-blue-800" onClick={() => {
                      setSearchState('loading');
                      setRetrySearch((value) => value + 1);
                    }}>
                      Try again
                    </button>
                  </div>
                )}
                {currentSearchState === 'ready' && results.length === 0 && (
                  <p className="px-3 py-3 text-sm text-slate-500">No matching results found</p>
                )}
                {currentSearchState === 'ready' && results.map((result, index) => (
                  <button
                    key={`${result.category}-${result.id}`}
                    id={`global-search-result-${index}`}
                    type="button"
                    role="option"
                    aria-selected={activeResultIndex === index}
                    className={`block w-full rounded-xl px-3 py-2.5 text-left ${activeResultIndex === index ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setActiveResultIndex(index)}
                    onClick={() => selectResult(result)}
                  >
                    <span className="block text-[11px] font-semibold uppercase tracking-wide text-blue-700">{result.category}</span>
                    <span className="mt-0.5 block truncate text-sm font-medium text-slate-800">{result.name}</span>
                    <span className="mt-0.5 block truncate text-xs text-slate-500">{result.description}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

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
          {isEvaluatorDemo && onSwitchDemoRole && (
            <label className="rounded-xl border border-amber-200 bg-amber-50 px-2 py-1.5 text-sm text-amber-900">
              <span className="sr-only">Switch demo role</span>
              <select
                aria-label="Switch demo role"
                value={appRole}
                disabled={demoRoleSwitching}
                onChange={(event) => {
                  const role = demoRoleOptions.find((option) => option.role === event.target.value)?.role;
                  if (role && role !== appRole) onSwitchDemoRole(role);
                }}
                className="max-w-40 bg-transparent font-medium outline-none disabled:opacity-60"
              >
                {demoRoleOptions.map(({ role, label }) => <option key={role} value={role}>{label}</option>)}
              </select>
            </label>
          )}
          {isEvaluatorDemo && onSignOut && (
            <button type="button" onClick={onSignOut} className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100" aria-label="Sign out of demo account">
              <LogOut size={16} /><span className="hidden lg:inline">Exit Demo</span>
            </button>
          )}
          {onSignOut && !demoMode && !isEvaluatorDemo && (
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
  appRole,
  approvals,
  activity,
  dashboardStats,
  audits,
  firebaseEnabled,
  demoMode,
}: {
  appRole: ApiAppRole;
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
  const recentReviews = ['reviewer', 'brand_admin'].includes(appRole)
    ? approvals.slice(0, 4).map((item) => ({
        name: item.campaignName,
        assets: item.assetCount,
        riskLevel: item.riskLevel,
        date: item.submittedAt,
        status: item.status,
      }))
    : audits.slice(0, 4).map((item) => ({
        name: item.campaignName,
        assets: 0,
        riskLevel: item.riskLevel,
        date: item.createdAt,
        status: 'pending',
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
  const visibleSummaryCards = summaryCards.filter(({ label }) => {
    if (appRole === 'creator') return label !== 'Pending Approvals';
    if (appRole === 'reviewer') return label !== 'Total Assets';
    if (appRole === 'agency_partner') return label !== 'Pending Approvals';
    return true;
  });
  const dashboardTitle: Record<ApiAppRole, string> = {
    creator: 'Your campaign audit workspace.',
    reviewer: 'Your review queue and decisions.',
    agency_partner: 'Your client campaign workspaces.',
    brand_admin: 'Your brand and workspace overview.',
  };
  const canSubmit = ['creator', 'agency_partner', 'brand_admin'].includes(appRole);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-slate-500">{demoMode ? 'Sample dashboard' : appRole.replace('_', ' ')}</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-900">{dashboardTitle[appRole]}</h1>
        </div>
        <div className="flex gap-3">
          {canSubmit ? (
            <>
              <button type="button" onClick={() => navigate('/reviews')} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm shadow-blue-200 transition hover:bg-blue-500">Review Campaign</button>
              <button type="button" onClick={() => navigate('/assets')} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50">Upload Assets</button>
            </>
          ) : (
            <button type="button" onClick={() => navigate('/approvals')} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm shadow-blue-200 transition hover:bg-blue-500">Open review queue</button>
          )}
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {visibleSummaryCards.map(({ label, value, description, icon: Icon, accent }) => (
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
            {canSubmit ? (
              <>
                <button type="button" onClick={() => navigate('/assets')} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white"><Upload size={16} /> Upload asset</button>
                {appRole === 'brand_admin' && <button type="button" onClick={() => navigate('/guidelines')} className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700"><PenSquare size={16} /> Edit guidelines</button>}
                <button type="button" onClick={() => navigate('/reviews')} className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700"><FileText size={16} /> Start review</button>
              </>
            ) : (
              <button type="button" onClick={() => navigate('/approvals')} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white"><CheckCheck size={16} /> Review submissions</button>
            )}
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
  canUploadAssets,
  canManageAssets,
  search,
  setSearch,
  assetLoadError,
  selectedAssetSearchId,
  onAssetSelectionChange,
}: {
  assets: Asset[];
  setAssets: Dispatch<SetStateAction<Asset[]>>;
  onAssetUpload: (file: File) => void | Promise<void>;
  canUploadAssets: boolean;
  canManageAssets: boolean;
  search: string;
  setSearch: (value: string) => void;
  assetLoadError: string;
  selectedAssetSearchId: string | null;
  onAssetSelectionChange: (id: string | null) => void;
}) {
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [typeFilter, setTypeFilter] = useState('All');
  const [campaignFilter, setCampaignFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [sortBy, setSortBy] = useState('newest');
  const [tagDraft, setTagDraft] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const selectedAsset = assets.find((item) => item.id === selectedAssetSearchId) ?? null;

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
    setTagDraft('');
  };

  const removeTag = (tag: string) => {
    if (!selectedAsset) return;
    const nextTags = selectedAsset.tags.filter((item) => item !== tag);
    setAssets((current) => current.map((asset) => (asset.id === selectedAsset.id ? { ...asset, tags: nextTags } : asset)));
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
        {canUploadAssets && <div className="flex gap-3">
          <button type="button" disabled={isUploading} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-60" onClick={() => fileInputRef.current?.click()}>
            <Upload size={16} /> {isUploading ? 'Uploading…' : 'Upload'}
          </button>
          <input ref={fileInputRef} type="file" className="hidden" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void uploadSelectedFile(file);
            event.target.value = '';
          }} />
        </div>}
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
                  <button type="button" className="font-medium text-blue-700" onClick={() => onAssetSelectionChange(asset.id)}>View details</button>
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
              <button type="button" className="rounded-lg border border-slate-200 p-2" onClick={() => onAssetSelectionChange(null)}><X size={16} /></button>
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
                  {canManageAssets && <button type="button" onClick={() => removeTag(tag)} className="text-slate-400 hover:text-slate-900"><X size={12} /></button>}
                  </span>
                ))}
              </div>
              {canManageAssets && <div className="mt-3 flex gap-2">
                <input value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} placeholder="Add tag" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-blue-300" />
                <button type="button" onClick={addTag} className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white">Add</button>
              </div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function GuidelinesPage({
  guidelines,
  firebaseEnabled,
  canManageGuidelines,
  onSave,
  onDelete,
  onImportSaved,
  selectedSearchId,
}: {
  guidelines: BrandGuideline[];
  firebaseEnabled: boolean;
  canManageGuidelines: boolean;
  onSave: (next: BrandGuideline) => void | Promise<void>;
  onDelete: (id: string) => void | Promise<void>;
  onImportSaved: (guidelines: ApiGuideline[], filename: string) => Promise<void>;
  selectedSearchId: string | null;
}) {
  const [selected, setSelected] = useState<BrandGuideline | null>(null);
  const [form, setForm] = useState({
    category: 'Brand Overview',
    title: '',
    description: '',
    value: '',
    requirementType: 'guidance' as NonNullable<BrandGuideline['requirementType']>,
  });
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!selectedSearchId) return;
    const guideline = guidelines.find((item) => item.id === selectedSearchId);
    if (!guideline) return;
    const timeout = window.setTimeout(() => {
      document.getElementById(`guideline-item-${guideline.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);
    return () => window.clearTimeout(timeout);
  }, [guidelines, selectedSearchId]);

  const closeModal = () => {
    setIsModalOpen(false);
    setSelected(null);
    setSaveError('');
    setForm({ category: 'Brand Overview', title: '', description: '', value: '', requirementType: 'guidance' });
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
      requirementType: form.requirementType,
      demo: true,
      sourceDocumentId: selected?.sourceDocumentId,
      sourceReference: selected?.sourceReference,
      sourceExcerpt: selected?.sourceExcerpt,
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
          <p className="text-sm text-slate-500">Manage active brand rules and import documented company policies.</p>
        </div>
        {canManageGuidelines && <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white" onClick={() => {
          setSelected(null);
          setForm({ category: 'Brand Overview', title: '', description: '', value: '', requirementType: 'guidance' });
          setSaveError('');
          setIsModalOpen(true);
        }}>
          <Plus size={16} /> Add Rule
        </button>}
      </div>

      {canManageGuidelines
        ? <GuidelineImportSection firebaseEnabled={firebaseEnabled} onSaved={onImportSaved} />
        : <p className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">Approved company rules are shared in this workspace. Contact a workspace owner or admin to request changes.</p>}

      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">{category}</h2>
          <div className="space-y-3">
            {items.map((item) => (
              <div
                key={item.id}
                id={`guideline-item-${item.id}`}
                className={`flex flex-col gap-3 rounded-2xl border p-4 md:flex-row md:items-center md:justify-between ${
                  selectedSearchId === item.id ? 'border-blue-300 bg-blue-50 ring-2 ring-blue-100' : 'border-slate-200 bg-slate-50'
                }`}
              >
                <div>
                  <div className="font-medium text-slate-800">{item.title}</div>
                  <div className="mt-1 text-sm text-slate-500">{item.description}</div>
                  <div className="mt-2 text-sm font-medium text-slate-700">{item.value}</div>
                  {item.sourceReference && (
                    <div className="mt-2 text-xs text-blue-800">
                      Imported from {item.sourceReference}
                      {item.sourceExcerpt ? ` · “${item.sourceExcerpt}”` : ''}
                    </div>
                  )}
                </div>
                {canManageGuidelines && <div className="flex gap-2">
                  <button type="button" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700" onClick={() => {
                    setSelected(item);
                    setForm({
                      category: item.category,
                      title: item.title,
                      description: item.description,
                      value: item.value,
                      requirementType: item.requirementType ?? 'guidance',
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
                </div>}
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
                  {['Company Identity', 'Brand Overview', 'Logo Usage', 'Logo and Visual Identity', 'Brand Colors', 'Typography', 'Tone of Voice', 'Voice and Tone', 'Approved Terminology', 'Approved Product Facts', 'Prohibited Terminology', 'Prohibited Terms', 'Pricing Rules', 'Pricing and Offers', 'Marketing Claims', 'Approved Claims', 'Image and Visual Guidelines', 'Social Media Guidelines', 'Other Company Policies'].map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
                <select value={form.requirementType} onChange={(event) => setForm((current) => ({ ...current, requirementType: event.target.value as NonNullable<BrandGuideline['requirementType']> }))} aria-label="Rule requirement status" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none">
                  <option value="guidance">Guidance</option>
                  <option value="required">Required</option>
                  <option value="prohibited">Prohibited</option>
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
  isDemoMode,
  onAuditComplete,
}: {
  isDemoMode: boolean;
  onAuditComplete: (submission: AuditSubmission) => void | Promise<void>;
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
      await onAuditComplete({
        campaignName: form.name.trim(),
        campaignType: form.type,
        submittedContent: form.copy.trim(),
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
        <p className="text-sm text-slate-500">
          {isDemoMode
            ? 'Sample rule checks run in this temporary demo; results are not saved to your account.'
            : 'Check campaign text against your saved brand guidelines. When configured, campaign text and active rules are sent to the selected Gemini or Groq provider; otherwise only local deterministic checks run.'}
        </p>
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
            <label className="mb-2 block text-sm font-medium text-slate-700">Campaign text</label>
            <textarea value={form.copy} required onChange={(event) => setForm((current) => ({ ...current, copy: event.target.value }))} className="min-h-52 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-blue-300" placeholder="Paste marketing copy here" />
          </div>
          <div className="lg:col-span-2">
            <label className="mb-2 block text-sm font-medium text-slate-700">Optional image preview (not analyzed)</label>
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
            {isReviewing ? 'Running guideline audit…' : 'Run Brand Audit'}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </div>
  );
}

function VideoReviewPage({ firebaseEnabled }: { firebaseEnabled: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const [reviews, setReviews] = useState<ApiVideoReview[]>([]);
  const [selectedReview, setSelectedReview] = useState<ApiVideoReview | null>(null);
  const [loading, setLoading] = useState(firebaseEnabled);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [progressMessage, setProgressMessage] = useState('');
  const submissionInProgressRef = useRef(false);

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  useEffect(() => {
    if (!firebaseEnabled) return;
    let active = true;
    listVideoReviews()
      .then((items) => {
        if (active) {
          setReviews(items);
          setSelectedReview(items[0] ?? null);
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(`Video reviews could not be loaded: ${backendErrorMessage(loadError)}`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [firebaseEnabled]);

  const submitReview = async (selectedFile: File, isRetry = false) => {
    if (submissionInProgressRef.current || !firebaseEnabled) return;
    submissionInProgressRef.current = true;
    setUploading(true);
    setError('');
    setSuccess('');
    setProgressMessage(
      isRetry
        ? 'Retrying analysis with the selected video. The active AI provider applies its configured recovery policy.'
        : 'Uploading the video and analyzing sampled frames. Temporary provider failures may be retried automatically.',
    );
    try {
      const review = await uploadVideoForReview(selectedFile);
      setReviews((current) => [review, ...current]);
      setSelectedReview(review);
      setSuccess(
        review.fallback_used
          ? `Analysis completed and saved for ${review.original_filename} using backup model ${review.model_used}.`
          : `Analysis completed and saved for ${review.original_filename} using ${review.model_used ?? 'Gemini'}.`,
      );
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
      setPreviewUrl(null);
      setFile(null);
    } catch (uploadError) {
      const detail = backendErrorMessage(uploadError);
      const dailyQuotaExhausted = /daily.*quota|quota.*daily/i.test(detail);
      const temporaryProviderFailure = /HTTP 50[0234]|UNAVAILABLE|overload|high demand|temporarily unavailable|remained unavailable|rate limits persisted/i.test(detail);
      setError(
        dailyQuotaExhausted
          ? `The selected AI provider's daily request quota is exhausted. Wait until its quota resets, then retry; your selected video is still available and no review was saved. ${detail}`
          : temporaryProviderFailure
            ? `The selected AI provider is temporarily overloaded or unavailable. Analysis failed without saving a review. ${detail}`
            : `Analysis failed without saving a review. ${detail}`,
      );
      setSuccess('');
    } finally {
      submissionInProgressRef.current = false;
      setUploading(false);
      setProgressMessage('');
    }
  };

  const handleUpload = (event: FormEvent) => {
    event.preventDefault();
    if (file) void submitReview(file);
  };

  const formatDuration = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remaining = Math.floor(seconds % 60);
    return `${minutes}:${String(remaining).padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-700">Creative quality</p>
          <h1 className="text-3xl font-semibold text-slate-900">Video Review</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Review sampled frames for visual consistency and clearly legible on-screen text against your saved brand guidelines.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
          <Clock3 size={15} className="text-blue-700" />
          Up to 50 MB · 3 minutes · 12 sampled frames
        </div>
      </div>

      {!firebaseEnabled && (
        <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Video reviews require an authenticated workspace and the FastAPI backend. They are unavailable in demo mode.
        </div>
      )}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="font-semibold text-slate-900">New review</h2>
            <p className="mt-1 text-sm text-slate-500">MP4, MOV, M4V, AVI, or WebM</p>
          </div>
          <form onSubmit={handleUpload} className="space-y-4 p-5" aria-busy={uploading}>
            <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center transition hover:border-blue-400 hover:bg-blue-50/40">
              <Video size={25} className="mb-3 text-blue-700" />
              <span className="text-sm font-medium text-slate-800">{file?.name ?? 'Choose a video to review'}</span>
              <span className="mt-1 text-xs text-slate-500">Maximum file size 50 MB</span>
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/x-m4v,video/x-msvideo,video/webm,.m4v,.avi"
                className="sr-only"
                disabled={!firebaseEnabled || uploading}
                onChange={(event) => {
                  const nextFile = event.target.files?.[0] ?? null;
                  if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
                  previewUrlRef.current = nextFile ? URL.createObjectURL(nextFile) : null;
                  setFile(nextFile);
                  setPreviewUrl(previewUrlRef.current);
                  setError('');
                }}
              />
            </label>
            {previewUrl && <video src={previewUrl} controls className="max-h-72 w-full rounded-lg bg-slate-950" />}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <p className="max-w-md text-xs leading-5 text-slate-500">
                Only sampled frames are analyzed. Text and captions are checked only when legible in a sampled frame; audio transcription is not supported.
              </p>
              <button
                type="submit"
                disabled={!file || !firebaseEnabled || uploading}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {uploading ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
                {uploading ? 'Uploading and analyzing…' : 'Review video'}
              </button>
            </div>
            {uploading && (
              <p role="status" aria-live="polite" className="text-sm text-blue-800">
                {progressMessage}
              </p>
            )}
          </form>
          {success && <p role="status" className="mx-5 mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">{success}</p>}
          {error && (
            <div className="mx-5 mb-5 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-800">
              <p role="alert">{error}</p>
              {file && firebaseEnabled && (
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => void submitReview(file, true)}
                  className="mt-2 rounded-md border border-red-300 bg-white px-3 py-1.5 font-medium text-red-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {/daily.*quota|quota.*daily/i.test(error) ? 'Retry after quota reset' : 'Retry Analysis'}
                </button>
              )}
            </div>
          )}
        </section>

        <section className="min-w-0 rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="font-semibold text-slate-900">Review results</h2>
            <p className="mt-1 text-sm text-slate-500">Timestamped observations from sampled frames and legible on-screen text</p>
          </div>
          {loading ? (
            <div className="flex items-center gap-2 p-6 text-sm text-slate-500"><LoaderCircle size={16} className="animate-spin" /> Loading review history…</div>
          ) : selectedReview ? (
            <div>
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-900">{selectedReview.original_filename}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {formatDuration(selectedReview.duration_seconds)} · {selectedReview.frame_count} frames · {new Date(selectedReview.created_at).toLocaleString()}
                  </p>
                </div>
                {selectedReview.analysis_mode === 'demo_sample' ? (
                  <span className="shrink-0 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900">
                    Demonstration sample · not AI analyzed
                  </span>
                ) : (
                  <span className="shrink-0 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800">
                    Analysis completed · {selectedReview.model_used ?? 'Gemini'}
                    {selectedReview.fallback_used ? ' backup model' : ''}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-3 gap-px border-b border-slate-100 bg-slate-100">
                <div className="bg-white px-4 py-3">
                  <p className="text-[11px] font-medium uppercase text-slate-500">Compliance</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">{selectedReview.compliance_score}%</p>
                </div>
                <div className="bg-white px-4 py-3">
                  <p className="text-[11px] font-medium uppercase text-slate-500">Risk score</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">{selectedReview.risk_score}<span className="text-xs font-normal text-slate-500"> / 100</span></p>
                </div>
                <div className="bg-white px-4 py-3">
                  <p className="text-[11px] font-medium uppercase text-slate-500">Risk level</p>
                  <p className={`mt-1 text-base font-semibold capitalize ${selectedReview.risk_category === 'high' ? 'text-red-700' : selectedReview.risk_category === 'medium' ? 'text-amber-700' : 'text-emerald-700'}`}>{selectedReview.risk_category}</p>
                </div>
              </div>
              <p className="border-b border-slate-100 px-5 py-2 text-xs text-slate-500">
                {selectedReview.analysis_mode === 'demo_sample'
                  ? 'Illustrative demonstration scores only; this sample is not a real video analysis.'
                  : 'Risk score is severity-weighted from returned findings (Low 10, Medium 20, High 35), capped at 100. It is not a confidence score.'}
              </p>
              {selectedReview.findings.length ? (
                <ul className="divide-y divide-slate-100">
                  {selectedReview.findings.map((finding, index) => (
                    <li key={`${finding.timestamp_seconds}-${index}`} className="space-y-2 px-5 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-slate-100 px-2 py-1 font-mono text-xs font-semibold text-slate-700">{finding.timestamp}</span>
                        <span className={`rounded px-2 py-1 text-xs font-semibold ${finding.severity === 'high' ? 'bg-red-50 text-red-700' : finding.severity === 'medium' ? 'bg-amber-50 text-amber-800' : 'bg-sky-50 text-sky-800'}`}>
                          {finding.severity.toUpperCase()}
                        </span>
                        <span className="text-xs capitalize text-slate-500">{finding.category.replaceAll('_', ' ')}</span>
                      </div>
                      <h3 className="text-sm font-semibold text-slate-900">{finding.title}</h3>
                      <p className="text-sm leading-5 text-slate-600">{finding.evidence} {finding.explanation}</p>
                      <p className="border-l-2 border-blue-600 pl-3 text-sm leading-5 text-slate-700">{finding.suggested_correction}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-5 py-8 text-sm text-slate-600">No specific brand issues were identified in the sampled frames.</p>
              )}
              {reviews.length > 1 && (
                <div className="border-t border-slate-200 px-5 py-3">
                  <label className="sr-only" htmlFor="video-review-history">Select a previous video review</label>
                  <select
                    id="video-review-history"
                    value={selectedReview.id}
                    onChange={(event) => setSelectedReview(reviews.find((review) => review.id === Number(event.target.value)) ?? null)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                  >
                    {reviews.map((review) => <option key={review.id} value={review.id}>{review.original_filename} · {new Date(review.created_at).toLocaleDateString()}</option>)}
                  </select>
                </div>
              )}
            </div>
          ) : (
            <div className="px-5 py-10 text-center">
              <Video size={24} className="mx-auto mb-3 text-slate-400" />
              <p className="text-sm font-medium text-slate-800">No video reviews yet</p>
              <p className="mt-1 text-sm text-slate-500">Your completed reviews will appear here.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ReviewResultsPage({
  isDemoMode,
  auditResult,
  audits,
  onSelectAudit,
  onFindingStatusChange,
}: {
  isDemoMode: boolean;
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
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
              {auditResult.analysisMode === 'gemini_assisted'
                ? 'Gemini-assisted, evidence-validated audit'
                : auditResult.analysisMode === 'groq_assisted'
                  ? 'Groq-assisted, evidence-validated audit'
                : isDemoMode
                  ? 'Sample rule-based audit'
                  : 'Evidence-based rule audit'}
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-900">{auditResult.campaignName}</h1>
          </div>
          <div className="rounded-2xl bg-slate-50 px-4 py-3 text-right">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{isDemoMode ? 'Sample demo score' : 'Overall risk score / 100'}</div>
            <div className="text-3xl font-semibold text-slate-900">{auditResult.overallScore}</div>
          </div>
        </div>
        <p className="mt-3 text-sm text-slate-500">
          {isDemoMode
            ? 'Sample rule checks only; these demo results are temporary and do not represent an AI confidence score.'
            : auditResult.analysisMode === 'gemini_assisted' || auditResult.analysisMode === 'groq_assisted'
              ? `${auditResult.analysisMode === 'groq_assisted' ? 'Groq' : 'Gemini'}-assisted analysis; each AI finding is checked against an exact text excerpt and an active guideline. A human reviewer should confirm context. The risk score is not a model confidence score.`
              : 'No live AI provider analysis was used. Deterministic text checks only. The risk score adds 10 for each Low, 20 for each Medium, and 35 for each High finding, capped at 100; it is not an AI confidence score.'}
        </p>

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
          {auditResult.findings.length === 0 && (
            <p role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              No configured text rules were triggered. This does not certify claims or evaluate visual assets; complete a human review before publication.
            </p>
          )}
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

function ApprovalsPage({ appRole, approvals, audits, onSelectAudit, onApprovalUpdate }: {
  appRole: ApiAppRole;
  approvals: Approval[];
  audits: AuditResult[];
  onSelectAudit: (audit: AuditResult) => void;
  onApprovalUpdate: (id: string, status: Approval['status'], comment?: string) => Promise<boolean>;
}) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'All' | 'Pending' | 'Approved' | 'Rejected' | 'Changes requested'>('All');
  const [query, setQuery] = useState('');
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null);
  const [comment, setComment] = useState('');
  const [savingApprovalId, setSavingApprovalId] = useState<string | null>(null);
  const [reviewers, setReviewers] = useState<ApiWorkspaceMember[]>([]);
  const [assignedReviewerIds, setAssignedReviewerIds] = useState<Record<string, string>>({});
  const [assignmentError, setAssignmentError] = useState('');

  useEffect(() => {
    if (appRole !== 'brand_admin') return;
    const workspaceId = getStoredWorkspaceId();
    if (!workspaceId) return;
    void listWorkspaceMembers(workspaceId).then((members) => {
      setReviewers(members.filter((member) => member.app_role === 'reviewer'));
      setAssignmentError('');
    }).catch((error: unknown) => {
      setAssignmentError(backendErrorMessage(error));
    });
  }, [appRole]);

  const filtered = approvals.filter((approval) => {
    const matchesTab = tab === 'All' ||
      approval.status === (tab === 'Changes requested' ? 'changes_requested' : tab.toLowerCase());
    const matchesQuery = !query || approval.campaignName.toLowerCase().includes(query.toLowerCase()) || approval.submittedBy.toLowerCase().includes(query.toLowerCase());
    return matchesTab && matchesQuery;
  });

  const updateApproval = async (approval: Approval, decision: Approval['status'], note?: string) => {
    if (savingApprovalId || approval.status !== 'pending') return;
    setSavingApprovalId(approval.id);
    try {
      const saved = await onApprovalUpdate(approval.id, decision, note);
      if (saved && selectedApproval?.id === approval.id) {
        setSelectedApproval(null);
        setComment('');
      }
    } finally {
      setSavingApprovalId(null);
    }
  };

  const assignReviewer = async (approval: Approval, reviewerUserId: string) => {
    setAssignmentError('');
    try {
      await assignApprovalReviewer(Number(approval.id), reviewerUserId || null);
      setAssignedReviewerIds((current) => ({ ...current, [approval.id]: reviewerUserId }));
    } catch (error) {
      setAssignmentError(backendErrorMessage(error));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Approvals</h1>
        <p className="text-sm text-slate-500">Approval decisions remain human-controlled and are saved with the workspace data.</p>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">
            {['All', 'Pending', 'Approved', 'Rejected', 'Changes requested'].map((value) => (
              <button type="button" key={value} onClick={() => setTab(value as 'All' | 'Pending' | 'Approved' | 'Rejected' | 'Changes requested')} className={`rounded-xl px-3 py-2 text-sm font-medium ${tab === value ? 'bg-blue-600 text-white' : 'border border-slate-200 bg-white text-slate-700'}`}>
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
        {assignmentError && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{assignmentError}</p>}
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
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusStyles[approval.status] || 'bg-slate-100 text-slate-700'}`}>{approval.status.replace('_', ' ')}</span>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {appRole === 'brand_admin' && (
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  Assign reviewer
                  <select
                    aria-label={`Assign reviewer for ${approval.campaignName}`}
                    value={assignedReviewerIds[approval.id] ?? approval.assignedReviewerUid ?? ''}
                    onChange={(event) => void assignReviewer(approval, event.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-2"
                  >
                    <option value="">Unassigned</option>
                    {reviewers.map((reviewer) => (
                      <option key={reviewer.user_id} value={reviewer.user_id}>{reviewer.email || reviewer.user_id}</option>
                    ))}
                  </select>
                </label>
              )}
              <button
                type="button"
                disabled={!audits.some((audit) => audit.id === approval.auditId)}
                className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 disabled:opacity-50"
                onClick={() => {
                  const audit = audits.find((item) => item.id === approval.auditId);
                  if (!audit) return;
                  onSelectAudit(audit);
                  navigate('/results');
                }}
              >
                Review findings
              </button>
              <button type="button" className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700" onClick={() => setSelectedApproval(approval)}>Inspect</button>
              {approval.status === 'pending' && <>
                <button type="button" disabled={savingApprovalId !== null} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => void updateApproval(approval, 'approved')}>Approve</button>
                <button type="button" disabled={savingApprovalId !== null} className="rounded-xl bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => void updateApproval(approval, 'rejected', 'Please revise the final copy and pricing details.')}>Reject</button>
                <button type="button" disabled={savingApprovalId !== null} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => void updateApproval(approval, 'changes_requested', 'Revision requested by compliance team.')}>Request changes</button>
              </>}
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
              <button type="button" disabled={savingApprovalId !== null} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-50" onClick={() => setSelectedApproval(null)}>Close</button>
              {selectedApproval.status === 'pending' && <button type="button" disabled={savingApprovalId !== null} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => void updateApproval(selectedApproval, 'approved', comment)}>Approve</button>}
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

function WorkspaceSharingSection() {
  const [workspaces, setWorkspaces] = useState<ApiWorkspace[]>([]);
  const [invitations, setInvitations] = useState<ApiWorkspaceInvitation[]>([]);
  const [members, setMembers] = useState<ApiWorkspaceMember[]>([]);
  const [selectedId, setSelectedId] = useState(() => getStoredWorkspaceId() ?? '');
  const [workspaceName, setWorkspaceName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteAppRole, setInviteAppRole] = useState<ApiAppRole>('creator');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const selected = workspaces.find((item) => item.id === selectedId);
  const canManage = selected?.app_role === 'brand_admin';

  const refresh = async (preferredId?: string) => {
    const workspaceData = await listWorkspaceData();
    const items = workspaceData.workspaces;
    setInvitations(workspaceData.pending_invitations);
    setWorkspaces(items);
    const activeId = preferredId ?? items.find((item) => item.id === selectedId)?.id ?? items[0]?.id ?? '';
    setSelectedId(activeId);
    const active = items.find((item) => item.id === activeId);
    if (active?.app_role === 'brand_admin') setMembers(await listWorkspaceMembers(activeId));
    else setMembers([]);
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const workspaceData = await listWorkspaceData();
        const items = workspaceData.workspaces;
        const selectedWorkspace = items.find((item) => item.id === getStoredWorkspaceId()) ?? items[0];
        if (!active) return;
        setWorkspaces(items);
        setInvitations(workspaceData.pending_invitations);
        setSelectedId(selectedWorkspace?.id ?? '');
        if (selectedWorkspace?.app_role === 'brand_admin') {
          const workspaceMembers = await listWorkspaceMembers(selectedWorkspace.id);
          if (active) setMembers(workspaceMembers);
        } else {
          setMembers([]);
        }
      } catch (loadError) {
        if (active) setError(backendErrorMessage(loadError));
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const switchWorkspace = (workspaceId: string) => {
    setActiveWorkspaceId(workspaceId);
    window.location.reload();
  };

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const workspace = await createWorkspace(workspaceName);
      setWorkspaceName('');
      setNotice('Workspace created. Invite verified company accounts to share approved guidelines.');
      setActiveWorkspaceId(workspace.id);
      window.location.reload();
    } catch (createError) {
      setError(backendErrorMessage(createError));
    } finally {
      setBusy(false);
    }
  };

  const submitInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canManage) return;
    setBusy(true);
    setError('');
    try {
      const membershipRole = inviteAppRole === 'brand_admin' ? 'admin' : 'member';
      await inviteWorkspaceMember(selected.id, inviteEmail, membershipRole, inviteAppRole);
      setInviteEmail('');
      setNotice('Invitation recorded. The recipient must sign in with this verified email to join.');
    } catch (inviteError) {
      setError(backendErrorMessage(inviteError));
    } finally {
      setBusy(false);
    }
  };

  const changeMemberRole = async (member: ApiWorkspaceMember, appRole: ApiAppRole) => {
    if (!selected || !canManage) return;
    setBusy(true);
    setError('');
    try {
      await updateWorkspaceMemberRole(selected.id, member.user_id, appRole);
      await refresh(selected.id);
      setNotice('Workspace role updated.');
    } catch (roleError) {
      setError(backendErrorMessage(roleError));
    } finally {
      setBusy(false);
    }
  };

  const acceptInvitation = async (invitationId: string) => {
    setBusy(true);
    setError('');
    try {
      await acceptWorkspaceInvitation(invitationId);
      await refresh();
      setNotice('Workspace invitation accepted.');
    } catch (acceptError) {
      setError(backendErrorMessage(acceptError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Company workspace access</h2>
      <p className="mt-1 text-sm text-slate-600">Share approved guidelines with explicitly invited members. Each workspace remains isolated.</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="mt-3 text-sm text-emerald-700">{notice}</p>}
      {invitations.length > 0 && (
        <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50 p-3">
          <h3 className="text-sm font-semibold text-slate-800">Workspace invitations</h3>
          {invitations.map((invitation) => (
            <div key={invitation.id} className="mt-2 flex items-center justify-between gap-3 text-sm">
              <span>{invitation.workspace_name} · {invitation.role}</span>
              <button
                type="button"
                disabled={busy}
                onClick={() => void acceptInvitation(invitation.id)}
                className="rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white disabled:opacity-50"
              >
                Accept
              </button>
            </div>
          ))}
          <p className="mt-2 text-xs text-slate-600">Only invitations matching your verified Firebase email are shown.</p>
        </div>
      )}
      <div className="mt-4">
        <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="active-workspace">Active workspace</label>
        <select
          id="active-workspace"
          value={selectedId}
          onChange={(event) => switchWorkspace(event.target.value)}
          className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm"
        >
          {workspaces.map((workspace) => (
            <option value={workspace.id} key={workspace.id}>{workspace.name} · {workspace.app_role.replace('_', ' ')}</option>
          ))}
        </select>
      </div>
      {selected && (
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-slate-800">Members</h3>
          <ul className="mt-2 space-y-2 text-sm text-slate-600">
            {members.map((member) => (
              <li key={member.user_id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                <span className="min-w-0 truncate">{member.email || member.user_id}</span>
                {canManage ? (
                  <select
                    aria-label={`Role for ${member.email || member.user_id}`}
                    value={member.app_role}
                    disabled={busy || member.role === 'owner'}
                    onChange={(event) => void changeMemberRole(member, event.target.value as ApiAppRole)}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs capitalize"
                  >
                    <option value="creator">Creator</option>
                    <option value="reviewer">Reviewer</option>
                    <option value="agency_partner">Agency Partner</option>
                    {selected?.role === 'owner' && <option value="brand_admin">Brand Admin</option>}
                  </select>
                ) : <span className="capitalize">{member.app_role.replace('_', ' ')}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {selected && canManage && (
        <form onSubmit={submitInvite} className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
          <input
            type="email"
            required
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
            placeholder="Company member email"
            aria-label="Company member email"
            className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm"
          />
          <select
            aria-label="Invitation role"
            value={inviteAppRole}
            onChange={(event) => setInviteAppRole(event.target.value as ApiAppRole)}
            className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm"
          >
            <option value="creator">Creator</option>
            <option value="reviewer">Reviewer</option>
            <option value="agency_partner">Agency Partner</option>
            {selected.role === 'owner' && <option value="brand_admin">Brand Admin</option>}
          </select>
          <button disabled={busy} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">Invite</button>
        </form>
      )}
      {canManage && <form onSubmit={submitCreate} className="mt-5 flex gap-3">
        <input
          required
          minLength={2}
          maxLength={120}
          value={workspaceName}
          onChange={(event) => setWorkspaceName(event.target.value)}
          placeholder="New company workspace name"
          aria-label="New workspace name"
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2.5 text-sm"
        />
        <button disabled={busy} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-50">Create workspace</button>
      </form>}
    </section>
  );
}

function SettingsPage({
  settings,
  onChange,
  onResetDemo,
  firebaseEnabled,
  appRole,
}: {
  settings: WorkspaceSettings;
  onChange: (next: WorkspaceSettings) => void;
  onResetDemo: () => void;
  firebaseEnabled: boolean;
  appRole: ApiAppRole;
}) {
  const [form, setForm] = useState(settings);

  const update = (key: keyof WorkspaceSettings, value: WorkspaceSettings[keyof WorkspaceSettings]) => {
    const next = { ...form, [key]: value };
    setForm(next);
    onChange(next);
  };

  return (
    <div className="space-y-6">
      {firebaseEnabled && <WorkspaceSharingSection />}
      {appRole === 'agency_partner' && (
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h1 className="text-xl font-semibold text-slate-900">Client workspaces</h1>
          <p className="mt-1 text-sm text-slate-600">Switch between workspaces assigned to your agency or accept a verified invitation above.</p>
        </div>
      )}
      {appRole === 'brand_admin' && <>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-500">Workspace profile, notifications, and review preferences.</p>
        </div>
        {!firebaseEnabled && <button type="button" onClick={() => {
          onResetDemo();
          setForm(defaultSettings);
        }} className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-700">Reset demo data</button>}
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
      </>}
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
            <h1 className="text-lg font-semibold text-slate-900">Application data unavailable</h1>
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
