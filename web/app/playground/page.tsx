"use client";

import { useMemo, useRef, useState } from "react";
import { appPath } from "@/lib/base-path";
import { buildPlaygroundPrompt, deterministicPlaygroundControl, parsePlaygroundModelResult, playgroundIncident, retrievePlaygroundEvidence, type PlaygroundEvidence } from "@/lib/browser-playground";

type PlaygroundResult = {
  root_cause: string;
  confidence: number;
  citations: string[];
  invalid_citations?: unknown[];
  remediation: string[];
  evidence: PlaygroundEvidence[];
  model: string;
  latency_ms: number;
};

export default function Playground() {
  const apiKey = useRef("");
  const [hasKey, setHasKey] = useState(false);
  const [query, setQuery] = useState("What caused checkout latency after deployment v1.8.3, and what should we do next?");
  const [model, setModel] = useState("openrouter/free");
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const evidence = useMemo(() => retrievePlaygroundEvidence(query), [query]);

  function updateKey(value: string) {
    apiKey.current = value;
    setHasKey(Boolean(value.trim()));
  }

  function clearKey() {
    apiKey.current = "";
    setHasKey(false);
    const input = document.querySelector<HTMLInputElement>("#playground-key");
    if (input) input.value = "";
  }

  function runControl() {
    const started = performance.now();
    const control = deterministicPlaygroundControl(query);
    setResult({ ...control, latency_ms: Math.round(performance.now() - started) });
    setError("");
  }

  async function runModel() {
    if (!apiKey.current.trim()) return setError("Enter an OpenRouter API key, or run the no-key control.");
    setRunning(true);
    setError("");
    const started = performance.now();
    try {
      const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey.current.trim()}`,
          "Content-Type": "application/json",
          "HTTP-Referer": window.location.origin,
          "X-OpenRouter-Title": "RootSignal Bench",
        },
        body: JSON.stringify({ model: model.trim() || "openrouter/free", messages: [{ role: "user", content: buildPlaygroundPrompt(query, evidence) }], temperature: 0, max_tokens: 500 }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error?.message || `Provider request failed (${response.status})`);
      const content = payload?.choices?.[0]?.message?.content;
      if (typeof content !== "string") throw new Error("Provider returned no model response");
      const parsed = parsePlaygroundModelResult(content, evidence);
      setResult({ ...parsed, model: payload.model || model, latency_ms: Math.round(performance.now() - started) });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Model request failed");
    } finally {
      setRunning(false);
    }
  }

  const cited = new Set(result?.citations || []);
  return <main className="playground-shell">
    <header className="playground-topbar"><a className="brand" href={appPath("/")}><span className="brand-mark">RS</span><span>RootSignal</span></a><a href={appPath("/")}>Full engineering workspace →</a></header>
    <section className="playground-hero"><p className="eyebrow"><span>●</span> ZERO-COST HOSTED PLAYGROUND</p><h1>Investigate an incident.<br/><em>Bring your own model.</em></h1><p>Retrieval and evidence selection run locally in your browser. Use the deterministic control without a key, or send the retrieved evidence directly to OpenRouter with your own key.</p></section>
    <section className="playground-security" aria-label="Credential boundary"><strong>Your key never reaches RootSignal</strong><span>Held only in this tab’s memory</span><span>Sent directly to openrouter.ai</span><span>Cleared on refresh or when you click Clear</span></section>
    <section className="playground-grid">
      <article className="playground-card input-card"><span className="card-kicker">01 · INCIDENT</span><h2>{playgroundIncident.title}</h2><p>{playgroundIncident.summary}</p><label>INVESTIGATION QUESTION<textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={4}/></label><div className="retrieval-summary"><strong>{evidence.length} chunks retrieved locally</strong><span>lexical rank · bounded top-k · no network request</span></div></article>
      <article className="playground-card key-card"><span className="card-kicker">02 · EXECUTION</span><label>OPENROUTER API KEY<input id="playground-key" type="password" autoComplete="off" spellCheck={false} onChange={(event) => updateKey(event.target.value)} placeholder="Stored in memory only"/></label><label>MODEL<input value={model} onChange={(event) => setModel(event.target.value)} spellCheck={false}/></label><p>The default <code>openrouter/free</code> router selects a currently available free model. Provider limits still apply.</p><div className="playground-actions"><button className="secondary" onClick={runControl}>Run no-key control</button><button onClick={runModel} disabled={!hasKey || running}>{running ? "Investigating…" : "Run model agent →"}</button></div><button className="clear-key" onClick={clearKey} disabled={!hasKey}>Clear key from memory</button>{error && <p className="playground-error" role="alert">{error}</p>}</article>
    </section>
    <section className="playground-card retrieval-card"><div><span className="card-kicker">03 · LOCAL RETRIEVAL</span><h2>Evidence passed to the model</h2></div><div className="retrieval-list">{evidence.map((item, index) => <div key={item.id}><span>{String(index + 1).padStart(2,"0")}</span><strong>{item.source}</strong><code>{item.id}</code><p>{item.content}</p></div>)}</div></section>
    {result && <section className="playground-results">
      <article className="playground-card"><span className="card-kicker">04 · DIAGNOSIS</span><div className="result-meta"><span>{result.model}</span><span>{result.latency_ms} ms</span><span>{Math.round(result.confidence * 100)}% stated confidence</span></div><h2>{result.root_cause}</h2>{result.invalid_citations?.length ? <p className="playground-error">Rejected {result.invalid_citations.length} citation(s) that were not in retrieved evidence.</p> : null}<h3>Remediation</h3><ol>{result.remediation.map((item) => <li key={item}>{item}</li>)}</ol></article>
      <article className="playground-card"><span className="card-kicker">05 · CITATION AUDIT</span><h2>{result.citations.length}/{result.evidence.length} retrieved items cited</h2><div className="citation-audit">{result.evidence.map((item) => <div className={cited.has(item.id) ? "cited" : ""} key={item.id}><strong>{cited.has(item.id) ? "✓ CITED" : "NOT CITED"}</strong><code>{item.id}</code><p>{item.content}</p></div>)}</div></article>
    </section>}
    <footer><span>Browser playground · no RootSignal backend required</span><a href="https://github.com/medhavee-upadhyaya/rootsignal-bench" target="_blank" rel="noreferrer">Inspect the full implementation ↗</a></footer>
  </main>;
}
