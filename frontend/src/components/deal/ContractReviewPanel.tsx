import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Upload, ChevronDown, ChevronUp, CheckCircle2, XCircle,
  AlertTriangle, ShieldAlert, ShieldCheck, Info, Loader2,
  FileText, TrendingDown, RotateCcw, ArrowRight, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StandardContract {
  id: string;
  name: string;
  version: string;
  is_active: boolean;
  clause_count: number;
  uploaded_at?: string;
}

interface Deviation {
  id?: string;
  clause_category: string;
  clause_name: string;
  standard_value: string;
  prospect_value: string;
  deviation_type: "modified" | "removed" | "added";
  severity: "critical" | "major" | "minor" | "acceptable";
  risk_score: number;
  explanation: string;
  counter_suggestion: string;
  is_discount_related: boolean;
  discount_standard_pct?: number | null;
  discount_prospect_pct?: number | null;
  accepted?: boolean | null;
}

interface Summary {
  total_deviations: number;
  critical_count: number;
  major_count: number;
  minor_count: number;
  acceptable_count: number;
  contract_risk_score: number;
  has_discount_risk: boolean;
}

interface AnalysisResult {
  prospect_contract_id: string;
  deal_name: string;
  prospect_name: string;
  region: string;
  deviations: Deviation[];
  summary: Summary;
  discount_insights?: any;
  demo?: boolean;
}

interface Props {
  dealId: string | null;
  dealName?: string;
  region?: string;
  amount?: number;
  stage?: string;
}

// ── Config ────────────────────────────────────────────────────────────────────

const SEVERITY_CONFIG = {
  critical:   { label: "Critical",   color: "text-red-600 dark:text-red-400",       bg: "bg-red-50 dark:bg-red-900/20",       border: "border-red-200 dark:border-red-800/50",       icon: ShieldAlert },
  major:      { label: "Major",      color: "text-orange-600 dark:text-orange-400", bg: "bg-orange-50 dark:bg-orange-900/20", border: "border-orange-200 dark:border-orange-800/50", icon: AlertTriangle },
  minor:      { label: "Minor",      color: "text-yellow-600 dark:text-yellow-400", bg: "bg-yellow-50 dark:bg-yellow-900/20", border: "border-yellow-200 dark:border-yellow-800/50", icon: Info },
  acceptable: { label: "Acceptable", color: "text-green-600 dark:text-green-400",   bg: "bg-green-50 dark:bg-green-900/20",   border: "border-green-200 dark:border-green-800/50",   icon: ShieldCheck },
} as const;

const CATEGORY_LABELS: Record<string, string> = {
  payment_terms: "Payment Terms", liability: "Liability", sla: "SLA",
  termination: "Termination", ip_ownership: "IP Ownership", indemnity: "Indemnity",
  confidentiality: "Confidentiality", warranty: "Warranty", discount_pricing: "Discount / Pricing",
  data_protection: "Data Protection", force_majeure: "Force Majeure",
  dispute_resolution: "Dispute Resolution", renewal: "Renewal", support_response: "Support",
  other: "Other",
};

function _catLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat.replace(/_/g, " ");
}

function _deviationBadge(t: string) {
  if (t === "added")   return <span className="text-[10px] font-semibold bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded-full">Added</span>;
  if (t === "removed") return <span className="text-[10px] font-semibold bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 px-1.5 py-0.5 rounded-full">Removed</span>;
  return <span className="text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-1.5 py-0.5 rounded-full">Modified</span>;
}

// ── File drop zone (shared) ────────────────────────────────────────────────────

