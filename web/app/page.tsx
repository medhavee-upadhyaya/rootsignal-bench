"use client";

import { useEffect, useMemo, useState } from "react";

type Evidence = { source: string; content: string; relevance: number };
type ToolCall = { name: string; arguments: Record<string, string> };
type Investigation = {
  incident_id: string;
  root_cause: string;
  confidence: number;
  evidence: Evidence[];
  remediation: string[];
  tool_calls: ToolCall[];
  run?: { model: string; latency_ms: number; prompt_tokens: number; completion_tokens: number; retrieved_chunks: number };
  record?: { run_id: string; created_at: string; mode: ExecutionMode };
};

type IncidentSummary = {
  id: string;
  title: string;
  summary: string;
  metadata: { failure_class?: string; difficulty?: string; synthetic?: boolean; catalog_source?: "built-in" | "custom" };
  observation_counts: { metrics: number; logs: number; deployments: number; runbooks: number };
};

type IncidentCatalog = { schema_version: string; count: number; incidents: IncidentSummary[] };
type KnowledgeCollection = { id: string; name: string; description: string; documents: number };
type ExecutionMode = "baseline" | "model";
type SystemStatus = {
  llm: { provider: string; model: string; healthy: boolean };
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
};
type StoredRun = RunSummary & {
  query: string;
  result: Investigation;
  metadata: { api_version: string; oracle_backed: boolean; retrieval_engine: string; request_id: string };
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

const sourceIcons: Record<string, string> = {
  metrics: "⌁",
  logs: "≡",
  deployments: "↗",
};

function lines(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function buildFixture(draft: Record<string, string>) {
  const metrics = Object.fromEntries(lines(draft.metrics).map((line) => {
    const separator = line.indexOf("=");
    return separator > 0 ? [line.slice(0, separator).trim(), line.slice(separator + 1).trim()] : [line, "observed"];
  }));
  return {
    schema_version: "1.0",
    id: draft.id,
    title: draft.title,
    summary: draft.summary,
    metadata: { failure_class: draft.failureClass, difficulty: draft.difficulty, license: "Proprietary", synthetic: true },
    telemetry: { metrics, logs: lines(draft.logs), deployments: lines(draft.deployments) },
    runbooks: [{ id: `${draft.id}-operations`, title: `${draft.title} operations`, content: draft.runbook }],
    oracle: {
      root_cause: draft.rootCause,
      required_evidence: lines(draft.evidence),
      remediation: lines(draft.remediation),
      expected_tools: ["query_metrics", "query_logs", "query_deployments", "search_runbooks"],
    },
  };
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
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<StoredRun | null>(null);
  const [referenceRunId, setReferenceRunId] = useState("");
  const [candidateRunId, setCandidateRunId] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState("");
  const [showCreator, setShowCreator] = useState(false);
  const [creatorMode, setCreatorMode] = useState<"guided" | "json">("guided");
  const [creatorStatus, setCreatorStatus] = useState("");
  const [jsonFixture, setJsonFixture] = useState("");
  const [incidentDraft, setIncidentDraft] = useState({
    id: "", title: "", summary: "", failureClass: "custom-incident", difficulty: "medium",
    metrics: "service.error_rate=12%\nservice.latency_p95=1800ms",
    logs: "service ERROR request failed\nservice WARN latency threshold exceeded",
    deployments: "service v2.0 deployed before the incident",
    runbook: "Inspect correlated signals and the recent deployment. Roll back the unsafe change.",
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
      chooseComparablePair(payload.runs);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  function chooseComparablePair(runs: RunSummary[]) {
    for (const candidate of runs) {
      const reference = runs.find(
        (run) => run.run_id !== candidate.run_id && run.incident_id === candidate.incident_id && run.fixture_sha256 === candidate.fixture_sha256,
      );
      if (reference) {
        setReferenceRunId((current) => current || reference.run_id);
        setCandidateRunId((current) => current || candidate.run_id);
        return;
      }
    }
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

  async function investigate() {
    if (!selectedIncidentId) return;
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
          collection_ids: selectedCollectionIds,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || payload.detail || "Investigation failed");
      setResult(payload);
      setCompletedMode(mode);
      setActiveRunId(payload.record?.run_id ?? null);
      await refreshRuns();
      if (payload.record?.run_id) await loadRun(payload.record.run_id, false);
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
    setResult(null);
    setCompletedMode(null);
    setActiveRunId(null);
    setActiveRun(null);
    setRunError("");
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

  async function compareSelectedRuns() {
    if (!referenceRunId || !candidateRunId) return;
    setComparisonLoading(true);
    setComparisonError("");
    try {
      const response = await fetch("/api/compare", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reference_run_id: referenceRunId, candidate_run_id: candidateRunId }),
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

  async function createCustomIncident() {
    setCreatorStatus("Validating…");
    try {
      const fixture = creatorMode === "json" ? JSON.parse(jsonFixture) : buildFixture(incidentDraft);
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

      <section className="creator-section" id="create">
        <div className="creator-intro">
          <div><span>CUSTOM EVALUATION DATA</span><strong>Bring your own incident</strong><small>Create a private scenario from observations and a hidden expected outcome.</small></div>
          <button onClick={() => setShowCreator(!showCreator)}>{showCreator ? "Close builder" : "Create scenario →"}</button>
        </div>
        {showCreator && <div className="creator-panel">
          <div className="creator-tabs"><button className={creatorMode === "guided" ? "active" : ""} onClick={() => setCreatorMode("guided")}>Guided builder</button><button className={creatorMode === "json" ? "active" : ""} onClick={() => setCreatorMode("json")}>JSON import</button></div>
          {creatorMode === "guided" ? <div className="creator-form">
            <label>INCIDENT ID<input value={incidentDraft.id} onChange={(event) => setIncidentDraft({...incidentDraft, id: event.target.value})} placeholder="payments-timeout-custom" /></label>
            <label>TITLE<input value={incidentDraft.title} onChange={(event) => setIncidentDraft({...incidentDraft, title: event.target.value})} placeholder="Payment requests timing out" /></label>
            <label className="wide">PUBLIC SUMMARY<textarea rows={2} value={incidentDraft.summary} onChange={(event) => setIncidentDraft({...incidentDraft, summary: event.target.value})} placeholder="Describe observable symptoms without revealing the answer." /></label>
            <label>FAILURE CLASS<input value={incidentDraft.failureClass} onChange={(event) => setIncidentDraft({...incidentDraft, failureClass: event.target.value})} /></label>
            <label>DIFFICULTY<select value={incidentDraft.difficulty} onChange={(event) => setIncidentDraft({...incidentDraft, difficulty: event.target.value})}><option>easy</option><option>medium</option><option>hard</option></select></label>
            <label>METRICS · KEY=VALUE<textarea rows={4} value={incidentDraft.metrics} onChange={(event) => setIncidentDraft({...incidentDraft, metrics: event.target.value})} /></label>
            <label>LOG EVENTS · ONE PER LINE<textarea rows={4} value={incidentDraft.logs} onChange={(event) => setIncidentDraft({...incidentDraft, logs: event.target.value})} /></label>
            <label>DEPLOYMENTS · ONE PER LINE<textarea rows={3} value={incidentDraft.deployments} onChange={(event) => setIncidentDraft({...incidentDraft, deployments: event.target.value})} /></label>
            <label>RUNBOOK<textarea rows={3} value={incidentDraft.runbook} onChange={(event) => setIncidentDraft({...incidentDraft, runbook: event.target.value})} /></label>
            <label className="wide private-field">HIDDEN ROOT CAUSE<textarea rows={2} value={incidentDraft.rootCause} onChange={(event) => setIncidentDraft({...incidentDraft, rootCause: event.target.value})} placeholder="Expected diagnosis used only for scoring" /></label>
            <label>REQUIRED EVIDENCE · ONE PER LINE<textarea rows={3} value={incidentDraft.evidence} onChange={(event) => setIncidentDraft({...incidentDraft, evidence: event.target.value})} /></label>
            <label>REMEDIATION · ONE PER LINE<textarea rows={3} value={incidentDraft.remediation} onChange={(event) => setIncidentDraft({...incidentDraft, remediation: event.target.value})} /></label>
          </div> : <label className="json-import">FIXTURE JSON<textarea rows={18} value={jsonFixture} onChange={(event) => setJsonFixture(event.target.value)} placeholder='{"schema_version":"1.0","id":"..."}' /></label>}
          <div className="creator-actions"><span>{creatorStatus || "The oracle is stored server-side and never returned by catalog APIs."}</span><button onClick={createCustomIncident}>{creatorMode === "json" ? "Validate and import" : "Create scenario"} →</button></div>
        </div>}
      </section>

      <section className="command-card" id="workspace">
        <div className="command-label"><span>⌘</span> REPLAY AN INCIDENT</div>
        <div className="scenario-row">
          <label>
            BENCHMARK SCENARIO
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
              <span>{Object.values(selectedIncident.observation_counts).reduce((sum, count) => sum + count, 0)} observations</span>
            </div>
          )}
        </div>
        <div className="mode-picker" role="radiogroup" aria-label="Execution mode">
          <button
            className={mode === "baseline" ? "active" : ""}
            onClick={() => selectMode("baseline")}
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
            <small>{system?.llm.healthy ? "Grounded model run using tools and retrieved evidence." : "Model endpoint is offline or not configured."}</small>
          </button>
          <div className="connection-state">
            <span className={system?.llm.healthy ? "online" : "offline"}>
              <i /> {systemLoading ? "Checking model" : system?.llm.healthy ? "Model online" : "Model offline"}
            </span>
            <button onClick={refreshSystem} disabled={systemLoading}>Refresh</button>
          </div>
        </div>
        {mode === "model" && !system?.llm.healthy && (
          <div className="connection-help">
            Start an OpenAI-compatible server, then configure <code>INCIDENTLAB_LLM_URL</code> and <code>INCIDENTLAB_MODEL</code> on the API.
          </div>
        )}
        <div className="command-row">
          <textarea
            value={query}
            aria-label="Incident description"
            rows={2}
            readOnly
          />
          <button onClick={investigate} disabled={running || !selectedIncidentId || (mode === "model" && !system?.llm.healthy)}>
            {running ? <><span className="spinner" /> Investigating</> : <>Run {mode === "baseline" ? "control" : "agent"} <span>→</span></>}
          </button>
        </div>
        <div className="command-meta">
          <span><i className="dot green" /> {selectedIncident?.id ?? "catalog loading"}</span>
          <span><i className="dot amber" /> {selectedIncident?.metadata.difficulty ?? "—"}</span>
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
          <div className="trace-footer"><span>{result.tool_calls.length} tool calls</span><span>{result.evidence.length} cited items</span><span>{completedMode === "model" ? result.run?.model || "model" : "oracle-backed control"}</span></div>
        </article>

        <article className="panel diagnosis-panel">
          <div className="panel-heading">
            <div><span className="panel-index coral">02</span><div><p>ROOT CAUSE</p><h2>Evidence-backed diagnosis</h2></div></div>
            <div className="confidence"><strong>{Math.round(result.confidence * 100)}%</strong><span>confidence</span></div>
          </div>
          <div className="cause">
            <span className="cause-label">PRIMARY CAUSE</span>
            <p>{result.root_cause}</p>
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
          <div><span>API / RETRIEVAL</span><code>{activeRun.metadata.api_version} · {activeRun.metadata.retrieval_engine}</code></div>
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
          <div className="run-list">
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
        ) : (
          <div className="runs-empty">{historyLoading ? "Loading saved experiments…" : "No saved runs yet. Complete a control or agent run to create the first experiment record."}</div>
        )}
        <div className="comparison-workspace">
          <div className="comparison-heading">
            <div><span>REGRESSION ANALYSIS</span><h3>Compare experiments</h3></div>
            <p>Fair comparisons require the same incident and fixture revision. The candidate is judged against the reference.</p>
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
            <button onClick={compareSelectedRuns} disabled={!referenceRunId || !candidateRunId || comparisonLoading}>{comparisonLoading ? "Comparing…" : "Compare runs"}</button>
          </div>
          {comparisonError && <p className="comparison-error" role="alert">{comparisonError}</p>}
          {comparison && (
            <div className={`comparison-result ${comparison.verdict}`}>
              <div className="verdict">
                <span>CANDIDATE VERDICT</span>
                <strong>{comparison.verdict}</strong>
                {comparison.reasons.map((reason) => <p key={reason}>{reason}</p>)}
                <a className="comparison-export" href={`/api/export?run_id=${encodeURIComponent(comparison.reference.run.run_id)}&compare_to=${encodeURIComponent(comparison.candidate.run.run_id)}`}>Export verified evidence ↓</a>
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
