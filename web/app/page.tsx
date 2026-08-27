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
};

type IncidentSummary = {
  id: string;
  title: string;
  summary: string;
  metadata: { failure_class?: string; difficulty?: string; synthetic?: boolean };
  observation_counts: { metrics: number; logs: number; deployments: number; runbooks: number };
};

type IncidentCatalog = { schema_version: string; count: number; incidents: IncidentSummary[] };
type ExecutionMode = "baseline" | "model";
type SystemStatus = {
  llm: { provider: string; model: string; healthy: boolean };
  execution_modes: {
    baseline: { available: boolean; oracle_backed: boolean; purpose: string };
    model: { available: boolean; oracle_backed: boolean; purpose: string };
  };
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
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);

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
        body: JSON.stringify({ incident_id: selectedIncidentId, query, mode }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || payload.detail || "Investigation failed");
      setResult(payload);
      setCompletedMode(mode);
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
    setRunError("");
  }

  function selectMode(nextMode: ExecutionMode) {
    setMode(nextMode);
    setResult(null);
    setCompletedMode(null);
    setRunError("");
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
        body: JSON.stringify({ source, text: knowledgeText }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Indexing failed");
      setIndexStatus(`${payload.status} · ${payload.chunks} new chunk${payload.chunks === 1 ? "" : "s"}`);
      setKnowledgeText("");
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

      <section className="knowledge-section" id="knowledge">
        <div className="knowledge-copy">
          <p className="eyebrow"><span>●</span> LIVE RETRIEVAL PIPELINE</p>
          <h2>Teach the investigator<br />your operational context.</h2>
          <p>Paste a runbook, postmortem, or service note. RootSignal chunks it, fuses lexical and semantic ranks, and preserves source-level citations.</p>
          <div className="pipeline"><span>INGEST</span><i>→</i><span>CHUNK</span><i>→</i><span>INDEX</span><i>→</i><span>RETRIEVE</span></div>
        </div>
        <div className="ingest-card">
          <label>DOCUMENT SOURCE<input value={source} onChange={(event) => setSource(event.target.value)} /></label>
          <label>KNOWLEDGE<textarea rows={6} value={knowledgeText} onChange={(event) => setKnowledgeText(event.target.value)} placeholder="Paste a runbook, postmortem, or operational note…" /></label>
          <div><span>{indexStatus || "SQLite FTS5 · SHA-256 deduplication"}</span><button onClick={indexKnowledge}>Index document <b>→</b></button></div>
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
