# Contributing

Thank you for improving RootSignal. Run the following before opening a pull request:

```bash
python -m unittest discover -s tests -v
python -m evals.run --fixtures fixtures/incidents
```

Do not include real credentials, customer data, internal hostnames, or copied proprietary runbooks. Incident fixtures must be synthetic or safely licensed, include distractors, document their causal chain, and pass schema validation. Changes to scoring weights or fixture schemas require documentation and a schema-version change.

Good first contributions include new synthetic fixtures, grading tests, model adapters, retrieval baselines, and documentation improvements.
