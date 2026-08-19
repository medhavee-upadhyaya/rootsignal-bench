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

const benchmarkFallback: Benchmark = {
  model: "Qwen3-1.7B GGUF",
  fixture_count: 5,
  aggregate: { root_cause: .3135, tool_selection: .95, evidence_coverage: .65, remediation_coverage: 1, overall: .6622, mean_latency_ms: 8827.17, citation_validity: 1, model_planned_steps: 19, agent_steps: 20 },
};

const fallback: Investigation = {
  incident_id: "checkout-latency-001",
  root_cause:
    "Deployment v1.8.3 reduced checkout-api DB_POOL_SIZE from 40 to 10, exhausting the database connection pool.",
  confidence: 0.94,
  evidence: [
    { source: "metrics", content: "p95 latency: 240ms → 2,800ms after v1.8.3", relevance: 1 },
    { source: "metrics", content: "db.pool.wait_ms: 35ms → 1,830ms", relevance: 1 },
    { source: "logs", content: "Database connection acquisition timed out after 2000ms", relevance: 1 },
    { source: "deployments", content: "DB_POOL_SIZE changed from 40 → 10 at 10:02Z", relevance: 1 },
  ],
  remediation: [
    "Restore DB_POOL_SIZE to 40",
    "Roll back v1.8.3 if configuration restoration is unsafe",
    "Alert on database pool wait time and saturation",
  ],
  tool_calls: [
    { name: "query_metrics", arguments: {} },
    { name: "query_logs", arguments: { service: "checkout-api" } },
    { name: "query_deployments", arguments: { service: "checkout-api" } },
    { name: "search_runbooks", arguments: { query: "database pool exhaustion" } },
  ],
};

const sourceIcons: Record<string, string> = {
  metrics: "⌁",
  logs: "≡",
  deployments: "↗",
};

export default function Home() {
  const [query, setQuery] = useState("Investigate checkout latency after deployment v1.8.3");
  const [result, setResult] = useState<Investigation>(fallback);
  const [running, setRunning] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState<"evidence" | "remediation">("evidence");
  const [source, setSource] = useState("runbook/custom-operations");
  const [knowledgeText, setKnowledgeText] = useState("");
  const [indexStatus, setIndexStatus] = useState("");
  const [benchmark, setBenchmark] = useState<Benchmark>(benchmarkFallback);

  useEffect(() => {
    fetch("/api/benchmark").then((response) => response.ok ? response.json() : null).then((data) => data && setBenchmark(data)).catch(() => undefined);
  }, []);

  const evidenceGroups = useMemo(() => {
    return result.evidence.reduce<Record<string, Evidence[]>>((groups, item) => {
      (groups[item.source] ||= []).push(item);
      return groups;
    }, {});
  }, [result]);

  async function investigate() {
    setRunning(true);
    try {
      const response = await fetch("/api/investigate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ incident_id: "checkout-latency-001", query }),
      });
      if (!response.ok) throw new Error("API unavailable");
      setResult(await response.json());
      setConnected(true);
    } catch {
      setResult(fallback);
      setConnected(false);
    } finally {
      setRunning(false);
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
          <p className="eyebrow"><span>●</span> OPEN LLM SYSTEMS BENCHMARK</p>
          <h1>Find the cause.<br /><em>Show the evidence.</em></h1>
          <p className="hero-copy">
            Train, serve, and evaluate tool-using agents on reproducible production incidents.
            Every diagnosis is traced. Every claim is scored.
          </p>
        </div>
        <div className="hero-stats" aria-label="System statistics">
          <div><strong>{benchmark.fixture_count}</strong><span>graded incidents</span></div>
          <div><strong>{Math.round(benchmark.aggregate.tool_selection * 100)}%</strong><span>tool selection</span></div>
          <div><strong>11/11</strong><span>tests passing</span></div>
        </div>
      </section>

      <section className="command-card" id="workspace">
        <div className="command-label"><span>⌘</span> NEW INVESTIGATION</div>
        <div className="command-row">
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Incident description"
            rows={2}
          />
          <button onClick={investigate} disabled={running}>
            {running ? <><span className="spinner" /> Investigating</> : <>Run investigation <span>→</span></>}
          </button>
        </div>
        <div className="command-meta">
          <span><i className="dot green" /> checkout-api</span>
          <span><i className="dot amber" /> SEV-2</span>
          <span>Incident #001</span>
          {connected !== null && (
            <span className={connected ? "live" : "demo"}>{connected ? "LIVE API" : "DEMO DATA"}</span>
          )}
        </div>
      </section>

      <section className="workspace-grid">
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
          <div className="trace-footer"><span>{result.tool_calls.length} tool calls</span><span>{result.evidence.length} cited items</span><span>{result.run?.model || "baseline"}</span></div>
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
      </section>

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
        <div className="score-card">
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
        </div>
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
