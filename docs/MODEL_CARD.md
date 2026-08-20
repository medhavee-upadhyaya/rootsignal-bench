# Tool-selector model card

## Intended use

The optional LoRA adapter predicts the next diagnostic tool from an incident state and a fixed set of schemas. It is a research component, not an autonomous production operator.

## Training data

Examples are generated from reviewed RootSignal fixtures. Each record contains an incident summary, tool schemas, and one expected tool call. Generated datasets include a SHA-256 digest. Train/evaluation splits must be separated by incident template.

Generate and validate a leakage-resistant split:

```bash
python -m training.build_dataset --fixtures fixtures/incidents --output-dir work/dataset
python -m training.validate_artifacts --dataset-manifest work/dataset/dataset_manifest.json
```

## Evaluation

Report exact tool-name accuracy, JSON validity, argument-schema validity, end-to-end completion, latency, and memory. Compare against a prompted base model and the deterministic baseline. Publish failed cases, not only aggregate scores.

Base and adapter predictions use the same held-out examples and can be compared
with `python -m training.compare --base <base.jsonl> --adapter <adapter.jsonl>`.
The comparison records sample count, tool accuracy, argument validity, and
measured deltas; it does not infer improvement from training loss alone.

Every trained adapter manifest binds the base-model revision, dataset and
configuration digests, template-isolated split, seed, train/eval metrics,
runtime device, and a checksum over the adapter files. Validate a completed run
with `python -m training.validate_artifacts --training-manifest <adapter>/rootsignal_manifest.json`.

## Limitations

Synthetic incidents underrepresent organizational ambiguity, missing telemetry, access restrictions, and correlated failures. Tool selection does not establish that a diagnosis is correct. The current sample fixture is insufficient to train or claim a useful model; it only validates the pipeline.

## Safety

Model outputs are proposals. Production tool adapters should be read-only by default, apply tenant-aware authorization, redact secrets, enforce budgets, and require human approval for state-changing operations.
