import { useRef, useState, type DragEvent } from 'react';
import { AlertCircle, Check, FileText, LoaderCircle, Sparkles, Upload, X } from 'lucide-react';
import {
  backendErrorMessage,
  extractGuidelineDocument,
  saveGuidelineImport,
  type ApiExtractedGuidelineRule,
  type ApiGuideline,
  type ApiGuidelineExtraction,
} from '../lib/backend';

type ReviewRule = ApiExtractedGuidelineRule & {
  decision: 'pending' | 'approved' | 'rejected';
};

const CATEGORY_OPTIONS = [
  ['company_identity', 'Company Identity'],
  ['logo_usage', 'Logo Usage'],
  ['brand_colors', 'Brand Colors'],
  ['typography', 'Typography'],
  ['tone_of_voice', 'Tone of Voice'],
  ['approved_terminology', 'Approved Terminology'],
  ['prohibited_terminology', 'Prohibited Terminology'],
  ['pricing_rules', 'Pricing Rules'],
  ['marketing_claims', 'Marketing Claims'],
  ['image_visual_guidelines', 'Image and Visual Guidelines'],
  ['social_media_guidelines', 'Social Media Guidelines'],
  ['other_company_policies', 'Other Company Policies'],
] as const;

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = /\.(pdf|docx|txt)$/i;

