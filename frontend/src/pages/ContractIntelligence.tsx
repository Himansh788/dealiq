import { useState, useRef } from "react";
import { useSession } from "@/contexts/SessionContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import {
  FileText, Upload, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp,
  TrendingDown, BarChart3, Shield, AlertCircle, Loader2, RefreshCw
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

type Deviation = {
  clause_category: string;
  clause_name: string;
  standard_value: string;
  prospect_value: string;
  deviation_type: string;
  severity: "critical" | "major" | "minor" | "acceptable";
  risk_score: number;
  explanation: string;
  counter_suggestion: string;
  is_discount_related: boolean;
  discount_standard_pct?: number | null;
  discount_prospect_pct?: number | null;
  accepted?: boolean | null;
  id?: string;
};

type AnalysisResult = {
  prospect_contract_id: string;
  deal_name: string;
  prospect_name: string;
  region: string;
  deviations: Deviation[];
  summary: {
    total_deviations: number;
    critical_count: number;
    major_count: number;
    minor_count: number;
    acceptable_count: number;
    contract_risk_score: number;
    has_discount_risk: boolean;
  };
  discount_insights?: any;
  demo?: boolean;
};

const SEVERITY_CONFIG = {
  critical: { color: "bg-red-100 text-red-700 border-red-200", dot: "bg-red-500", label: "Critical" },
  major:    { color: "bg-orange-100 text-orange-700 border-orange-200", dot: "bg-orange-500", label: "Major" },
  minor:    { color: "bg-yellow-100 text-yellow-700 border-yellow-200", dot: "bg-yellow-500", label: "Minor" },
  acceptable: { color: "bg-green-100 text-green-700 border-green-200", dot: "bg-green-500", label: "Acceptable" },
};