function FileDropZone({
  file,
  onFile,
  label = "Click to upload",
  hint = "PDF, DOCX, or TXT · max 10MB",
}: {
  file: File | null;
  onFile: (f: File) => void;
  label?: string;
  hint?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      onClick={() => ref.current?.click()}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-5 cursor-pointer transition-colors",
        file
          ? "border-indigo-400 bg-indigo-50/50 dark:bg-indigo-900/10"
          : "border-slate-300 dark:border-slate-700 hover:border-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-800/50"
      )}
    >
      <input ref={ref} type="file" accept=".pdf,.docx,.txt" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
      {file ? (
        <>
          <FileText className="h-5 w-5 text-indigo-500" />
          <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300 text-center">{file.name}</span>
          <span className="text-xs text-slate-400">{(file.size / 1024).toFixed(0)} KB · click to change</span>
        </>
      ) : (
        <>
          <Upload className="h-5 w-5 text-slate-400" />
          <span className="text-sm text-slate-500">{label}</span>
          <span className="text-xs text-slate-400">{hint}</span>
        </>
      )}
    </div>
  );
}

// ── Step 1 — Standard template upload ─────────────────────────────────────────

function StandardTemplateStep({
  existing,
  onUploaded,
  onRefresh,
}: {
  existing: StandardContract | null;
  onUploaded: (c: StandardContract) => void;
  onRefresh: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("Vervotech Subscriber Agreement");
  const [version, setVersion] = useState("1.0");
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(!existing);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const result = await api.uploadStandardContract({ file, name, version });
      toast.success(`Standard template "${name}" uploaded — ${result.clause_count} clauses extracted`);
      onUploaded(result);
      setShowUpload(false);
      setFile(null);
    } catch (e: any) {
      toast.error(e?.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  // Existing template summary
  if (existing && !showUpload) {
    return (
      <div className="rounded-lg border border-green-200 dark:border-green-800/50 bg-green-50/60 dark:bg-green-900/10 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{existing.name}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                v{existing.version} · {existing.clause_count} clauses extracted
              </p>
            </div>
          </div>
          <button
            onClick={() => { setShowUpload(true); }}
            className="text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 underline underline-offset-2 shrink-0"
          >
            Replace
          </button>
        </div>
      </div>
    );
  }

  // Upload form
  return (
    <div className="space-y-3">
      {existing && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">Upload a new version to replace the current template.</p>
          <button onClick={() => setShowUpload(false)} className="text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 underline underline-offset-2">Cancel</button>
        </div>
      )}

      <FileDropZone file={file} onFile={setFile} label="Upload standard contract template" />

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Template name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Version</label>
          <input
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="e.g. 2.1"
            className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
      </div>

      <button
        onClick={handleUpload}
        disabled={!file || !name || uploading}
        className="w-full flex items-center justify-center gap-2 rounded-md bg-[#020887] hover:bg-[#010665] disabled:opacity-40 text-white py-2 text-sm font-medium transition-colors"
      >
        {uploading ? (
          <><Loader2 className="h-4 w-4 animate-spin" />Extracting clauses...</>
        ) : (
          <><Upload className="h-4 w-4" />Save Standard Template</>
        )}
      </button>
    </div>
  );
}

// ── Step 2 — Prospect redline upload ──────────────────────────────────────────

function RedlineUploadStep({
  dealId,
  dealName,
  region,
  amount,
  stage,
  standardContractId,
  onResult,
}: {
  dealId: string;
  dealName: string;
  region: string;
  amount: number;
  stage: string;
  standardContractId: string;
  onResult: (r: AnalysisResult) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [prospectName, setProspectName] = useState("");
  const [uploading, setUploading] = useState(false);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const result = await api.uploadProspectContract({
        file,
        dealId,
        dealName,
        prospectName,
        region,
        dealAmount: amount,
        dealStage: stage,
        standardContractId,
      });
      toast.success(`Analysis complete — ${result.summary?.total_deviations ?? 0} deviations found`);
      onResult(result);
    } catch (e: any) {
      toast.error(e?.message ?? "Analysis failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Upload the prospect's redlined version. DealIQ will compare every clause against your standard template.
      </p>

      <FileDropZone file={file} onFile={setFile} label="Upload prospect's redlined contract" />

      <div>
        <label className="block text-xs text-slate-500 mb-1">Prospect / Company name <span className="text-slate-400">(optional)</span></label>
        <input
          type="text"
          value={prospectName}
          onChange={(e) => setProspectName(e.target.value)}
          placeholder="e.g. Acme Corporation"
          className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
      </div>

      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="w-full flex items-center justify-center gap-2 rounded-md bg-[#020887] hover:bg-[#010665] disabled:opacity-40 text-white py-2 text-sm font-medium transition-colors"
      >
        {uploading ? (
          <><Loader2 className="h-4 w-4 animate-spin" />Analyzing deviations...</>
        ) : (
          <><ArrowRight className="h-4 w-4" />Analyze Redline</>
        )}
      </button>
    </div>
  );
}

// ── Summary bar ────────────────────────────────────────────────────────────────

function SummaryBar({ summary }: { summary: Summary }) {
  const total = summary.total_deviations || 1;
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {summary.total_deviations} Deviation{summary.total_deviations !== 1 ? "s" : ""} Found
        </span>
        <span className={cn(
          "text-xs font-bold px-2 py-0.5 rounded-full",
          summary.contract_risk_score >= 70 ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300" :
          summary.contract_risk_score >= 40 ? "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300" :
          "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
        )}>
          Risk Score: {summary.contract_risk_score}
        </span>
      </div>

      <div className="flex h-2 rounded-full overflow-hidden gap-px">
        {summary.critical_count   > 0 && <div className="bg-red-500"    style={{ width: `${(summary.critical_count   / total) * 100}%` }} />}
        {summary.major_count      > 0 && <div className="bg-orange-500" style={{ width: `${(summary.major_count      / total) * 100}%` }} />}
        {summary.minor_count      > 0 && <div className="bg-yellow-500" style={{ width: `${(summary.minor_count      / total) * 100}%` }} />}
        {summary.acceptable_count > 0 && <div className="bg-green-500"  style={{ width: `${(summary.acceptable_count / total) * 100}%` }} />}
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-slate-600 dark:text-slate-400">
        {summary.critical_count   > 0 && <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500 inline-block" />{summary.critical_count} Critical</span>}
        {summary.major_count      > 0 && <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-orange-500 inline-block" />{summary.major_count} Major</span>}
        {summary.minor_count      > 0 && <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-yellow-500 inline-block" />{summary.minor_count} Minor</span>}
        {summary.acceptable_count > 0 && <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-500 inline-block" />{summary.acceptable_count} Acceptable</span>}
      </div>

      {summary.has_discount_risk && (
        <div className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400 font-medium border-t border-slate-100 dark:border-slate-800 pt-2">
          <TrendingDown className="h-3.5 w-3.5" />
          Discount risk — prospect is requesting a steep discount
        </div>
      )}
    </div>
  );
}

// ── Deviation row ──────────────────────────────────────────────────────────────

function DeviationRow({
  dev,
  contractId,
  onStatusChange,
}: {
  dev: Deviation;
  contractId: string;
  onStatusChange: (id: string, accepted: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [updating, setUpdating] = useState(false);
  const cfg = SEVERITY_CONFIG[dev.severity] ?? SEVERITY_CONFIG.acceptable;
  const SevIcon = cfg.icon;
  const devId = dev.id ?? "";

  async function decide(accepted: boolean) {
    if (!devId) return;
    setUpdating(true);
    try {
      await api.updateDeviationStatus(contractId, devId, accepted);
      onStatusChange(devId, accepted);
      toast.success(accepted ? "Deviation accepted" : "Deviation rejected");
    } catch {
      toast.error("Failed to update");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div className={cn("rounded-lg border transition-colors", cfg.border, cfg.bg)}>
      <button onClick={() => setExpanded((v) => !v)} className="w-full flex items-start gap-3 p-3 text-left">
        <SevIcon className={cn("h-4 w-4 mt-0.5 shrink-0", cfg.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-medium text-slate-800 dark:text-slate-100">{dev.clause_name}</span>
            {_deviationBadge(dev.deviation_type)}
            <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded-full">{_catLabel(dev.clause_category)}</span>
            {dev.accepted === true  && <span className="text-[10px] font-semibold text-green-600 dark:text-green-400 flex items-center gap-0.5"><CheckCircle2 className="h-3 w-3" />Accepted</span>}
            {dev.accepted === false && <span className="text-[10px] font-semibold text-red-500 flex items-center gap-0.5"><XCircle className="h-3 w-3" />Rejected</span>}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">{dev.explanation}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn("text-[11px] font-bold px-1.5 py-0.5 rounded bg-white/60 dark:bg-black/30", cfg.color)}>{dev.risk_score}</span>
          {expanded ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-3 space-y-3 border-t border-slate-200 dark:border-slate-700/50">
          {/* Side-by-side */}
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 p-2.5">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Standard</p>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">{dev.standard_value}</p>
            </div>
            <div className={cn("rounded-md border p-2.5 bg-white/60 dark:bg-black/20", cfg.border)}>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Prospect Redline</p>
              <p className={cn("text-xs leading-relaxed font-medium", cfg.color)}>{dev.prospect_value}</p>
            </div>
          </div>

          {/* Discount delta */}
          {dev.is_discount_related && dev.discount_standard_pct != null && dev.discount_prospect_pct != null && (
            <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-md px-3 py-2 border border-red-200 dark:border-red-800/50">
              <TrendingDown className="h-3.5 w-3.5 shrink-0" />
              Standard: {dev.discount_standard_pct}% → Prospect asking: {dev.discount_prospect_pct}%
              &nbsp;(+{Math.round((dev.discount_prospect_pct - dev.discount_standard_pct) / Math.max(dev.discount_standard_pct, 1) * 100)}% vs standard)
            </div>
          )}

          {/* Counter proposal */}
          {dev.counter_suggestion && (
            <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800/50 p-2.5">
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-1">AI Counter-Proposal</p>
              <p className="text-xs text-blue-800 dark:text-blue-200 leading-relaxed">{dev.counter_suggestion}</p>
            </div>
          )}

          {/* Decision buttons */}
          {devId && dev.accepted == null && (
            <div className="flex items-center gap-2 pt-1">
              <button onClick={() => decide(true)} disabled={updating}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium bg-green-100 hover:bg-green-200 text-green-700 dark:bg-green-900/30 dark:hover:bg-green-900/50 dark:text-green-300 disabled:opacity-50 transition-colors">
                {updating ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                Accept
              </button>
              <button onClick={() => decide(false)} disabled={updating}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium bg-red-100 hover:bg-red-200 text-red-700 dark:bg-red-900/30 dark:hover:bg-red-900/50 dark:text-red-300 disabled:opacity-50 transition-colors">
                <XCircle className="h-3 w-3" />Reject
              </button>
            </div>
          )}
          {devId && dev.accepted != null && (
            <button onClick={() => decide(!dev.accepted)} disabled={updating}
              className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-400 disabled:opacity-50 transition-colors">
              <RotateCcw className="h-3 w-3" />Change decision
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Step indicator ─────────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: "Standard Template" },
    { n: 2, label: "Upload Redline" },
    { n: 3, label: "Review Deviations" },
  ];
  return (
    <div className="flex items-center gap-0 mb-4">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center">
          <div className={cn(
            "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
            step === s.n ? "bg-[#020887] text-white" :
            step > s.n  ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300" :
                          "bg-slate-100 dark:bg-slate-800 text-slate-400"
          )}>
            {step > s.n
              ? <CheckCircle2 className="h-3 w-3" />
              : <span className="h-3.5 w-3.5 flex items-center justify-center text-[10px] font-bold">{s.n}</span>
            }
            <span className="hidden sm:inline">{s.label}</span>
          </div>
          {i < steps.length - 1 && (
            <ArrowRight className="h-3 w-3 mx-1 text-slate-300 dark:text-slate-600" />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function ContractReviewPanel({
  dealId, dealName = "", region = "", amount = 0, stage = "",
}: Props) {
  const [loadingStandard, setLoadingStandard] = useState(true);
  const [standardContract, setStandardContract] = useState<StandardContract | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [deviations, setDeviations] = useState<Deviation[]>([]);
  const [showNewUpload, setShowNewUpload] = useState(false);

  // Determine which step the user is on
  const step: 1 | 2 | 3 = result ? 3 : standardContract ? 2 : 1;

  // Load existing standard contracts on mount
  useEffect(() => {
    setLoadingStandard(true);
    api.listStandardContracts()
      .then((list: StandardContract[]) => {
        const active = list.find((c) => c.is_active) ?? list[0] ?? null;
        setStandardContract(active);
      })
      .catch(() => {/* no standard yet — that's ok */})
      .finally(() => setLoadingStandard(false));
  }, []);

  function handleStatusChange(devId: string, accepted: boolean) {
    setDeviations((prev) => prev.map((d) => d.id === devId ? { ...d, accepted } : d));
  }

  function handleAnalysisResult(r: AnalysisResult) {
    setResult(r);
    setDeviations(r.deviations ?? []);
    setShowNewUpload(false);
  }

  if (loadingStandard) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading...
      </div>
    );
  }

  const contractId = result?.prospect_contract_id ?? "";

  return (
    <div className="space-y-4">
      <StepIndicator step={step} />

      {/* ── Step 1: Standard template ── */}
      <div className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
          Step 1 — Standard Template
        </p>
        <StandardTemplateStep
          existing={standardContract}
          onUploaded={(c) => setStandardContract(c)}
          onRefresh={() => {}}
        />
      </div>

      {/* ── Step 2: Upload redline (unlocked after standard is set) ── */}
      {!result && (
        <div className={cn("space-y-2", !standardContract && "opacity-40 pointer-events-none select-none")}>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Step 2 — Prospect Redline
            {!standardContract && <span className="ml-2 normal-case font-normal text-slate-400">— upload standard template first</span>}
          </p>
          {dealId && standardContract && (
            <RedlineUploadStep
              dealId={dealId}
              dealName={dealName}
              region={region}
              amount={amount}
              stage={stage}
              standardContractId={standardContract.id}
              onResult={handleAnalysisResult}
            />
          )}
        </div>
      )}

      {/* ── Step 3: Results ── */}
      {result && (
        <div className="space-y-3">
          {/* Result header */}
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
              Step 3 — Deviation Analysis
            </p>
            <button
              onClick={() => { setResult(null); setDeviations([]); setShowNewUpload(false); }}
              className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <RefreshCw className="h-3 w-3" />Analyze new redline
            </button>
          </div>

          {/* Demo banner */}
          {result.demo && (
            <div className="flex items-center gap-2 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              <Info className="h-3.5 w-3.5 shrink-0" />
              Showing demo data. Upload a real redlined contract to see actual deviations.
            </div>
          )}

          {/* Meta */}
          {(result.prospect_name || result.deal_name) && (
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {result.prospect_name && <span className="font-medium text-slate-700 dark:text-slate-300">{result.prospect_name}</span>}
              {result.prospect_name && result.deal_name && " · "}
              {result.deal_name}
              {result.region && <span className="ml-2 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-[11px]">{result.region}</span>}
            </div>
          )}

          <SummaryBar summary={result.summary} />

          {deviations.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Deviations ({deviations.length})
              </p>
              {deviations.map((dev, i) => (
                <DeviationRow
                  key={dev.id ?? `${dev.clause_category}-${i}`}
                  dev={dev}
                  contractId={contractId}
                  onStatusChange={handleStatusChange}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
