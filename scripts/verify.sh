#!/usr/bin/env bash
set -euo pipefail

if [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=.venv/bin/python
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

"$PYTHON_BIN" -m unittest discover -s tests -v
"$PYTHON_BIN" -m evals.run --fixtures fixtures/incidents --minimum 0.80
"$PYTHON_BIN" -m evals.retrieval --fixtures fixtures/incidents --k 2 --ablation --minimum-recall 1.0
"$PYTHON_BIN" -m evals.adversarial --minimum 1.0
DATASET_DIR="$(mktemp -d)/rootsignal-dataset"
"$PYTHON_BIN" -m training.build_dataset --fixtures fixtures/incidents --output-dir "$DATASET_DIR"
"$PYTHON_BIN" -m training.validate_artifacts --dataset-manifest "$DATASET_DIR/dataset_manifest.json"
npm --prefix web run lint
npm --prefix web test
