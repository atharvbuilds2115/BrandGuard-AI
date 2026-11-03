import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  Check,
  CircleAlert,
  Clock3,
  LoaderCircle,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  backendErrorMessage,
  createConsistencyReport,
  listCompletedAudits,
  listConsistencyReports,
  type ApiAudit,
  type ApiConsistencyReport,
} from '../lib/backend';

const severityColors = { high: '#dc2626', medium: '#d97706', low: '#0284c7' };

function complianceScore(riskScore: number): number {
  return 100 - Math.max(0, Math.min(100, riskScore));
}

export default function ConsistencyDashboard({ firebaseEnabled }: { firebaseEnabled: boolean }) {
  const [audits, setAudits] = useState<ApiAudit[]>([]);
  const [reports, setReports] = useState<ApiConsistencyReport[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedReport, setSelectedReport] = useState<ApiConsistencyReport | null>(null);
  const [loading, setLoading] = useState(firebaseEnabled);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!firebaseEnabled) return;
    let active = true;
    Promise.all([listCompletedAudits(), listConsistencyReports()])
      .then(([auditRecords, reportRecords]) => {
        if (!active) return;
        const completed = auditRecords.filter((audit) => audit.audit_status.toLowerCase() === 'completed');
        setAudits(completed);
        setSelectedIds(completed.slice(0, 50).map((audit) => audit.id));
        setReports(reportRecords);
        setSelectedReport(reportRecords[0] ?? null);
        setError('');
      })
      .catch((loadError: unknown) => {
        if (active) setError(`Consistency data could not be loaded: ${backendErrorMessage(loadError)}`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [firebaseEnabled, reloadKey]);

  const toggleAudit = (auditId: number) => {
    setSuccess('');
    if (selectedIds.includes(auditId)) {
      setSelectedIds((current) => current.filter((id) => id !== auditId));
      return;
    }
    if (selectedIds.length >= 50) {
      setError('A comparison can include at most 50 campaigns.');
      return;
    }
    setSelectedIds((current) => current.includes(auditId) ? current : [...current, auditId]);
  };

  const handleGenerate = async () => {
    if (selectedIds.length < 2) return;
    setGenerating(true);
    setError('');
    setSuccess('');
    try {
      const report = await createConsistencyReport(selectedIds);
      setReports((current) => [report, ...current]);
      setSelectedReport(report);
      setSuccess(`Comparison saved for ${report.campaign_count} campaigns.`);
    } catch (generationError) {
      setError(backendErrorMessage(generationError));
    } finally {
      setGenerating(false);
    }
  };

  const formatDate = (value: string) => new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  if (!firebaseEnabled) {
    return (
      <div className="space-y-4">
        <PageHeading />
        <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
          Cross-campaign reports use saved, authenticated audit history and are unavailable in demo mode.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeading />

      {error && (
        <div role="alert" className="flex items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <span className="flex items-start gap-2"><CircleAlert size={17} className="mt-0.5 shrink-0" />{error}</span>
          <button type="button" className="shrink-0 rounded p-1 hover:bg-red-100" onClick={() => {
            setLoading(true);
            setReloadKey((key) => key + 1);
          }} aria-label="Retry loading consistency reports" title="Retry">
            <RefreshCw size={15} />
          </button>
        </div>
      )}
      {success && <div role="status" className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><Check size={16} />{success}</div>}

      <section className="grid items-start gap-5 xl:grid-cols-[minmax(320px,0.82fr)_minmax(0,1.5fr)]">
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <div>
              <h2 className="font-semibold text-slate-900">Select campaign audits</h2>
              <p className="mt-1 text-xs text-slate-500">Completed audits only · up to 50 per report</p>
            </div>
            <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">{selectedIds.length} selected</span>
          </div>
          {loading ? (
            <div className="flex items-center gap-2 px-5 py-8 text-sm text-slate-500"><LoaderCircle size={16} className="animate-spin" /> Loading saved audits…</div>
          ) : audits.length < 2 ? (
            <div className="px-5 py-8 text-sm text-slate-600">
              <p className="font-medium text-slate-800">More campaign history needed</p>
              <p className="mt-1">At least two completed audits are required to compare consistency.</p>
            </div>
          ) : (
            <div className="max-h-[520px] divide-y divide-slate-100 overflow-y-auto">
              {audits.map((audit) => {
                const checked = selectedIds.includes(audit.id);
                const score = complianceScore(audit.risk_score);
                const severityCounts = audit.findings.reduce((counts, finding) => {
                  const severity = finding.severity.toLowerCase();
                  if (severity in counts) counts[severity as keyof typeof counts] += 1;
                  return counts;
                }, { high: 0, medium: 0, low: 0 });
                return (
                  <label key={audit.id} className={`block cursor-pointer px-5 py-4 transition hover:bg-slate-50 ${checked ? 'bg-blue-50/50' : ''}`}>
                    <div className="flex items-start gap-3">
                      <input type="checkbox" checked={checked} onChange={() => toggleAudit(audit.id)} className="mt-1 h-4 w-4 accent-blue-700" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-900">{audit.campaign_name}</p>
                            <p className="mt-0.5 text-xs text-slate-500">{audit.campaign_type} · {formatDate(audit.created_at)}</p>
                          </div>
                          <span className={`rounded px-2 py-1 text-xs font-semibold capitalize ${audit.risk_category === 'high' ? 'bg-red-50 text-red-700' : audit.risk_category === 'medium' ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'}`}>
                            {audit.risk_category} risk
                          </span>
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-3 text-xs">
                          <span className="font-medium text-slate-700">Compliance {score}% <span className="font-normal text-slate-500">· Risk {audit.risk_score}</span></span>
                          <span className="flex gap-2" aria-label={`${severityCounts.high} high, ${severityCounts.medium} medium, ${severityCounts.low} low severity findings`}>
                            <span className="text-red-700">H {severityCounts.high}</span>
                            <span className="text-amber-700">M {severityCounts.medium}</span>
                            <span className="text-sky-700">L {severityCounts.low}</span>
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-label={`Compliance score ${score}%`}>
                          <div className="h-full rounded-full bg-emerald-600" style={{ width: `${score}%` }} />
                        </div>
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          )}
          <div className="border-t border-slate-200 p-4">
            <button
              type="button"
              onClick={() => void handleGenerate()}
              disabled={loading || generating || selectedIds.length < 2}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {generating ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
              {generating ? 'Comparing saved audits…' : 'Generate comparison'}
            </button>
          </div>
        </div>

        <div className="space-y-5">
          {loading ? (
            <div className="flex min-h-48 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white text-sm text-slate-500"><LoaderCircle size={17} className="animate-spin" /> Loading report history…</div>
          ) : selectedReport ? (
            <ReportView report={selectedReport} reports={reports} onSelect={setSelectedReport} formatDate={formatDate} />
          ) : (
            <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 text-center">
              <BarChart3 size={27} className="mb-3 text-slate-400" />
              <p className="text-sm font-semibold text-slate-800">No comparison reports yet</p>
              <p className="mt-1 max-w-sm text-sm text-slate-500">Select at least two completed campaign audits to create your first evidence-based comparison.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function PageHeading() {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-700">Brand intelligence</p>
        <h1 className="text-3xl font-semibold text-slate-900">Cross-campaign consistency</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-500">Compare saved audit evidence, find repeated guideline violations, and track risk across campaigns.</p>
      </div>
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"><Clock3 size={15} className="text-blue-700" />Saved reports are immutable snapshots</div>
    </header>
  );
}

function ReportView({
  report,
  reports,
  onSelect,
  formatDate,
}: {
  report: ApiConsistencyReport;
  reports: ApiConsistencyReport[];
  onSelect: (report: ApiConsistencyReport) => void;
  formatDate: (value: string) => string;
}) {
  const data = report.report_data;
  const riskTrend = data.risk_trends.map((item) => ({
    ...item,
    label: item.campaign_name.length > 14 ? `${item.campaign_name.slice(0, 12)}…` : item.campaign_name,
  }));
  return (
    <div className="space-y-5">
      {reports.length > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
          <label htmlFor="consistency-history" className="text-sm font-medium text-slate-700">Report history</label>
          <select
            id="consistency-history"
            value={report.id}
            onChange={(event) => {
              const next = reports.find((item) => item.id === Number(event.target.value));
              if (next) onSelect(next);
            }}
            className="max-w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
          >
            {reports.map((item) => <option key={item.id} value={item.id}>{formatDate(item.created_at)} · {item.campaign_count} campaigns</option>)}
          </select>
        </div>
      )}

      {data.demonstration_note && (
        <p role="note" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          {data.demonstration_note}
        </p>
      )}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Campaigns compared" value={report.campaign_count} detail={`Saved ${formatDate(report.created_at)}`} />
        <Metric label="Average compliance" value={`${data.average_compliance_score}%`} detail="100 minus saved risk score" />
        <Metric label="Average risk" value={data.average_risk_score} detail="Penalty score, 0 to 100" />
        <Metric label="Recurring violations" value={data.recurring_violations.length} detail="Found across 2+ campaigns" />
      </section>

      <section className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-slate-900">Compliance by campaign</h2>
            <p className="mt-1 text-xs text-slate-500">Derived consistently from the stored risk penalty</p>
          </div>
          <div className="h-56 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.campaigns} margin={{ top: 8, right: 6, left: -20, bottom: 8 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="campaign_name" tick={{ fontSize: 10 }} interval={0} angle={-18} textAnchor="end" height={48} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(value) => [`${value}%`, 'Compliance']} />
                <Bar dataKey="compliance_score" name="Compliance" radius={[4, 4, 0, 0]}>
                  {data.campaigns.map((campaign) => <Cell key={campaign.audit_id} fill={campaign.compliance_score >= 70 ? '#059669' : campaign.compliance_score >= 40 ? '#d97706' : '#dc2626'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-slate-900">Risk trend</h2>
            <p className="mt-1 text-xs text-slate-500">Campaigns ordered by their original audit date</p>
          </div>
          <div className="h-56 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={riskTrend} margin={{ top: 8, right: 12, left: -20, bottom: 8 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Tooltip labelFormatter={(_label, items) => items[0]?.payload.campaign_name ?? ''} />
                <Line type="monotone" dataKey="risk_score" name="Risk score" stroke="#dc2626" strokeWidth={2.5} dot={{ r: 4, fill: '#dc2626' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Campaign comparison</h2>
          <p className="mt-1 text-xs text-slate-500">Scores, risk, and saved finding severity by campaign</p>
        </div>
        <div className="grid gap-px bg-slate-100 sm:grid-cols-2 2xl:grid-cols-3">
          {data.campaigns.map((campaign) => (
            <article key={campaign.audit_id} className="min-w-0 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-semibold text-slate-900">{campaign.campaign_name}</h3>
                  <p className="mt-1 text-xs text-slate-500">{campaign.campaign_type} · {formatDate(campaign.audited_at)}</p>
                </div>
                <span className={`shrink-0 rounded px-2 py-1 text-xs font-semibold capitalize ${campaign.risk_category === 'high' ? 'bg-red-50 text-red-700' : campaign.risk_category === 'medium' ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'}`}>{campaign.risk_category} risk</span>
              </div>
              <div className="mt-4 flex items-end justify-between">
                <span className="text-2xl font-semibold text-slate-900">{campaign.compliance_score}%</span>
                <span className="text-xs text-slate-500">Risk score {campaign.risk_score}</span>
              </div>
              <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-emerald-600" style={{ width: `${campaign.compliance_score}%` }} />
              </div>
              <div className="mt-3 flex flex-wrap gap-3 text-xs">
                <span className="text-red-700">High {campaign.severity_counts.high}</span>
                <span className="text-amber-700">Medium {campaign.severity_counts.medium}</span>
                <span className="text-sky-700">Low {campaign.severity_counts.low}</span>
                <span className="ml-auto text-slate-500">{campaign.finding_count} findings</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="grid items-start gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Recurring violations</h2>
            <p className="mt-1 text-xs text-slate-500">Saved guideline or finding repeats across multiple campaigns</p>
          </div>
          {data.recurring_violations.length ? (
            <ul className="divide-y divide-slate-100">
              {data.recurring_violations.map((violation) => (
                <li key={`${violation.guideline_id ?? violation.guideline_name}-${violation.area}`} className="space-y-3 px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{violation.guideline_name}</p>
                      <p className="mt-1 text-xs capitalize text-slate-500">{violation.area} · {violation.campaign_count} campaigns · {violation.occurrence_count} findings</p>
                    </div>
                    <SeveritySummary counts={violation.severity_counts} />
                  </div>
                  <div className="space-y-2">
                    {violation.occurrences.slice(0, 3).map((occurrence) => (
                      <div key={`${occurrence.audit_id}-${occurrence.title}`} className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
                        <p className="mb-1 font-medium text-slate-800">{occurrence.campaign_name} · {occurrence.severity}</p>
                        <p>{occurrence.evidence}</p>
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-7 text-sm text-slate-600">No saved guideline violation repeats across these campaigns.</p>
          )}
        </div>

        <div className="space-y-5">
          <div className="rounded-xl border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-900">Most frequently violated guidelines</h2>
              <p className="mt-1 text-xs text-slate-500">Ranked from findings attached to saved guidelines</p>
            </div>
            {data.frequently_violated_guidelines.length ? (
              <ol className="divide-y divide-slate-100">
                {data.frequently_violated_guidelines.slice(0, 5).map((guideline, index) => (
                  <li key={guideline.guideline_id} className="flex items-center gap-3 px-5 py-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">{index + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-slate-800">{guideline.guideline_name}</p>
                      <p className="text-xs text-slate-500">{guideline.campaign_count} campaigns · {guideline.finding_count} findings</p>
                    </div>
                    <SeveritySummary counts={guideline.severity_counts} />
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 py-6 text-sm text-slate-600">No saved findings reference a user-owned guideline.</p>
            )}
          </div>

          <div className="rounded-xl border border-blue-200 bg-blue-50/60">
            <div className="flex items-center gap-2 border-b border-blue-100 px-5 py-4">
              <Sparkles size={16} className="text-blue-700" />
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Evidence-based recommendations</h2>
                <p className="mt-1 text-xs text-slate-600">Actions reuse corrections from your saved findings</p>
              </div>
            </div>
            {data.recommendations.length ? (
              <ol className="space-y-3 p-5">
                {data.recommendations.map((recommendation, index) => (
                  <li key={`${recommendation.guideline_name}-${index}`} className="flex gap-3 text-sm text-slate-700">
                    <span className="mt-0.5 text-xs font-semibold text-blue-800">{String(index + 1).padStart(2, '0')}</span>
                    <div>
                      <p className="font-medium text-slate-900">{recommendation.action}</p>
                      <p className="mt-1 text-xs text-slate-600">{recommendation.guideline_name} · based on {recommendation.based_on_findings} findings across {recommendation.campaign_count} campaigns</p>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 py-6 text-sm text-slate-600">There are no evidence-backed corrections to recommend in this report.</p>
            )}
          </div>
        </div>
      </section>

      {!!data.consistency_areas.length && (
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle size={17} className="text-amber-700" />
            <h2 className="text-sm font-semibold text-slate-900">Observed consistency areas</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {data.consistency_areas.map((area) => (
              <article key={area.area} className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold capitalize text-slate-800">{area.area}</h3>
                  <span className="text-xs text-slate-500">{area.campaign_count} campaigns</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{area.finding_count} saved findings</p>
                {area.evidence[0] && <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600">{area.evidence[0].evidence}</p>}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-white px-4 py-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-2 truncate text-2xl font-semibold text-slate-900">{value}</p>
      <p className="mt-1 truncate text-xs text-slate-500">{detail}</p>
    </div>
  );
}

function SeveritySummary({ counts }: { counts: Record<'high' | 'medium' | 'low', number> }) {
  return (
    <span className="flex shrink-0 gap-1.5 text-[10px] font-semibold">
      {(['high', 'medium', 'low'] as const).map((severity) => (
        <span key={severity} style={{ color: severityColors[severity] }}>{severity[0].toUpperCase()} {counts[severity]}</span>
      ))}
    </span>
  );
}