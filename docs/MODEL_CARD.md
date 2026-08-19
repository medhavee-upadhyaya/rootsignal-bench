# Tool-selector model card

## Intended use

The optional LoRA adapter predicts the next diagnostic tool from an incident state and a fixed set of schemas. It is a research component, not an autonomous production operator.

## Training data

Examples are generated from reviewed RootSignal fixtures. Each record contains an incident summary, tool schemas, and one expected tool call. Generated datasets include a SHA-256 digest. Train/evaluation splits must be separated by incident template.

## Evaluation

Report exact tool-name accuracy, JSON validity, argument-schema validity, end-to-end completion, latency, and memory. Compare against a prompted base model and the deterministic baseline. Publish failed cases, not only aggregate scores.

## Limitations

Synthetic incidents underrepresent organizational ambiguity, missing telemetry, access restrictions, and correlated failures. Tool selection does not establish that a diagnosis is correct. The current sample fixture is insufficient to train or claim a useful model; it only validates the pipeline.

## Safety

Model outputs are proposals. Production tool adapters should be read-only by default, apply tenant-aware authorization, redact secrets, enforce budgets, and require human approval for state-changing operations.