export default function GuidelineImportSection({
  firebaseEnabled,
  onSaved,
}: {
  firebaseEnabled: boolean;
  onSaved: (guidelines: ApiGuideline[], filename: string) => Promise<void>;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const actionInProgress = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [extraction, setExtraction] = useState<ApiGuidelineExtraction | null>(null);
  const [rules, setRules] = useState<ReviewRule[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const clearImport = () => {
    setFile(null);
    setExtraction(null);
    setRules([]);
    setUploadProgress(0);
    setError('');
    setNotice('');
    if (fileInput.current) fileInput.current.value = '';
  };

  const selectFile = (nextFile: File | undefined) => {
    if (isExtracting || isSaving) return;
    setError('');
    setNotice('');
    setExtraction(null);
    setRules([]);
    if (!nextFile) return;
    if (!ALLOWED_EXTENSIONS.test(nextFile.name)) {
      setFile(null);
      setError('Choose a PDF, DOCX, or TXT file.');
      return;
    }
    if (nextFile.size > MAX_FILE_BYTES) {
      setFile(null);
      setError('Guideline documents must be 10 MB or smaller.');
      return;
    }
    if (!nextFile.size) {
      setFile(null);
      setError('The selected guideline document is empty.');
      return;
    }
    setFile(nextFile);
    setUploadProgress(0);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (isExtracting || isSaving) return;
    selectFile(event.dataTransfer.files[0]);
  };

  const extractRules = async () => {
    if (!file || !firebaseEnabled || actionInProgress.current) return;
    actionInProgress.current = true;
    setIsExtracting(true);
    setError('');
    setNotice('');
    setUploadProgress(0);
    try {
      const result = await extractGuidelineDocument(file, setUploadProgress);
      setExtraction(result);
      setRules(result.rules.map((rule) => ({
        ...rule,
        decision: 'pending' as const,
      })));
      setNotice(result.rules.length
        ? `Review the extracted rules from ${result.original_filename}. Nothing is saved until you approve and save rules.`
        : 'No explicit brand rules were found in this document.');
    } catch (extractError) {
      setError(backendErrorMessage(extractError));
    } finally {
      actionInProgress.current = false;
      setIsExtracting(false);
    }
  };

  const updateRule = (index: number, patch: Partial<ReviewRule>) => {
    setRules((current) => current.map((rule, ruleIndex) => (
      ruleIndex === index ? { ...rule, ...patch } : rule
    )));
  };

  const saveApprovedRules = async () => {
    if (!extraction || actionInProgress.current) return;
    const approvedRules = rules.filter((rule) => rule.decision === 'approved');
    if (!approvedRules.length) {
      setError('Approve at least one rule before saving.');
      return;
    }
    actionInProgress.current = true;
    setIsSaving(true);
    setError('');
    try {
      const saved = await saveGuidelineImport(extraction, approvedRules);
      await onSaved(saved.guidelines, saved.original_filename);
      setNotice(`Saved ${saved.rules_saved} approved guideline${saved.rules_saved === 1 ? '' : 's'}. Existing rules were preserved.`);
      setFile(null);
      setExtraction(null);
      setRules([]);
      setUploadProgress(0);
      if (fileInput.current) fileInput.current.value = '';
    } catch (saveError) {
      setError(backendErrorMessage(saveError));
    } finally {
      actionInProgress.current = false;
      setIsSaving(false);
    }
  };

  const allApproved = rules.length > 0 && rules.every((rule) => rule.decision === 'approved');

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-blue-700" />
            <h2 className="text-lg font-semibold text-slate-900">Import Company Guidelines</h2>
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
            Upload an official PDF, DOCX, or TXT file. The selected AI provider extracts cited rules for your review;
            nothing becomes active until you approve and save it.
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">10 MB maximum</span>
      </div>

      <div
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (event.currentTarget === event.target) setIsDragging(false);
        }}
        onDrop={handleDrop}
        className={`mt-5 rounded-2xl border border-dashed p-5 text-center transition ${
          isDragging ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-slate-50'
        }`}
      >
        <Upload size={23} className="mx-auto text-blue-700" />
        <p className="mt-2 text-sm font-medium text-slate-800">
          {file ? file.name : 'Drag and drop your guideline file here'}
        </p>
        <p className="mt-1 text-xs text-slate-500">PDF, DOCX, or TXT · Up to 10 MB</p>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
          className="sr-only"
          disabled={!firebaseEnabled || isExtracting || isSaving}
          onChange={(event) => selectFile(event.target.files?.[0])}
        />
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <button
            type="button"
            disabled={!firebaseEnabled || isExtracting || isSaving}
            onClick={() => fileInput.current?.click()}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            Upload File
          </button>
          {file && !extraction && (
            <button
              type="button"
              disabled={!firebaseEnabled || isExtracting}
              onClick={() => void extractRules()}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {isExtracting ? <LoaderCircle size={15} className="animate-spin" /> : <Sparkles size={15} />}
              {isExtracting ? 'Extracting rules…' : 'Upload and Extract Rules'}
            </button>
          )}
          {file && (
            <button
              type="button"
              disabled={isExtracting || isSaving}
              onClick={clearImport}
              className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-sm font-medium text-slate-600 hover:bg-white disabled:opacity-50"
            >
              <X size={15} /> Remove file
            </button>
          )}
        </div>
        {!firebaseEnabled && <p className="mt-3 text-xs text-amber-800">Sign in to an authenticated workspace to import guidelines.</p>}
      </div>

      {isExtracting && (
        <div className="mt-4 space-y-2" role="status" aria-live="polite">
          <div className="flex items-center justify-between text-xs text-slate-600">
            <span>{uploadProgress < 100 ? 'Uploading document…' : 'Extracting rules with the selected AI provider…'}</span>
            <span>{uploadProgress}%</span>
          </div>
          <progress className="h-2 w-full accent-blue-700" max={100} value={uploadProgress} />
        </div>
      )}

      {error && <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700"><AlertCircle size={16} className="mt-0.5 shrink-0" />{error}</p>}
      {notice && <p role="status" className="mt-4 rounded-xl bg-blue-50 px-3 py-2.5 text-sm text-blue-800">{notice}</p>}

      {extraction && rules.length > 0 && (
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <h3 className="font-semibold text-slate-900">Review extracted rules</h3>
              <p className="mt-1 text-xs text-slate-500">
                Extracted by {extraction.provider === 'groq' ? 'Groq' : 'Gemini'} · {extraction.model_used}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setRules((current) => current.map((rule) => ({
                ...rule,
                decision: allApproved ? 'pending' : 'approved',
              })))}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700"
            >
              {allApproved ? 'Clear selection' : 'Approve all'}
            </button>
          </div>

          {rules.map((rule, index) => (
            <article key={`${rule.source_reference}-${index}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                  <input
                    type="checkbox"
                    checked={rule.decision === 'approved'}
                    onChange={(event) => updateRule(index, { decision: event.target.checked ? 'approved' : 'pending' })}
                    aria-label={`Approve ${rule.rule_name}`}
                    className="size-4 accent-blue-700"
                  />
                  Approve rule
                </label>
                <div className="flex flex-wrap gap-2">
                  {rule.manual_review && <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-900">Manual review recommended</span>}
                  {rule.potential_duplicate && <span className="rounded-full bg-orange-100 px-2.5 py-1 text-xs font-medium text-orange-900">Potential duplicate — existing rule preserved</span>}
                </div>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <label className="text-xs font-medium text-slate-600">
                  Rule title
                  <input value={rule.rule_name} onChange={(event) => updateRule(index, { rule_name: event.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800" />
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Category
                  <select value={rule.category} onChange={(event) => updateRule(index, { category: event.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
                    {CATEGORY_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Rule
                  <textarea value={rule.rule_value} onChange={(event) => updateRule(index, { rule_value: event.target.value })} className="mt-1 min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800" />
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Description
                  <textarea value={rule.description} onChange={(event) => updateRule(index, { description: event.target.value })} className="mt-1 min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800" />
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Status
                  <select value={rule.requirement_type} onChange={(event) => updateRule(index, { requirement_type: event.target.value as ReviewRule['requirement_type'] })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
                    <option value="required">Required</option>
                    <option value="prohibited">Prohibited</option>
                    <option value="guidance">Guidance</option>
                  </select>
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Severity
                  <select value={rule.severity} onChange={(event) => updateRule(index, { severity: event.target.value as ReviewRule['severity'] })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </label>
              </div>

              <div className="mt-3 rounded-xl border border-blue-100 bg-white px-3 py-2.5">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-blue-900"><FileText size={14} /> Source · {rule.source_reference}</p>
                <p className="mt-1 text-sm leading-5 text-slate-700">“{rule.source_excerpt}”</p>
              </div>

              <div className="mt-3 flex justify-end">
                {rule.decision === 'rejected' ? (
                  <button type="button" onClick={() => updateRule(index, { decision: 'pending' })} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600">Undo reject</button>
                ) : (
                  <button type="button" onClick={() => updateRule(index, { decision: 'rejected' })} className="rounded-lg px-3 py-1.5 text-sm font-medium text-red-700">Reject rule</button>
                )}
              </div>
            </article>
          ))}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <span className="text-sm text-slate-600">{rules.filter((rule) => rule.decision === 'approved').length} approved · {rules.filter((rule) => rule.decision === 'rejected').length} rejected</span>
            <button
              type="button"
              disabled={isSaving || !rules.some((rule) => rule.decision === 'approved')}
              onClick={() => void saveApprovedRules()}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {isSaving ? <LoaderCircle size={16} className="animate-spin" /> : <Check size={16} />}
              {isSaving ? 'Saving approved rules…' : 'Save approved rules'}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