function SeverityBadge({ severity }: { severity: string }) {
  const cfg = SEVERITY_CONFIG[severity as keyof typeof SEVERITY_CONFIG] || SEVERITY_CONFIG.acceptable;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function RiskGauge({ score }: { score: number }) {
  const color = score >= 80 ? "text-red-500" : score >= 50 ? "text-orange-500" : "text-green-500";
  const barColor = score >= 80 ? "bg-red-500" : score >= 50 ? "bg-orange-500" : "bg-green-500";
  return (
    <div className="flex flex-col items-center gap-1">
      <span className={`text-3xl font-bold ${color}`}>{score}</span>
      <span className="text-xs text-muted-foreground">/ 100</span>
      <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

function DeviationRow({ dev, onAccept, onReject }: { dev: Deviation; onAccept: () => void; onReject: () => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`border rounded-lg overflow-hidden ${dev.severity === "critical" ? "border-red-200" : dev.severity === "major" ? "border-orange-200" : "border-border"}`}>
      <button
        className="w-full flex items-center gap-3 p-3 text-left hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <SeverityBadge severity={dev.severity} />
        <span className="font-medium text-sm flex-1">{dev.clause_name}</span>
        <span className="text-xs text-muted-foreground hidden sm:block">Risk: {dev.risk_score}</span>
        {dev.accepted === true && <CheckCircle2 className="w-4 h-4 text-green-500" />}
        {dev.accepted === false && <AlertCircle className="w-4 h-4 text-red-400" />}
        {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-border bg-muted/20">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3">
            <div className="bg-background rounded p-2 border border-border">
              <p className="text-xs font-medium text-muted-foreground mb-1">Standard</p>
              <p className="text-sm">{dev.standard_value}</p>
            </div>
            <div className={`bg-background rounded p-2 border ${dev.severity === "critical" ? "border-red-300" : "border-orange-200"}`}>
              <p className="text-xs font-medium text-muted-foreground mb-1">Prospect asks</p>
              <p className="text-sm">{dev.prospect_value}</p>
            </div>
          </div>

          <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded p-2 border border-yellow-200 dark:border-yellow-800">
            <p className="text-xs font-medium text-yellow-700 dark:text-yellow-400 mb-1">Why this matters</p>
            <p className="text-sm text-yellow-800 dark:text-yellow-300">{dev.explanation}</p>
          </div>

          <div className="bg-blue-50 dark:bg-blue-900/20 rounded p-2 border border-blue-200 dark:border-blue-800">
            <p className="text-xs font-medium text-blue-700 dark:text-blue-400 mb-1">Counter with</p>
            <p className="text-sm text-blue-800 dark:text-blue-300">{dev.counter_suggestion}</p>
          </div>

          {dev.accepted === null || dev.accepted === undefined ? (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="text-green-600 border-green-300 hover:bg-green-50" onClick={onAccept}>
                <CheckCircle2 className="w-3 h-3 mr-1" /> Accept
              </Button>
              <Button size="sm" variant="outline" className="text-red-600 border-red-300 hover:bg-red-50" onClick={onReject}>
                <AlertTriangle className="w-3 h-3 mr-1" /> Reject
              </Button>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              {dev.accepted ? "Accepted" : "Rejected"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DiscountSpotlight({ insights }: { insights: any }) {
  if (!insights) return null;
  const chartData = [
    { name: "Your avg", value: insights.company_avg_discount_pct, fill: "#6366f1" },
    { name: "Region avg", value: insights.region_avg_discount_pct, fill: "#8b5cf6" },
    { name: "This deal", value: insights.this_deal_discount_pct, fill: insights.is_steep ? "#ef4444" : "#22c55e" },
  ];
  return (
    <Card className="border-orange-200 dark:border-orange-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <TrendingDown className="w-4 h-4 text-orange-500" />
          Discount Intelligence
          {insights.is_steep && <Badge className="bg-red-100 text-red-700 text-xs">Steep</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => `${v}%`} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-muted rounded-lg p-3 text-sm">
          <p className="font-medium text-foreground mb-1">AI Recommendation</p>
          <p className="text-muted-foreground">{insights.recommendation}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">Historical acceptance rate for {insights.this_deal_discount_pct}%+ discounts</p>
          <div className="flex items-center gap-2">
            <Progress value={insights.historical_acceptance_rate * 100} className="flex-1 h-2" />
            <span className="text-xs font-medium">{Math.round(insights.historical_acceptance_rate * 100)}%</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ContractIntelligence() {
  const { session } = useSession();
  const isDemo = !session || session.access_token === "DEMO_MODE";

  const [activeTab, setActiveTab] = useState("analyze");
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [deviationStates, setDeviationStates] = useState<Record<number, boolean | null>>({});

  const [dealName, setDealName] = useState("");
  const [prospectName, setProspectName] = useState("");
  const [region, setRegion] = useState("APAC");
  const [dealId, setDealId] = useState("demo_deal");
  const prospectFileRef = useRef<HTMLInputElement>(null);
  const [prospectFileName, setProspectFileName] = useState("");

  const [library, setLibrary] = useState<any[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);

  const authHeader = () => {
    if (!session) return "Bearer DEMO_MODE";
    const token = btoa(JSON.stringify(session));
    return `Bearer ${token}`;
  };

  const handleDemoAnalysis = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/contracts/demo/analysis`, {
        headers: { Authorization: authHeader() },
      });
      const data = await res.json();
      setAnalysis({ ...data, demo: true });
      setDeviationStates({});
    } catch (e) {
      toast.error("Failed to load demo analysis");
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!isDemo && !prospectFileRef.current?.files?.[0]) {
      toast.error("Please select a prospect contract file");
      return;
    }

    setLoading(true);
    try {
      if (isDemo) {
        await handleDemoAnalysis();
        return;
      }

      const formData = new FormData();
      formData.append("file", prospectFileRef.current!.files![0]);
      formData.append("deal_id", dealId || "unknown");
      formData.append("deal_name", dealName || "Unknown Deal");
      formData.append("prospect_name", prospectName || "Unknown Prospect");
      formData.append("region", region || "");
      formData.append("standard_contract_id", "std_demo");

      const res = await fetch(`${API_BASE}/contracts/prospect/upload`, {
        method: "POST",
        headers: { Authorization: authHeader() },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAnalysis(data);
      setDeviationStates({});
      toast.success(`Analysis complete — ${data.deviations?.length || 0} deviations found`);
    } catch (e: any) {
      toast.error(`Analysis failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeviationStatus = async (idx: number, accepted: boolean) => {
    if (!analysis) return;
    const dev = analysis.deviations[idx];
    try {
      if (!isDemo && dev.id) {
        await fetch(`${API_BASE}/contracts/prospect/${analysis.prospect_contract_id}/deviations/${dev.id}`, {
          method: "PATCH",
          headers: { Authorization: authHeader(), "Content-Type": "application/json" },
          body: JSON.stringify({ accepted }),
        });
      }
      setDeviationStates(s => ({ ...s, [idx]: accepted }));
      toast.success(accepted ? "Deviation accepted" : "Deviation rejected");
    } catch {
      toast.error("Failed to update status");
    }
  };

  const loadLibrary = async () => {
    setLibraryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/contracts/library`, {
        headers: { Authorization: authHeader() },
      });
      const data = await res.json();
      setLibrary(data);
    } catch {
      toast.error("Failed to load contract library");
    } finally {
      setLibraryLoading(false);
    }
  };

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <FileText className="w-6 h-6 text-primary" />
          Contract Intelligence
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Upload a prospect's redlined contract and get clause-by-clause deviation analysis with AI negotiation guidance.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={v => { setActiveTab(v); if (v === "library") loadLibrary(); }}>
        <TabsList>
          <TabsTrigger value="analyze">Analyze Contract</TabsTrigger>
          <TabsTrigger value="library">Contract Library</TabsTrigger>
        </TabsList>

        <TabsContent value="analyze" className="space-y-6 mt-4">
          {/* Upload panels */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Standard contract */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-500" />
                  Standard Contract (Your Template)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="border-2 border-dashed border-border rounded-lg p-6 text-center bg-muted/20">
                  <FileText className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
                  <p className="text-sm font-medium">SaaS Master Agreement v3.2</p>
                  <p className="text-xs text-muted-foreground mt-1">8 clauses extracted</p>
                  <Badge className="mt-2 bg-blue-100 text-blue-700 text-xs">Active template</Badge>
                </div>
              </CardContent>
            </Card>

            {/* Prospect contract */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Upload className="w-4 h-4 text-orange-500" />
                  Prospect's Redlined Contract
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {!isDemo && (
                  <>
                    <div
                      className="border-2 border-dashed border-border rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 hover:bg-muted/30 transition-colors"
                      onClick={() => prospectFileRef.current?.click()}
                    >
                      <Upload className="w-6 h-6 mx-auto text-muted-foreground mb-1" />
                      {prospectFileName ? (
                        <p className="text-sm font-medium text-foreground">{prospectFileName}</p>
                      ) : (
                        <>
                          <p className="text-sm text-muted-foreground">Drop PDF or DOCX here</p>
                          <p className="text-xs text-muted-foreground">Max 10MB</p>
                        </>
                      )}
                    </div>
                    <input
                      ref={prospectFileRef}
                      type="file"
                      accept=".pdf,.docx,.txt"
                      className="hidden"
                      onChange={e => setProspectFileName(e.target.files?.[0]?.name || "")}
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <Label className="text-xs">Deal name</Label>
                        <Input className="h-8 text-sm" value={dealName} onChange={e => setDealName(e.target.value)} placeholder="Acme Corp" />
                      </div>
                      <div>
                        <Label className="text-xs">Prospect name</Label>
                        <Input className="h-8 text-sm" value={prospectName} onChange={e => setProspectName(e.target.value)} placeholder="Acme Inc" />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <Label className="text-xs">Region</Label>
                        <Input className="h-8 text-sm" value={region} onChange={e => setRegion(e.target.value)} placeholder="APAC" />
                      </div>
                      <div>
                        <Label className="text-xs">Deal ID</Label>
                        <Input className="h-8 text-sm" value={dealId} onChange={e => setDealId(e.target.value)} placeholder="Zoho deal ID" />
                      </div>
                    </div>
                  </>
                )}
                {isDemo && (
                  <div className="border-2 border-dashed border-orange-200 rounded-lg p-6 text-center bg-orange-50/50">
                    <FileText className="w-8 h-8 mx-auto text-orange-400 mb-2" />
                    <p className="text-sm font-medium text-orange-700">Acme_Enterprise_Redlined_v2.pdf</p>
                    <p className="text-xs text-orange-500 mt-1">Demo mode — pre-loaded prospect contract</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Button
            className="w-full sm:w-auto"
            onClick={handleAnalyze}
            disabled={loading}
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Analyzing...</>
            ) : (
              <><BarChart3 className="w-4 h-4 mr-2" /> {isDemo ? "Run Demo Analysis" : "Analyze Contracts"}</>
            )}
          </Button>

          {/* Analysis results */}
          {analysis && (
            <div className="space-y-4">
              {/* Summary cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <Card className="text-center">
                  <CardContent className="pt-4 pb-3">
                    <p className="text-2xl font-bold text-foreground">{analysis.summary.total_deviations}</p>
                    <p className="text-xs text-muted-foreground">Total deviations</p>
                  </CardContent>
                </Card>
                <Card className="text-center border-red-200">
                  <CardContent className="pt-4 pb-3">
                    <p className="text-2xl font-bold text-red-500">{analysis.summary.critical_count}</p>
                    <p className="text-xs text-muted-foreground">Critical</p>
                  </CardContent>
                </Card>
                <Card className="text-center border-orange-200">
                  <CardContent className="pt-4 pb-3">
                    <p className="text-2xl font-bold text-orange-500">{analysis.summary.major_count}</p>
                    <p className="text-xs text-muted-foreground">Major</p>
                  </CardContent>
                </Card>
                <Card className={`text-center ${analysis.summary.has_discount_risk ? "border-red-200" : ""}`}>
                  <CardContent className="pt-4 pb-3">
                    {analysis.summary.has_discount_risk ? (
                      <>
                        <AlertTriangle className="w-5 h-5 text-red-500 mx-auto mb-1" />
                        <p className="text-xs text-red-600 font-medium">Discount risk</p>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-5 h-5 text-green-500 mx-auto mb-1" />
                        <p className="text-xs text-muted-foreground">No discount risk</p>
                      </>
                    )}
                  </CardContent>
                </Card>
                <Card className="text-center">
                  <CardContent className="pt-4 pb-3">
                    <RiskGauge score={analysis.summary.contract_risk_score} />
                    <p className="text-xs text-muted-foreground mt-1">Risk score</p>
                  </CardContent>
                </Card>
              </div>

              {/* Discount spotlight */}
              {analysis.discount_insights && (
                <DiscountSpotlight insights={analysis.discount_insights} />
              )}

              {/* Deviation list */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Clause Deviations</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {analysis.deviations.map((dev, idx) => (
                    <DeviationRow
                      key={idx}
                      dev={{ ...dev, accepted: deviationStates[idx] ?? dev.accepted }}
                      onAccept={() => handleDeviationStatus(idx, true)}
                      onReject={() => handleDeviationStatus(idx, false)}
                    />
                  ))}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="library" className="mt-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-medium text-foreground">Analyzed Contracts</h2>
            <Button variant="outline" size="sm" onClick={loadLibrary} disabled={libraryLoading}>
              <RefreshCw className={`w-3 h-3 mr-1 ${libraryLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>

          {libraryLoading ? (
            <div className="space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-16 bg-muted rounded-lg animate-pulse" />)}
            </div>
          ) : library.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <FileText className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                <p className="text-muted-foreground">No analyzed contracts yet.</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => { setActiveTab("analyze"); handleDemoAnalysis(); }}>
                  Run demo analysis
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {library.map(c => (
                <Card key={c.id} className="hover:bg-muted/30 transition-colors cursor-pointer">
                  <CardContent className="py-3 px-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-sm">{c.deal_name || "Unknown Deal"}</p>
                        <p className="text-xs text-muted-foreground">{c.prospect_name} · {c.region}</p>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{c.deviation_count} deviations</span>
                        {c.critical_count > 0 && (
                          <Badge className="bg-red-100 text-red-700 text-xs">{c.critical_count} critical</Badge>
                        )}
                        {c.has_discount_risk && (
                          <Badge className="bg-orange-100 text-orange-700 text-xs">Discount risk</Badge>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
