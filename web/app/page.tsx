"use client";

import { useEffect, useMemo, useState } from "react";
import { getGuidedWorkflow, type GuidedStepId } from "@/lib/guided-workflow";
import { findControlAgentPair } from "@/lib/run-pairing";
import { buildReviewLink, parseReviewLink } from "@/lib/review-links";
import { MAX_TELEMETRY_FILE_BYTES, parseTelemetryBundle } from "@/lib/telemetry-import";

type Evidence = { source: string; content: string; relevance: number };
type ToolCall = { name: string; arguments: Record<string, string> };
type Investigation = {
  incident_id: string;
  root_cause: string;
  confidence: number;
  evidence: Evidence[];
  remediation: string[];
  tool_calls: ToolCall[];
  run?: { model: string; latency_ms: number; prompt_tokens: number; completion_tokens: number; retrieved_chunks: number; stop_reason?: "model_finish" | "tools_exhausted" | "step_budget"; model_requested_stop?: boolean; grounding?: { status: "grounded" | "limited" | "insufficient"; valid_citations: number; source_families: string[]; source_diversity: number } };
  record?: { run_id: string; created_at: string; mode: ExecutionMode };
};

type IncidentSummary = {
  id: string;
  title: string;
  summary: string;
  metadata: { failure_class?: string; difficulty?: string; synthetic?: boolean; evaluable?: boolean; catalog_source?: "built-in" | "custom" };
  observation_counts: { metrics: number; logs: number; deployments: number; runbooks: number };
};

type IncidentCatalog = { schema_version: string; count: number; incidents: IncidentSummary[] };
type KnowledgeCollection = { id: string; name: string; description: string; documents: number };
type ExecutionMode = "baseline" | "model";
type SystemStatus = {
  llm: { provider: string; model: string; healthy: boolean; status: "ready" | "server_error" | "incompatible_server" | "model_not_loaded" | "server_unreachable"; message: string };
  execution_modes: {
    baseline: { available: boolean; oracle_backed: boolean; purpose: string };
    model: { available: boolean; oracle_backed: boolean; purpose: string };
  };
};
type RunSummary = {
  run_id: string;
  created_at: string;
  incident_id: string;
  incident_title: string;
  mode: ExecutionMode;
  model: string;
  fixture_sha256: string;
  confidence: number;
  tool_calls: number;
  evidence_items: number;
  latency_ms: number;
  evaluable: boolean;
};
type StoredRun = RunSummary & {
  query: string;
  result: Investigation;
  metadata: { api_version: string; oracle_backed: boolean; retrieval_engine: string; request_id: string; knowledge_collections?: string[] };
};
type Scorecard = {
  root_cause: number;
  tool_selection: number;
  tool_precision: number;
  evidence_coverage: number;
  citation_validity: number;
  remediation_coverage: number;
  overall: number;
};
type Comparison = {
  verdict: "improved" | "regressed" | "unchanged";
  reasons: string[];
  reference: { run: { run_id: string; model: string; mode: ExecutionMode; latency_ms: number; root_cause: string }; scorecard: Scorecard };
  candidate: { run: { run_id: string; model: string; mode: ExecutionMode; latency_ms: number; root_cause: string }; scorecard: Scorecard };
  deltas: Scorecard & { latency_ms: number; latency_percent: number | null };
  experiment: { inputs_match: boolean; query_match: boolean; knowledge_scope_match: boolean; input_changes: string[]; reference_knowledge_collections: string[]; candidate_knowledge_collections: string[] };
};

type Benchmark = {
  model: string;
  fixture_count: number;
  aggregate: {
    root_cause: number;
    tool_selection: number;
    evidence_coverage: number;
    remediation_coverage: number;
    overall: number;
    mean_latency_ms: number;
    citation_validity: number;
    model_planned_steps: number;
    agent_steps: number;
  };
};
type SuiteReport = { fixture_count: number; models: string[]; aggregate: Omit<Scorecard, "incident_id">; confidence_intervals: { overall: { lower: number; upper: number } }; incidents: Array<Scorecard & { run_id: string; model: string }>; integrity: { algorithm: string; digest: string } };

const sourceIcons: Record<string, string> = {
  metrics: "⌁",
  logs: "≡",
  deployments: "↗",
};

