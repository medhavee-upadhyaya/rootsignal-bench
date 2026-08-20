# Contributing

Thank you for improving RootSignal. Contributions are welcome across benchmark fixtures, retrieval, evaluation, inference, training, observability, deployment, and documentation.

## Development setup

Create a branch from `main`, use Python 3.11 or newer, and install the development environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[api,observability]'
npm ci --prefix web
```

Run the complete local gate before opening a pull request:

```bash
./scripts/verify.sh
```

Do not include real credentials, customer data, internal hostnames, or copied proprietary runbooks. Incident fixtures must be synthetic or safely licensed, include distractors, document their causal chain, and pass schema validation. Changes to scoring weights or fixture schemas require documentation and a schema-version change.

Good first contributions include new synthetic fixtures, grading tests, model adapters, retrieval baselines, and documentation improvements.

## Pull-request expectations

- Keep each pull request focused and explain the user-visible or benchmark impact.
- Add regression tests for behavior changes.
- Include before/after machine-readable results for evaluation or performance changes.
- Distinguish measured results from proposals and estimates.
- Update documentation when a public interface, schema, or operational contract changes.
- Confirm that generated datasets, model weights, credentials, and local databases remain untracked.

Maintainers review correctness, reproducibility, safety, and scope. A passing score alone is insufficient if the change leaks oracle information, weakens guardrails, or makes results harder to reproduce.

## Benchmark fixtures

Use the incident issue template before investing in a large fixture. Every accepted fixture needs a single defensible causal chain, public observations sufficient to infer it, at least one plausible distractor, expected tools, evidence requirements, remediation criteria, and synthetic or safely licensed content.

## Community standards

Be specific, respectful, and evidence-driven. Security vulnerabilities belong in private vulnerability reporting rather than public issues. General usage questions should include the revision, runtime, model configuration, and the smallest reproducible example.
