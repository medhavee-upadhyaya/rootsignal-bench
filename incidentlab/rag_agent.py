from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from .knowledge import KnowledgeBase, RetrievedChunk
from .llm import Generation, OllamaClient
from .models import Incident
from .tools import TOOL_REGISTRY


@dataclass(frozen=True)
class PlannedCall:
    name: str
    arguments: dict[str, object]
    decision_source: str


class GroundedAgent:
    """Bounded observe-act agent with validated tools and evidence-grounded synthesis."""

    TOOL_DESCRIPTIONS = {
        "query_metrics": "Read latency, saturation, capacity, and utilization metrics.",
        "query_logs": "Search service logs for errors and anomalous events.",
        "query_deployments": "Inspect recent versions and configuration changes.",
        "retrieve_knowledge": "Search indexed runbooks and operational documents.",
    }

    def __init__(
        self,
        knowledge: KnowledgeBase,
        llm: OllamaClient,
        max_steps: int = 4,
        collection_ids: list[str] | None = None,
        on_event: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.knowledge = knowledge
        self.llm = llm
        self.max_steps = max_steps
        self.collection_ids = collection_ids
        self.on_event = on_event or (lambda event: None)

    def investigate(self, query: str, incident: Incident) -> dict[str, object]:
        evidence: list[dict[str, object]] = []
        calls: list[PlannedCall] = []
        planning_runs: list[Generation] = []
        remaining = list(self.TOOL_DESCRIPTIONS)
        stop_reason = "tools_exhausted"

        for _ in range(self.max_steps):
            if not remaining:
                break
            self.on_event({"type": "planning", "step": len(calls) + 1})
            call, generation = self._choose_next(
                query, evidence, remaining, allow_finish=len(self._source_families(evidence)) >= 2
            )
            if generation:
                planning_runs.append(generation)
            if call.name == "finish":
                stop_reason = "model_finish"
                self.on_event({"type": "stopped", "reason": stop_reason, "steps": len(calls)})
                break
            calls.append(call)
            remaining.remove(call.name)
            new_evidence = self._execute(call, incident, query, evidence)
            evidence.extend(new_evidence)
            self.on_event({
                "type": "tool_completed",
                "step": len(calls),
                "tool": call.name,
                "evidence_items": len(new_evidence),
            })
        if remaining and stop_reason != "model_finish":
            stop_reason = "step_budget"

        numbered = "\n".join(
            f"[{index}] source={item['source']} | {item['content']}" for index, item in enumerate(evidence, 1)
        )
        self.on_event({"type": "synthesizing", "evidence_items": len(evidence)})
        generation = self.llm.generate_json(
            system=(
                "You are a read-only production incident investigator. Use only supplied evidence. Return valid "
                "compact JSON with root_cause (string), confidence (0 to 1), citations (array containing only integer "
                "evidence numbers such as [1,4]), and remediation (array of strings). Interpret A -> B as a change "
                "from A to B; if B is smaller it was reduced. Cite deployment changes and runbooks when relevant."
            ),
            user=f"Question: {query}\n\nEvidence:\n{numbered}",
        )
        answer, generation = self._parse_or_repair(generation)
        valid_citations = sorted(
            {int(value) for value in answer.get("citations", []) if str(value).isdigit() and 1 <= int(value) <= len(evidence)}
        )
        cited_evidence = [evidence[index - 1] for index in valid_citations]
        source_families = self._source_families(cited_evidence)
        if not cited_evidence:
            grounding_status = "insufficient"
        elif len(source_families) < 2:
            grounding_status = "limited"
        else:
            grounding_status = "grounded"
        raw_confidence = max(0.0, min(float(answer.get("confidence", 0)), 1.0))
        confidence = min(raw_confidence, 0.25 if grounding_status == "insufficient" else 0.65 if grounding_status == "limited" else 1.0)
        root_cause = str(answer.get("root_cause", "Insufficient evidence"))
        remediation = self._remediation(answer.get("remediation", []))
        limitations = ["Local compact-model result; verify recommendations before production changes."]
        if grounding_status == "insufficient":
            root_cause = "Insufficient cited evidence to support a diagnosis."
            remediation = ["Collect and cite evidence from at least two independent signal sources before remediation."]
            limitations.append("The model returned no valid evidence citations; diagnosis was withheld.")
        elif grounding_status == "limited":
            limitations.append("Citations cover only one signal source; confidence was capped at 0.65.")
        all_runs = [*planning_runs, generation]
        retrieved = [item for item in evidence if str(item["source"]).startswith("knowledge:")]
        return {
            "incident_id": incident.incident_id,
            "root_cause": root_cause,
            "confidence": confidence,
            "evidence": cited_evidence or self._fallback_evidence(evidence),
            "remediation": remediation,
            "tool_calls": [
                {"name": call.name, "arguments": call.arguments, "decision_source": call.decision_source}
                for call in calls
            ],
            "run": {
                "model": generation.model,
                "latency_ms": round(sum(run.latency_ms for run in all_runs), 2),
                "prompt_tokens": sum(run.prompt_tokens for run in all_runs),
                "completion_tokens": sum(run.completion_tokens for run in all_runs),
                "retrieved_chunks": len(retrieved),
                "knowledge_collections": self.collection_ids or ["incident-runbooks"],
                "citation_validity": 1.0 if valid_citations else 0.0,
                "grounding": {
                    "status": grounding_status,
                    "valid_citations": len(valid_citations),
                    "source_families": sorted(source_families),
                    "source_diversity": len(source_families),
                },
                "agent_steps": len(calls),
                "model_planned_steps": sum(call.decision_source == "model" for call in calls),
                "stop_reason": stop_reason,
                "model_requested_stop": stop_reason == "model_finish",
            },
            "limitations": limitations,
        }

    def _choose_next(
        self, query: str, evidence: list[dict[str, object]], remaining: list[str], *, allow_finish: bool
    ) -> tuple[PlannedCall, Generation | None]:
        observations = "\n".join(f"- {item['source']}: {item['content']}" for item in evidence[-8:]) or "None yet"
        tools = "\n".join(f"- {name}: {self.TOOL_DESCRIPTIONS[name]}" for name in remaining)
        finish = "\n- finish: Stop because the collected evidence is sufficient." if allow_finish else ""
        try:
            generation = self.llm.generate_json(
                "Choose the single best next read-only diagnostic action. Return compact JSON with name and arguments.",
                f"Incident: {query}\nObservations:\n{observations}\nAvailable actions:\n{tools}{finish}",
                max_tokens=100,
            )
            answer = self._json(generation.content)
            name = str(answer.get("name", ""))
            if name == "finish" and allow_finish:
                return PlannedCall("finish", {}, "model"), generation
            if name not in remaining:
                raise ValueError("Model selected an unavailable tool")
            arguments = answer.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            return PlannedCall(name, self._safe_arguments(name, arguments, query), "model"), generation
        except Exception:
            name = remaining[0]
            return PlannedCall(name, self._safe_arguments(name, {}, query), "policy-fallback"), None

    def _execute(
        self, call: PlannedCall, incident: Incident, query: str, evidence: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        if call.name == "retrieve_knowledge":
            retrieval_query = query + " " + " ".join(str(item["content"]) for item in evidence)
            return self._retrieved_evidence(
                self.knowledge.search(
                    retrieval_query, limit=2, collection_ids=self.collection_ids
                )
            )
        return [
            {"source": item.source, "content": item.content, "relevance": item.relevance}
            for item in TOOL_REGISTRY[call.name](incident, call.arguments)
        ]

    @staticmethod
    def _safe_arguments(name: str, arguments: dict[str, object], query: str) -> dict[str, object]:
        if name in {"query_logs", "query_deployments"}:
            return {"service": str(arguments.get("service", ""))[:100]}
        if name == "query_metrics":
            return {"name": str(arguments.get("name", ""))[:100]}
        return {"query": str(arguments.get("query", query))[:1000], "top_k": 2}

    def _parse_or_repair(self, generation: Generation) -> tuple[dict[str, object], Generation]:
        try:
            return self._json(generation.content), generation
        except (json.JSONDecodeError, ValueError):
            repaired = self.llm.generate_json(
                "Return valid compact JSON only. Do not add markdown.",
                "Repair this object without changing its meaning: " + generation.content[:3000],
                max_tokens=350,
            )
            combined = Generation(
                repaired.content,
                repaired.model,
                generation.latency_ms + repaired.latency_ms,
                generation.prompt_tokens + repaired.prompt_tokens,
                generation.completion_tokens + repaired.completion_tokens,
            )
            return self._json(repaired.content), combined

    @staticmethod
    def _json(content: str) -> dict[str, object]:
        clean = content.strip().removeprefix("```json").removesuffix("```").strip()
        value = json.loads(clean)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    @staticmethod
    def _retrieved_evidence(items: list[RetrievedChunk]) -> list[dict[str, object]]:
        return [
            {"source": f"knowledge:{item.source}#{item.chunk_id}", "content": item.content, "relevance": item.score}
            for item in items
        ]

    @staticmethod
    def _fallback_evidence(evidence: list[dict[str, object]]) -> list[dict[str, object]]:
        preferred = [item for item in evidence if item["source"] in {"deployments", "metrics"} or str(item["source"]).startswith("knowledge:")]
        return (preferred or evidence)[:6]

    @staticmethod
    def _source_families(evidence: list[dict[str, object]]) -> set[str]:
        return {
            "knowledge" if str(item["source"]).startswith(("knowledge:", "runbook:")) else str(item["source"])
            for item in evidence
        }

    @staticmethod
    def _remediation(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        return []