function lines(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function buildFixture(draft: Record<string, string>, includeOracle = true) {
  const metrics = Object.fromEntries(lines(draft.metrics).map((line) => {
    const separator = line.indexOf("=");
    return separator > 0 ? [line.slice(0, separator).trim(), line.slice(separator + 1).trim()] : [line, "observed"];
  }));
  const fixture: Record<string, unknown> = {
    schema_version: "1.0",
    id: draft.id,
    title: draft.title,
    summary: draft.summary,
    metadata: { failure_class: draft.failureClass, difficulty: draft.difficulty, license: "Proprietary", synthetic: includeOracle },
    telemetry: { metrics, logs: lines(draft.logs), deployments: lines(draft.deployments) },
    runbooks: draft.runbook.trim() ? [{ id: `${draft.id}-operations`, title: `${draft.title} operations`, content: draft.runbook.trim() }] : [],
  };
  if (includeOracle) fixture.oracle = {
      root_cause: draft.rootCause,
      required_evidence: lines(draft.evidence),
      remediation: lines(draft.remediation),
      expected_tools: ["query_metrics", "query_logs", "query_deployments", "search_runbooks"],
  };
  return fixture;
}

export default function Home() {
  const [catalog, setCatalog] = useState<IncidentCatalog | null>(null);
  const [selectedIncidentId, setSelectedIncidentId] = useState("");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Investigation | null>(null);
  const [mode, setMode] = useState<ExecutionMode>("baseline");
  const [completedMode, setCompletedMode] = useState<ExecutionMode | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [systemLoading, setSystemLoading] = useState(true);
  const [showModelSetup, setShowModelSetup] = useState(false);
  const [copiedCommand, setCopiedCommand] = useState("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [activeTab, setActiveTab] = useState<"evidence" | "remediation">("evidence");
  const [source, setSource] = useState("runbook/custom-operations");
  const [knowledgeText, setKnowledgeText] = useState("");
  const [indexStatus, setIndexStatus] = useState("");
  const [collections, setCollections] = useState<KnowledgeCollection[]>([]);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState(["incident-runbooks"]);
  const [ingestCollectionId, setIngestCollectionId] = useState("incident-runbooks");
  const [newCollection, setNewCollection] = useState({ id: "", name: "" });
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<StoredRun | null>(null);
  const [referenceRunId, setReferenceRunId] = useState("");
  const [candidateRunId, setCandidateRunId] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState("");
  const [reviewLinkStatus, setReviewLinkStatus] = useState("");
  const [suiteReport, setSuiteReport] = useState<SuiteReport | null>(null);
  const [suiteLoading, setSuiteLoading] = useState(false);
  const [suiteError, setSuiteError] = useState("");
  const [guidedControlRunId, setGuidedControlRunId] = useState<string | null>(null);
  const [guidedAgentRunId, setGuidedAgentRunId] = useState<string | null>(null);
  const [guidedExported, setGuidedExported] = useState(false);
  const [showCreator, setShowCreator] = useState(false);
  const [creatorMode, setCreatorMode] = useState<"guided" | "json">("guided");
  const [creatorPurpose, setCreatorPurpose] = useState<"live" | "evaluation">("live");
  const [creatorStatus, setCreatorStatus] = useState("");
  const [archiveConfirmId, setArchiveConfirmId] = useState("");
  const [jsonFixture, setJsonFixture] = useState("");
  const [incidentDraft, setIncidentDraft] = useState({
    id: "", title: "", summary: "", failureClass: "custom-incident", difficulty: "medium",
    metrics: "service.error_rate=12%\nservice.latency_p95=1800ms",
    logs: "service ERROR request failed\nservice WARN latency threshold exceeded",
    deployments: "service v2.0 deployed before the incident",
    runbook: "",
    rootCause: "", evidence: "error_rate 12%\nlatency_p95 1800ms",
    remediation: "Roll back the unsafe deployment\nAdd an alert for the failure signal",
  });

  useEffect(() => {
    fetch("/api/benchmark").then((response) => response.ok ? response.json() : null).then((data) => data && setBenchmark(data)).catch(() => undefined);
    fetch("/api/incidents")
      .then(async (response) => {
        if (!response.ok) throw new Error("Incident catalog unavailable");
        return response.json();
      })
      .then((data: IncidentCatalog) => {
        setCatalog(data);
        if (data.incidents.length) {
          setSelectedIncidentId(data.incidents[0].id);
          setQuery(data.incidents[0].summary);
        }
      })
      .catch((error) => setRunError(error instanceof Error ? error.message : "Incident catalog unavailable"));
    refreshSystem();
    refreshRuns();
    refreshCollections();
    const review = parseReviewLink(window.location.search);
    let restoreTimer: number | undefined;
    if (review) {
      restoreTimer = window.setTimeout(() => {
        setReferenceRunId(review.referenceRunId);
        setCandidateRunId(review.candidateRunId);
        void loadRun(review.candidateRunId, false);
        void compareSelectedRuns(review.referenceRunId, review.candidateRunId);
      }, 0);
    }
    return () => {
      if (restoreTimer) window.clearTimeout(restoreTimer);
    };
    // Initial data bootstrap; subsequent refreshes are explicit user or run-completion actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshSystem() {
    setSystemLoading(true);
    try {
      const response = await fetch("/api/system", { cache: "no-store" });
      if (!response.ok) throw new Error("System status unavailable");
      setSystem(await response.json());
    } catch {
      setSystem(null);
    } finally {
      setSystemLoading(false);
    }
  }

  async function copySetupCommand(label: string, command: string) {
    try {
      await navigator.clipboard.writeText(command);
      setCopiedCommand(label);
      window.setTimeout(() => setCopiedCommand(""), 1800);
    } catch {
      setCopiedCommand("Copy unavailable");
    }
  }

  async function refreshCollections() {
    try {
      const response = await fetch("/api/collections", { cache: "no-store" });
      if (!response.ok) throw new Error("Knowledge collections unavailable");
      const payload = await response.json();
      setCollections(payload.collections);
    } catch (error) {
      setIndexStatus(error instanceof Error ? error.message : "Knowledge collections unavailable");
    }
  }

  async function createCollection() {
    setIndexStatus("Creating collection…");
    try {
      const response = await fetch("/api/collections", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(newCollection),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || payload.detail || "Creation failed");
      await refreshCollections();
      setIngestCollectionId(payload.id);
      setSelectedCollectionIds((current) => [...new Set([...current, payload.id])]);
      setNewCollection({ id: "", name: "" });
      setIndexStatus(`Created ${payload.name}`);
    } catch (error) {
      setIndexStatus(error instanceof Error ? error.message : "Creation failed");
    }
  }

  function toggleCollection(collectionId: string) {
    setSelectedCollectionIds((current) => current.includes(collectionId)
      ? (current.length === 1 ? current : current.filter((item) => item !== collectionId))
      : [...current, collectionId]);
  }

  async function refreshRuns() {
    setHistoryLoading(true);
    try {
      const response = await fetch("/api/runs", { cache: "no-store" });
      if (!response.ok) throw new Error("Run history unavailable");
      const payload = await response.json();
      setHistory(payload.runs);
      setHistoryCursor(payload.next_cursor ?? null);
      chooseComparablePair(payload.runs);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadMoreRuns() {
    if (!historyCursor || historyLoadingMore) return;
    setHistoryLoadingMore(true);
    try {
      const response = await fetch(`/api/runs?cursor=${encodeURIComponent(historyCursor)}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load more runs");
      const payload = await response.json();
      const merged = [...history, ...payload.runs].filter((run, index, runs) => runs.findIndex((item) => item.run_id === run.run_id) === index);
      setHistory(merged);
      setHistoryCursor(payload.next_cursor ?? null);
      chooseComparablePair(merged);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not load more runs");
    } finally {
      setHistoryLoadingMore(false);
    }
  }

  const latestModelRuns = Array.from(
    history.filter((run) => run.mode === "model" && run.evaluable).reduce((runs, run) => {
      if (!runs.has(run.incident_id)) runs.set(run.incident_id, run);
      return runs;
    }, new Map<string, RunSummary>()).values(),
  );

  async function evaluateLoadedRuns() {
    if (latestModelRuns.length < 2) return;
    setSuiteLoading(true);
    setSuiteError("");
    try {
      const response = await fetch("/api/evaluate", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ run_ids: latestModelRuns.map((run) => run.run_id) }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Suite evaluation failed");
      setSuiteReport(payload);
    } catch (error) {
      setSuiteReport(null);
      setSuiteError(error instanceof Error ? error.message : "Suite evaluation failed");
    } finally {
      setSuiteLoading(false);
    }
  }

  function downloadSuiteReport() {
    if (!suiteReport) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(suiteReport, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `rootsignal-suite-${suiteReport.integrity.digest.slice(0, 12)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function chooseComparablePair(runs: RunSummary[]) {
    const pair = findControlAgentPair(runs);
    if (!pair) return;
    setReferenceRunId((current) => current || pair.referenceRunId);
    setCandidateRunId((current) => current || pair.candidateRunId);
  }

  const selectedIncident = useMemo(
    () => catalog?.incidents.find((incident) => incident.id === selectedIncidentId) ?? null,
    [catalog, selectedIncidentId],
  );

  const evidenceGroups = useMemo(() => {
    return (result?.evidence ?? []).reduce<Record<string, Evidence[]>>((groups, item) => {
      (groups[item.source] ||= []).push(item);
      return groups;
    }, {});
  }, [result]);

  const verifiedCollectionIds = useMemo(
    () => selectedCollectionIds.filter((id) => collections.some((collection) => collection.id === id)),
    [collections, selectedCollectionIds],
  );

  const guidedComparisonComplete = Boolean(
    comparison && guidedControlRunId && guidedAgentRunId
    && comparison.reference.run.run_id === guidedControlRunId
    && comparison.candidate.run.run_id === guidedAgentRunId,
  );
  const guidedWorkflow = getGuidedWorkflow({
    incidentId: selectedIncidentId,
    collectionCount: verifiedCollectionIds.length,
    controlRunId: guidedControlRunId,
    agentRunId: guidedAgentRunId,
    modelAvailable: Boolean(system?.llm.healthy),
    comparisonComplete: guidedComparisonComplete,
    exported: guidedExported,
  });

  async function investigate() {
    if (!selectedIncidentId || !verifiedCollectionIds.length) return;
    setRunning(true);
    setRunError("");
    try {
      const response = await fetch("/api/investigate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          incident_id: selectedIncidentId,
          query,
          mode,
          collection_ids: verifiedCollectionIds,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || payload.detail || "Investigation failed");
      setResult(payload);
      setCompletedMode(mode);
      setActiveRunId(payload.record?.run_id ?? null);
      if (payload.record?.run_id && mode === "baseline") {
        setGuidedControlRunId(payload.record.run_id);
        setGuidedAgentRunId(null);
        setGuidedExported(false);
        setComparison(null);
      } else if (payload.record?.run_id && mode === "model") {
        setGuidedAgentRunId(payload.record.run_id);
        setGuidedExported(false);
        setComparison(null);
        if (guidedControlRunId) {
          setReferenceRunId(guidedControlRunId);
          setCandidateRunId(payload.record.run_id);
        }
      }
      await refreshRuns();
      if (payload.record?.run_id) await loadRun(payload.record.run_id, false);
      if (mode === "baseline" && system?.llm.healthy) setMode("model");
    } catch (error) {
      setResult(null);
      setRunError(error instanceof Error ? error.message : "Investigation failed");
    } finally {
      setRunning(false);
    }
  }

  function selectIncident(incidentId: string) {
    const incident = catalog?.incidents.find((candidate) => candidate.id === incidentId);
    setSelectedIncidentId(incidentId);
    setQuery(incident?.summary ?? "");
    if (incident?.metadata.evaluable === false) setMode("model");
    setResult(null);
    setCompletedMode(null);
    setActiveRunId(null);
    setActiveRun(null);
    setRunError("");
    setGuidedControlRunId(null);
    setGuidedAgentRunId(null);
    setGuidedExported(false);
    setComparison(null);
  }

  function selectMode(nextMode: ExecutionMode) {
    setMode(nextMode);
    setResult(null);
    setCompletedMode(null);
    setActiveRunId(null);
    setActiveRun(null);
    setRunError("");
  }

  async function loadRun(runId: string, scroll = true) {
    setRunError("");
    try {
      const response = await fetch(`/api/runs?run_id=${encodeURIComponent(runId)}`, { cache: "no-store" });
      const payload: StoredRun & { error?: { message?: string } } = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Could not load run");
      setSelectedIncidentId(payload.incident_id);
      setQuery(payload.query);
      setMode(payload.mode);
      setCompletedMode(payload.mode);
      setResult(payload.result);
      setActiveRunId(payload.run_id);
      setActiveRun(payload);
      if (scroll) document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth" });
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not load run");
    }
  }

  function selectReference(runId: string) {
    const reference = history.find((run) => run.run_id === runId);
    const candidate = history.find(
      (run) => run.run_id !== runId && run.incident_id === reference?.incident_id && run.fixture_sha256 === reference?.fixture_sha256,
    );
    setReferenceRunId(runId);
    setCandidateRunId(candidate?.run_id ?? "");
    setComparison(null);
    setComparisonError("");
  }

  async function compareSelectedRuns(referenceId = referenceRunId, candidateId = candidateRunId) {
    if (!referenceId || !candidateId) return;
    setComparisonLoading(true);
    setComparisonError("");
    try {
      const response = await fetch("/api/compare", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reference_run_id: referenceId, candidate_run_id: candidateId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Comparison failed");
      setComparison(payload);
    } catch (error) {
      setComparison(null);
      setComparisonError(error instanceof Error ? error.message : "Comparison failed");
    } finally {
      setComparisonLoading(false);
    }
  }

  async function copyReviewLink() {
    if (!comparison) return;
    const link = buildReviewLink(
      window.location.href,
      comparison.reference.run.run_id,
      comparison.candidate.run.run_id,
    );
    try {
      await navigator.clipboard.writeText(link);
      window.history.replaceState({}, "", link);
      setReviewLinkStatus("Review link copied ✓");
    } catch {
      setReviewLinkStatus("Copy unavailable");
    }
  }

  function startCompleteExample() {
    const example = catalog?.incidents.find((incident) => incident.id.includes("checkout")) ?? catalog?.incidents[0];
    if (!example) return;
    selectIncident(example.id);
    setSelectedCollectionIds(["incident-runbooks"]);
    setMode("baseline");
    document.getElementById("guided-workflow")?.scrollIntoView({ behavior: "smooth" });
  }

  function continueGuidedWorkflow(step: GuidedStepId) {
    if (step === "incident") return document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth" });
    if (step === "knowledge") return document.getElementById("knowledge")?.scrollIntoView({ behavior: "smooth" });
    if (step === "control" || step === "agent") {
      selectMode(step === "control" ? "baseline" : "model");
      return document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth" });
    }
    if (step === "compare" && guidedControlRunId && guidedAgentRunId) {
      setReferenceRunId(guidedControlRunId);
      setCandidateRunId(guidedAgentRunId);
      void compareSelectedRuns(guidedControlRunId, guidedAgentRunId);
      return document.getElementById("runs")?.scrollIntoView({ behavior: "smooth" });
    }
  }

  async function createCustomIncident() {
    setCreatorStatus("Validating…");
    try {
      const fixture = creatorMode === "json" ? JSON.parse(jsonFixture) : buildFixture(incidentDraft, creatorPurpose === "evaluation");
      const response = await fetch("/api/incidents", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(fixture),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || payload.detail || "Import failed");
      const catalogResponse = await fetch("/api/incidents", { cache: "no-store" });
      if (!catalogResponse.ok) throw new Error("Catalog refresh failed");
      const updatedCatalog: IncidentCatalog = await catalogResponse.json();
      setCatalog(updatedCatalog);
      setSelectedIncidentId(payload.incident.id);
      setQuery(payload.incident.summary);
      setMode(payload.incident.metadata.evaluable ? "baseline" : "model");
      setResult(null);
      setActiveRun(null);
      setActiveRunId(null);
      setCreatorStatus(`Created ${payload.incident.id}`);
      setShowCreator(false);
      document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth" });
    } catch (error) {
      setCreatorStatus(error instanceof Error ? error.message : "Import failed");
    }
  }

  async function importTelemetryFile(file: File | undefined) {
    if (!file) return;
    setCreatorStatus("Reading telemetry locally…");
    try {
      if (file.size > MAX_TELEMETRY_FILE_BYTES) throw new Error("Telemetry bundle must not exceed 1 MB");
      const imported = parseTelemetryBundle(await file.text());
      setIncidentDraft((current) => ({
        ...current,
        id: imported.id || current.id,
        title: imported.title || current.title,
        summary: imported.summary || current.summary,
        metrics: imported.metrics,
        logs: imported.logs,
        deployments: imported.deployments,
        runbook: imported.runbook || current.runbook,
      }));
      setCreatorPurpose("live");
      setCreatorStatus(`Loaded locally · ${imported.counts.metrics} metrics · ${imported.counts.logs} logs · ${imported.counts.deployments} deployments`);
    } catch (error) {
      setCreatorStatus(error instanceof Error ? error.message : "Telemetry import failed");
    }
  }

  async function archiveSelectedIncident() {
    if (!selectedIncident || selectedIncident.metadata.catalog_source !== "custom") return;
    if (archiveConfirmId !== selectedIncident.id) {
      setArchiveConfirmId(selectedIncident.id);
      return;
    }
    setRunError("");
    try {
      const response = await fetch(`/api/incidents?incident_id=${encodeURIComponent(selectedIncident.id)}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Archival failed");
      const catalogResponse = await fetch("/api/incidents", { cache: "no-store" });
      if (!catalogResponse.ok) throw new Error("Catalog refresh failed");
      const updatedCatalog: IncidentCatalog = await catalogResponse.json();
      setCatalog(updatedCatalog);
      setArchiveConfirmId("");
      if (updatedCatalog.incidents.length) selectIncident(updatedCatalog.incidents[0].id);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Archival failed");
    }
  }

  async function indexKnowledge() {
    if (knowledgeText.trim().length < 20) {
      setIndexStatus("Add at least 20 characters.");
      return;
    }
    setIndexStatus("Indexing…");
    try {
      const response = await fetch("/api/knowledge", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ collection_id: ingestCollectionId, source, text: knowledgeText }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Indexing failed");
      setIndexStatus(`${payload.status} · ${payload.chunks} new chunk${payload.chunks === 1 ? "" : "s"}`);
      setKnowledgeText("");
      await refreshCollections();
    } catch (error) {
      setIndexStatus(error instanceof Error ? error.message : "Indexing failed");
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RootSignal home">
          <span className="brand-mark">RS</span>
          <span>RootSignal</span>
          <span className="version">v0.2</span>
        </a>
        <nav aria-label="Primary navigation">
          <a className="nav-active" href="#workspace">Investigations</a>
          <a href="#create">Create</a>
          <a href="#runs">Runs</a>
          <a href="#knowledge">Knowledge</a>
          <a href="#benchmarks">Benchmarks</a>
          <a href="#system">System</a>
        </nav>
        <div className="top-actions">
          <span className="environment"><i /> Local environment</span>
          <a className="github-button" href="https://github.com/medhavee-upadhyaya/rootsignal-bench" target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow"><span>●</span> INCIDENT AGENT EVALUATION WORKSPACE</p>
          <h1>Replay the incident.<br /><em>Audit the agent.</em></h1>
          <p className="hero-copy">
            Run reproducible production incidents through an investigator, inspect every tool call and citation,
            then measure whether a model found the right cause for the right reasons.
          </p>
        </div>
        <div className="hero-stats" aria-label="System statistics">
          <div><strong>{catalog?.count ?? "—"}</strong><span>replayable incidents</span></div>
          <div><strong>{benchmark ? `${Math.round(benchmark.aggregate.tool_selection * 100)}%` : "—"}</strong><span>tool selection</span></div>
          <div><strong>4</strong><span>audited tool types</span></div>
        </div>
      </section>

      <section className="guided-workflow" id="guided-workflow" aria-label="Guided evaluation workflow">
        <div className="guided-heading">
          <div><p>FIRST RUN</p><h2>From incident to verified evidence</h2><span>Complete one evaluation with real saved artifacts at every step.</span></div>
          <button onClick={startCompleteExample}>Try complete example →</button>
        </div>
        <ol className="guided-steps">
          {guidedWorkflow.steps.map((step, index) => {
            const labels = ["Choose incident", "Select knowledge", "Run control", "Run agent", "Compare", "Export"];
            return <li key={step.id} className={step.status} aria-current={step.status === "current" || step.status === "blocked" ? "step" : undefined}>
              <button onClick={() => continueGuidedWorkflow(step.id)} disabled={step.status === "pending" || step.status === "complete"}>
                <span>{step.status === "complete" ? "✓" : String(index + 1).padStart(2, "0")}</span>
                <strong>{labels[index]}</strong>
                <small>{step.status === "blocked" ? "Model connection required" : step.status}</small>
              </button>
            </li>;
          })}
        </ol>
        <div className={`guided-next ${guidedWorkflow.complete ? "complete" : ""}`}>
          {guidedWorkflow.complete ? <><strong>Evaluation complete</strong><span>You created a control, an agent run, a fair comparison, and portable evidence.</span></> : guidedWorkflow.current === "agent" && !system?.llm.healthy ? <><strong>Connect a model to continue</strong><span>{system?.llm.message || "Start the RootSignal API, then verify model readiness."}</span><button onClick={refreshSystem} disabled={systemLoading}>{systemLoading ? "Checking…" : "Recheck model"}</button></> : guidedWorkflow.current === "export" && comparison ? <><strong>Evidence is ready</strong><span>Download the signed run data and comparison scorecard.</span><a href={`/api/export?run_id=${encodeURIComponent(comparison.reference.run.run_id)}&compare_to=${encodeURIComponent(comparison.candidate.run.run_id)}`} onClick={() => setGuidedExported(true)}>Export evidence ↓</a></> : <><strong>Next: {guidedWorkflow.steps.find((step) => step.id === guidedWorkflow.current)?.id}</strong><span>{guidedWorkflow.completedCount} of 6 verified steps complete.</span><button onClick={() => guidedWorkflow.current && continueGuidedWorkflow(guidedWorkflow.current)}>Continue →</button></>}
        </div>
      </section>

      <section className="creator-section" id="create">
        <div className="creator-intro">
          <div><span>YOUR OPERATIONAL DATA</span><strong>Investigate a real incident</strong><small>Provide observations only, or add an answer key when building an evaluation.</small></div>
          <button onClick={() => setShowCreator(!showCreator)}>{showCreator ? "Close builder" : "Create incident →"}</button>
        </div>
        {showCreator && <div className="creator-panel">
          <div className="creator-tabs"><button className={creatorMode === "guided" ? "active" : ""} onClick={() => setCreatorMode("guided")}>Guided builder</button><button className={creatorMode === "json" ? "active" : ""} onClick={() => setCreatorMode("json")}>JSON import</button></div>
          {creatorMode === "guided" ? <div className="creator-form">
            <div className="creator-purpose wide"><button className={creatorPurpose === "live" ? "active" : ""} onClick={() => setCreatorPurpose("live")}><strong>Live investigation</strong><span>No answer key · ungraded</span></button><button className={creatorPurpose === "evaluation" ? "active" : ""} onClick={() => setCreatorPurpose("evaluation")}><strong>Evaluation scenario</strong><span>Hidden oracle · scoreable</span></button></div>
            <label className="telemetry-upload wide">IMPORT TELEMETRY BUNDLE · JSON<input type="file" accept="application/json,.json" onChange={(event) => { void importTelemetryFile(event.currentTarget.files?.[0]); event.currentTarget.value = ""; }} /><span>Parsed in your browser · maximum 1 MB · review every field before saving</span></label>
            <label>INCIDENT ID<input value={incidentDraft.id} onChange={(event) => setIncidentDraft({...incidentDraft, id: event.target.value})} placeholder="payments-timeout-custom" /></label>
            <label>TITLE<input value={incidentDraft.title} onChange={(event) => setIncidentDraft({...incidentDraft, title: event.target.value})} placeholder="Payment requests timing out" /></label>
            <label className="wide">PUBLIC SUMMARY<textarea rows={2} value={incidentDraft.summary} onChange={(event) => setIncidentDraft({...incidentDraft, summary: event.target.value})} placeholder="Describe observable symptoms without revealing the answer." /></label>
            <label>FAILURE CLASS<input value={incidentDraft.failureClass} onChange={(event) => setIncidentDraft({...incidentDraft, failureClass: event.target.value})} /></label>
            <label>DIFFICULTY<select value={incidentDraft.difficulty} onChange={(event) => setIncidentDraft({...incidentDraft, difficulty: event.target.value})}><option>easy</option><option>medium</option><option>hard</option></select></label>
            <label>METRICS · KEY=VALUE<textarea rows={4} value={incidentDraft.metrics} onChange={(event) => setIncidentDraft({...incidentDraft, metrics: event.target.value})} /></label>
            <label>LOG EVENTS · ONE PER LINE<textarea rows={4} value={incidentDraft.logs} onChange={(event) => setIncidentDraft({...incidentDraft, logs: event.target.value})} /></label>
            <label>DEPLOYMENTS · ONE PER LINE<textarea rows={3} value={incidentDraft.deployments} onChange={(event) => setIncidentDraft({...incidentDraft, deployments: event.target.value})} /></label>
            <label>RUNBOOK · OPTIONAL FOR LIVE INCIDENTS<textarea rows={3} value={incidentDraft.runbook} onChange={(event) => setIncidentDraft({...incidentDraft, runbook: event.target.value})} placeholder="Optional incident-specific procedure. Scoped knowledge collections remain available." /></label>
            {creatorPurpose === "evaluation" && <><label className="wide private-field">HIDDEN ROOT CAUSE<textarea rows={2} value={incidentDraft.rootCause} onChange={(event) => setIncidentDraft({...incidentDraft, rootCause: event.target.value})} placeholder="Expected diagnosis used only for scoring" /></label>
            <label>REQUIRED EVIDENCE · ONE PER LINE<textarea rows={3} value={incidentDraft.evidence} onChange={(event) => setIncidentDraft({...incidentDraft, evidence: event.target.value})} /></label>
            <label>REMEDIATION · ONE PER LINE<textarea rows={3} value={incidentDraft.remediation} onChange={(event) => setIncidentDraft({...incidentDraft, remediation: event.target.value})} /></label></>}
          </div> : <label className="json-import">FIXTURE JSON<textarea rows={18} value={jsonFixture} onChange={(event) => setJsonFixture(event.target.value)} placeholder='{"schema_version":"1.0","id":"..."}' /></label>}
          <div className="creator-actions"><span>{creatorStatus || (creatorPurpose === "live" ? "Live incidents are investigated without an answer key and excluded from benchmark scores." : "The oracle is stored server-side and never returned by catalog APIs.")}</span><button onClick={createCustomIncident}>{creatorMode === "json" ? "Validate and import" : creatorPurpose === "live" ? "Create live incident" : "Create evaluation"} →</button></div>
        </div>}
      </section>

      <section className="command-card" id="workspace">
        <div className="command-label"><span>⌘</span> REPLAY AN INCIDENT</div>
        <div className="scenario-row">
          <label>
            INCIDENT
            <select
              aria-label="Benchmark incident"
              value={selectedIncidentId}
              onChange={(event) => selectIncident(event.target.value)}
              disabled={!catalog}
            >
              {!catalog && <option>Loading incident catalog…</option>}
              {catalog?.incidents.map((incident) => (
                <option value={incident.id} key={incident.id}>{incident.title}</option>
              ))}
            </select>
          </label>
          {selectedIncident && (
            <div className="scenario-profile">
              <span>{selectedIncident.metadata.failure_class?.replaceAll("-", " ")}</span>
              <span>{selectedIncident.metadata.difficulty}</span>
              <span>{selectedIncident.metadata.catalog_source}</span>
              <span>{selectedIncident.metadata.evaluable === false ? "live · ungraded" : "evaluation · scoreable"}</span>
              <span>{Object.values(selectedIncident.observation_counts).reduce((sum, count) => sum + count, 0)} observations</span>
              {selectedIncident.metadata.catalog_source === "custom" && <button className={archiveConfirmId === selectedIncident.id ? "confirm" : ""} onClick={archiveSelectedIncident} onBlur={() => setArchiveConfirmId("")}>{archiveConfirmId === selectedIncident.id ? "Confirm archive" : "Archive"}</button>}
            </div>
          )}
        </div>
        <div className="mode-picker" role="radiogroup" aria-label="Execution mode">
          <button
            className={mode === "baseline" ? "active" : ""}
            onClick={() => selectMode("baseline")}
            disabled={selectedIncident?.metadata.evaluable === false}
            role="radio"
            aria-checked={mode === "baseline"}
          >
            <span>CONTROL</span>
            <strong>Deterministic baseline</strong>
            <small>Oracle-backed reference for verifying the evaluation pipeline.</small>
          </button>
          <button
            className={mode === "model" ? "active" : ""}
            onClick={() => selectMode("model")}
            role="radio"
            aria-checked={mode === "model"}
          >
            <span>AGENT</span>
            <strong>{system?.llm.model || "Connected model"}</strong>
            <small>{system?.llm.healthy ? "Grounded model run using tools and retrieved evidence." : system?.llm.message || "RootSignal API is unavailable."}</small>
          </button>
          <div className="connection-state">
            <span className={system?.llm.healthy ? "online" : "offline"}>
              <i /> {systemLoading ? "Checking model" : system?.llm.healthy ? "Model online" : system?.llm.status === "model_not_loaded" ? "Model not loaded" : "Model offline"}
            </span>
            <div><button onClick={() => setShowModelSetup(!showModelSetup)}>{showModelSetup ? "Hide setup" : "Setup"}</button><button onClick={refreshSystem} disabled={systemLoading}>Refresh</button></div>
          </div>
        </div>
        {(showModelSetup || (mode === "model" && !system?.llm.healthy)) && (
          <div className="model-setup" aria-label="Model setup">
            <div className="model-setup-heading"><div><span>LOCAL MODEL SETUP</span><strong>Connect private inference in three terminals</strong><small>No browser API key. Prompts and incident data stay on your machine.</small></div><span className={system?.llm.healthy ? "ready" : "waiting"}>{system?.llm.healthy ? "✓ READY" : "○ WAITING"}</span></div>
            <ol>
              {[
                ["1", "Start Ollama", "ollama serve"],
                ["2", "Download the model once", `ollama pull ${system?.llm.model || "qwen3:1.7b"}`],
                ["3", "Restart the RootSignal API", `INCIDENTLAB_LLM_URL=http://127.0.0.1:11434 INCIDENTLAB_MODEL=${system?.llm.model || "qwen3:1.7b"} uvicorn incidentlab.api:app --reload`],
              ].map(([number, label, command]) => <li key={number}><span>{number}</span><div><strong>{label}</strong><code>{command}</code></div><button onClick={() => copySetupCommand(label, command)}>{copiedCommand === label ? "Copied ✓" : "Copy"}</button></li>)}
            </ol>
            <div className="model-setup-footer"><span>Already running another OpenAI-compatible server? Replace the URL and model values in step 3.</span><button onClick={refreshSystem} disabled={systemLoading}>{systemLoading ? "Checking connection…" : "Verify connection →"}</button></div>
          </div>
        )}
        <div className="command-row">
          <div className="investigation-intent">
            <label htmlFor="investigation-query">INVESTIGATION QUESTION</label>
            <textarea id="investigation-query" value={query} aria-label="Investigation question" rows={2} maxLength={2000} onChange={(event) => setQuery(event.target.value)} />
            <div><span>{query.length}/2000 · saved with this run</span><button type="button" onClick={() => setQuery(selectedIncident?.summary ?? "")} disabled={!selectedIncident || query === selectedIncident.summary}>Reset to incident summary</button></div>
          </div>
          <button onClick={investigate} disabled={running || query.trim().length < 3 || !selectedIncidentId || !verifiedCollectionIds.length || (mode === "model" && !system?.llm.healthy)}>
            {running ? <><span className="spinner" /> Investigating</> : <>Run {mode === "baseline" ? "control" : "agent"} <span>→</span></>}
          </button>
        </div>
        <div className="command-meta">
          <span><i className="dot green" /> {selectedIncident?.id ?? "catalog loading"}</span>
          <span><i className="dot amber" /> {selectedIncident?.metadata.difficulty ?? "—"}</span>
          <span>{verifiedCollectionIds.length ? `${verifiedCollectionIds.length} verified knowledge scope${verifiedCollectionIds.length === 1 ? "" : "s"}` : "Knowledge scope unavailable"}</span>
          <span>credentials rejected before execution</span>
          <span>{mode === "baseline" ? "Oracle-backed synthesis" : "Oracle hidden from agent"}</span>
          <span className={mode === "model" ? "model-mode" : "live"}>{mode === "baseline" ? "CONTROL RUN" : "MODEL RUN"}</span>
        </div>
        {runError && <p className="run-error" role="alert">{runError}. Start the RootSignal API and try again.</p>}
      </section>

      {result ? <section className="workspace-grid">
        <article className="panel investigation-panel">
          <div className="panel-heading">
            <div><span className="panel-index">01</span><div><p>INVESTIGATION TRACE</p><h2>What the agent did</h2></div></div>
          <span className="complete"><i /> Complete · {result.run ? `${(result.run.latency_ms / 1000).toFixed(1)}s` : "baseline"}</span>
          </div>
          <ol className="trace-list">
            {result.tool_calls.map((call, index) => (
              <li key={`${call.name}-${index}`}>
                <span className="trace-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="trace-icon">{["⌁", "≡", "↗", "⌕"][index]}</span>
                <div>
                  <strong>{call.name.replaceAll("_", " ")}</strong>
                  <p>{Object.keys(call.arguments).length ? JSON.stringify(call.arguments) : "all available signals"}</p>
                </div>
                <span className="trace-status">✓</span>
              </li>
            ))}
          </ol>
          <div className="trace-footer"><span>{result.tool_calls.length} tool calls</span><span>{result.evidence.length} cited items</span><span>{result.run?.stop_reason === "model_finish" ? "model stopped after sufficient evidence" : result.run?.stop_reason?.replaceAll("_", " ") || (completedMode === "model" ? result.run?.model || "model" : "oracle-backed control")}</span></div>
        </article>

        <article className="panel diagnosis-panel">
          <div className="panel-heading">
            <div><span className="panel-index coral">02</span><div><p>ROOT CAUSE</p><h2>Evidence-backed diagnosis</h2></div></div>
            <div className={`confidence ${result.run?.grounding?.status ?? "control"}`}><strong>{Math.round(result.confidence * 100)}%</strong><span>{result.run?.grounding?.status ?? "control confidence"}</span></div>
          </div>
          <div className="cause">
            <span className="cause-label">PRIMARY CAUSE</span>
            <p>{result.root_cause}</p>
            {result.run?.grounding && <small className={`grounding-note ${result.run.grounding.status}`}>{result.run.grounding.valid_citations} valid citation{result.run.grounding.valid_citations === 1 ? "" : "s"} across {result.run.grounding.source_diversity} signal source{result.run.grounding.source_diversity === 1 ? "" : "s"}</small>}
          </div>
          <div className="tabs" role="tablist">
            <button className={activeTab === "evidence" ? "active" : ""} onClick={() => setActiveTab("evidence")}>Evidence <b>{result.evidence.length}</b></button>
            <button className={activeTab === "remediation" ? "active" : ""} onClick={() => setActiveTab("remediation")}>Remediation <b>{result.remediation.length}</b></button>
          </div>
          {activeTab === "evidence" ? (
            <div className="evidence-list">
              {Object.entries(evidenceGroups).map(([source, items]) => (
                <div className="evidence-group" key={source}>
                  <div className="source-icon">{sourceIcons[source] || "•"}</div>
                  <div><span>{source}</span>{items.map((item) => <p key={item.content}>{item.content}</p>)}</div>
                </div>
              ))}
            </div>
          ) : (
            <ol className="remediation-list">
              {result.remediation.map((item, index) => <li key={item}><span>{index + 1}</span>{item}</li>)}
            </ol>
          )}
        </article>
      </section> : (
        <section className="workspace-empty" aria-live="polite">
          <span>01</span>
          <div>
            <p>INVESTIGATION WORKSPACE</p>
            <h2>{selectedIncident ? selectedIncident.title : "Connect the incident catalog"}</h2>
            <p>{selectedIncident ? (mode === "baseline" ? "Run the control to verify tools, evidence, and the evaluation pipeline." : "Run the connected model to inspect its independent tool trace, citations, diagnosis, and remediation.") : "RootSignal needs the API to load replayable incidents."}</p>
          </div>
        </section>
      )}

      {activeRun && (
        <section className="run-manifest" aria-label="Reproducibility manifest">
          <div><span>RUN ID</span><code>{activeRun.run_id}</code></div>
          <div><span>INCIDENT SHA-256</span><code title={activeRun.fixture_sha256}>{activeRun.fixture_sha256.slice(0, 16)}…</code></div>
          <div><span>API / RETRIEVAL</span><code>{activeRun.metadata.api_version} · {activeRun.metadata.retrieval_engine} · {activeRun.metadata.knowledge_collections?.length ?? 0} scopes</code></div>
          <div><span>REQUEST ID</span><code>{activeRun.metadata.request_id}</code></div>
          <a className="evidence-export" href={`/api/export?run_id=${encodeURIComponent(activeRun.run_id)}`}><span>PORTABLE EVIDENCE</span><strong>Export JSON ↓</strong></a>
        </section>
      )}

      <section className="runs-section" id="runs">
        <div className="runs-heading">
          <div>
            <p className="eyebrow"><span>●</span> REPRODUCIBLE EXPERIMENTS</p>
            <h2>Run history</h2>
            <p>Every successful execution is stored with its incident hash, mode, model, latency, and immutable result snapshot.</p>
          </div>
          <button onClick={refreshRuns} disabled={historyLoading}>{historyLoading ? "Loading…" : "Refresh history"}</button>
        </div>
        {history.length ? (
          <><div className="run-list">
            {history.map((run) => (
              <button className={activeRunId === run.run_id ? "active" : ""} onClick={() => loadRun(run.run_id)} key={run.run_id}>
                <span className={`run-mode ${run.mode}`}>{run.mode === "baseline" ? "CONTROL" : "AGENT"}</span>
                <div>
                  <strong>{run.incident_title}</strong>
                  <small>{run.model} · {run.tool_calls} tools · {run.evidence_items} evidence</small>
                </div>
                <div className="run-stats">
                  <strong>{Math.round(run.confidence * 100)}%</strong>
                  <small>{run.latency_ms < 1000 ? `${Math.round(run.latency_ms)}ms` : `${(run.latency_ms / 1000).toFixed(1)}s`}</small>
                </div>
                <div className="run-identity">
                  <code>{run.run_id.slice(0, 8)}</code>
                  <time>{new Date(run.created_at).toLocaleString()}</time>
                </div>
                <span className="open-run">Open →</span>
              </button>
            ))}
          </div>
          {historyCursor && <button className="load-more-runs" onClick={loadMoreRuns} disabled={historyLoadingMore}>{historyLoadingMore ? "Loading…" : "Load more experiments ↓"}</button>}
          </>
        ) : (
          <div className="runs-empty">{historyLoading ? "Loading saved experiments…" : "No saved runs yet. Complete a control or agent run to create the first experiment record."}</div>
        )}
        <div className="suite-workspace">
          <div><span>SUITE EVALUATION</span><strong>Score saved model runs across incidents</strong><small>{latestModelRuns.length} distinct incident{latestModelRuns.length === 1 ? "" : "s"} available in loaded history</small></div>
          <button onClick={evaluateLoadedRuns} disabled={suiteLoading || latestModelRuns.length < 2}>{suiteLoading ? "Scoring…" : latestModelRuns.length < 2 ? "Need 2 model incidents" : "Evaluate suite →"}</button>
          {suiteError && <p role="alert">{suiteError}</p>}
          {suiteReport && <div className="suite-result"><div><span>OVERALL</span><strong>{suiteReport.aggregate.overall.toFixed(3)}</strong><small>95% CI {suiteReport.confidence_intervals.overall.lower.toFixed(3)}–{suiteReport.confidence_intervals.overall.upper.toFixed(3)}</small></div><div><span>COVERAGE</span><strong>{suiteReport.fixture_count}</strong><small>distinct incidents</small></div><div><span>MODEL SET</span><strong>{suiteReport.models.length}</strong><small>{suiteReport.models.join(", ")}</small></div><button onClick={downloadSuiteReport}>Download verified JSON ↓</button></div>}
        </div>
        <div className="comparison-workspace">
          <div className="comparison-heading">
            <div><span>REGRESSION ANALYSIS</span><h3>Compare experiments</h3></div>
            <p>Automatic pairing selects a control and agent with the same incident and fixture revision. Choose runs manually for model-to-model regression analysis.</p>
          </div>
          <div className="comparison-controls">
            <label>REFERENCE RUN<select aria-label="Reference run" value={referenceRunId} onChange={(event) => selectReference(event.target.value)}>
              <option value="">Select a reference</option>
              {history.map((run) => <option value={run.run_id} key={run.run_id}>{run.incident_title} · {run.model} · {run.run_id.slice(0, 8)}</option>)}
            </select></label>
            <span>→</span>
            <label>CANDIDATE RUN<select aria-label="Candidate run" value={candidateRunId} onChange={(event) => { setCandidateRunId(event.target.value); setComparison(null); setComparisonError(""); }} disabled={!referenceRunId}>
              <option value="">Select a candidate</option>
              {history.filter((run) => {
                const reference = history.find((item) => item.run_id === referenceRunId);
                return run.run_id !== referenceRunId && run.incident_id === reference?.incident_id && run.fixture_sha256 === reference?.fixture_sha256;
              }).map((run) => <option value={run.run_id} key={run.run_id}>{run.model} · {run.mode} · {run.run_id.slice(0, 8)}</option>)}
            </select></label>
            <button onClick={() => compareSelectedRuns()} disabled={!referenceRunId || !candidateRunId || comparisonLoading}>{comparisonLoading ? "Comparing…" : "Compare runs"}</button>
          </div>
          {comparisonError && <p className="comparison-error" role="alert">{comparisonError}</p>}
          {comparison && (
            <div className={`comparison-result ${comparison.verdict}`}>
              <div className="verdict">
                <span>CANDIDATE VERDICT</span>
                <strong>{comparison.verdict}</strong>
                {comparison.reasons.map((reason) => <p key={reason}>{reason}</p>)}
                <a className="comparison-export" href={`/api/export?run_id=${encodeURIComponent(comparison.reference.run.run_id)}&compare_to=${encodeURIComponent(comparison.candidate.run.run_id)}`} onClick={() => guidedComparisonComplete && setGuidedExported(true)}>Export verified evidence ↓</a>
                <button className="review-link" onClick={copyReviewLink}>{reviewLinkStatus || "Copy review link ↗"}</button>
              </div>
              <div className="comparison-table">
                <div className="comparison-row header"><span>Metric</span><span>Reference</span><span>Candidate</span><span>Delta</span></div>
                {([
                  ["Overall quality", "overall"],
                  ["Root cause", "root_cause"],
                  ["Tool selection", "tool_selection"],
                  ["Tool precision", "tool_precision"],
                  ["Evidence coverage", "evidence_coverage"],
                  ["Citation validity", "citation_validity"],
                  ["Remediation", "remediation_coverage"],
                ] as const).map(([label, metric]) => (
                  <div className="comparison-row" key={metric}>
                    <span>{label}</span>
                    <span>{comparison.reference.scorecard[metric].toFixed(2)}</span>
                    <span>{comparison.candidate.scorecard[metric].toFixed(2)}</span>
                    <span className={comparison.deltas[metric] > 0 ? "positive" : comparison.deltas[metric] < 0 ? "negative" : ""}>{comparison.deltas[metric] > 0 ? "+" : ""}{comparison.deltas[metric].toFixed(2)}</span>
                  </div>
                ))}
                <div className="comparison-row"><span>Latency</span><span>{Math.round(comparison.reference.run.latency_ms)}ms</span><span>{Math.round(comparison.candidate.run.latency_ms)}ms</span><span className={comparison.deltas.latency_ms < 0 ? "positive" : comparison.deltas.latency_ms > 0 ? "negative" : ""}>{comparison.deltas.latency_ms > 0 ? "+" : ""}{Math.round(comparison.deltas.latency_ms)}ms</span></div>
              </div>
              <div className="diagnosis-compare">
                <div><span>REFERENCE · {comparison.reference.run.model}</span><p>{comparison.reference.run.root_cause}</p></div>
                <div><span>CANDIDATE · {comparison.candidate.run.model}</span><p>{comparison.candidate.run.root_cause}</p></div>
              </div>
              <div className={`experiment-alignment ${comparison.experiment.inputs_match ? "matched" : "changed"}`}>
                <div><span>EXPERIMENT INPUTS</span><strong>{comparison.experiment.inputs_match ? "Matched" : "Changed"}</strong></div>
                <p>{comparison.experiment.inputs_match ? "Query and knowledge scope are identical, so quality deltas isolate execution behavior." : `Interpret the verdict with caution: ${comparison.experiment.input_changes.join(" and ")} changed between runs.`}</p>
                <div className="scope-diff"><code>REF · {comparison.experiment.reference_knowledge_collections.join(", ") || "unrecorded"}</code><code>CAND · {comparison.experiment.candidate_knowledge_collections.join(", ") || "unrecorded"}</code></div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="knowledge-section" id="knowledge">
        <div className="knowledge-copy">
          <p className="eyebrow"><span>●</span> LIVE RETRIEVAL PIPELINE</p>
          <h2>Teach the investigator<br />your operational context.</h2>
          <p>Paste a runbook, postmortem, or service note. RootSignal chunks it, fuses lexical and semantic ranks, and preserves source-level citations.</p>
          <div className="pipeline"><span>INGEST</span><i>→</i><span>CHUNK</span><i>→</i><span>INDEX</span><i>→</i><span>RETRIEVE</span></div>
        </div>
        <div className="ingest-card">
          <div className="collection-create">
            <label>NEW COLLECTION ID<input value={newCollection.id} onChange={(event) => setNewCollection({...newCollection, id: event.target.value})} placeholder="payments-platform" /></label>
            <label>DISPLAY NAME<input value={newCollection.name} onChange={(event) => setNewCollection({...newCollection, name: event.target.value})} placeholder="Payments platform" /></label>
            <button onClick={createCollection} disabled={!newCollection.id || !newCollection.name}>Create</button>
          </div>
          <label>INDEX INTO COLLECTION<select value={ingestCollectionId} onChange={(event) => setIngestCollectionId(event.target.value)}>{collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name} · {collection.documents} docs</option>)}</select></label>
          <label>DOCUMENT SOURCE<input value={source} onChange={(event) => setSource(event.target.value)} /></label>
          <label>KNOWLEDGE<textarea rows={6} value={knowledgeText} onChange={(event) => setKnowledgeText(event.target.value)} placeholder="Paste a runbook, postmortem, or operational note…" /></label>
          <div><span>{indexStatus || "SQLite FTS5 · SHA-256 deduplication"}</span><button onClick={indexKnowledge}>Index document <b>→</b></button></div>
          <fieldset className="collection-scope"><legend>ACTIVE FOR INVESTIGATIONS</legend>{collections.map((collection) => <label key={collection.id} htmlFor={`collection-${collection.id}`} aria-label={`Use ${collection.name} for investigations`}><input id={`collection-${collection.id}`} type="checkbox" checked={selectedCollectionIds.includes(collection.id)} onChange={() => toggleCollection(collection.id)} /><span><strong>{collection.name}</strong><small>{collection.documents} document{collection.documents === 1 ? "" : "s"}</small></span></label>)}</fieldset>
        </div>
      </section>

      <section className="proof" id="benchmarks">
        <div className="section-intro">
          <p className="eyebrow"><span>●</span> MEASURED, NOT MARKETED</p>
          <h2>An agent is only as good<br />as the proof behind it.</h2>
          <p>RootSignal Bench evaluates the investigation process—not just the final prose.</p>
        </div>
        {benchmark ? <div className="score-card">
          <div className="score-top"><span>LIVE MODEL · {benchmark.fixture_count} INCIDENTS</span><strong>{benchmark.aggregate.overall.toFixed(2)}</strong></div>
          {[
            ["Root-cause score", Math.round(benchmark.aggregate.root_cause * 100)],
            ["Tool selection", Math.round(benchmark.aggregate.tool_selection * 100)],
            ["Evidence coverage", Math.round(benchmark.aggregate.evidence_coverage * 100)],
            ["Citation validity", Math.round(benchmark.aggregate.citation_validity * 100)],
          ].map(([label, value]) => (
            <div className="metric" key={label as string}>
              <div><span>{label}</span><b>{value}%</b></div>
              <div className="bar"><i style={{ width: `${value}%` }} /></div>
            </div>
          ))}
          <p className="score-note">{benchmark.model} · {(benchmark.aggregate.mean_latency_ms / 1000).toFixed(1)}s mean latency · {benchmark.aggregate.model_planned_steps}/{benchmark.aggregate.agent_steps} steps model-planned · failures published, not hidden</p>
        </div> : <div className="score-card unavailable"><strong>Benchmark unavailable</strong><p>Start the API to load the latest measured evaluation artifact.</p></div>}
      </section>

      <section className="system-strip" id="system">
        {[
          ["RETRIEVAL", "Hybrid RRF + provenance", "⌕"],
          ["TOOL USE", "Typed · bounded · read-only", "⌘"],
          ["INFERENCE", "vLLM-compatible adapter", "↯"],
          ["OBSERVABILITY", "Counters + histograms", "⌁"],
        ].map(([title, detail, icon]) => <div key={title}><b>{icon}</b><span>{title}<small>{detail}</small></span></div>)}
      </section>

      <footer><span>RootSignal · Apache-2.0</span><span>Built for reproducible AI engineering.</span></footer>
    </main>
  );
}
