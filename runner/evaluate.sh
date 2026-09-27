#!/usr/bin/env bash
# Grade a run's predictions with the official SWE-bench harness.
# Usage: runner/evaluate.sh <run-id> [instance ids...]   (default ids: data/selected.json;
#        run-id "gold" checks the harness with the reference patches)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$1"
shift
cd "$ROOT"
IDS="${*:-$(.venv/bin/python -c "import json; print(' '.join(json.load(open('data/selected.json'))))")}"

if [[ "$RUN" == "gold" ]]; then
  PREDS=gold
else
  PREDS="runs/$RUN/predictions.jsonl"
fi
mkdir -p "runs/$RUN/eval"

# The prebuilt images are x86_64; Docker runs them under emulation on Apple Silicon.
export DOCKER_DEFAULT_PLATFORM=linux/amd64

.venv/bin/python -m swebench.harness.run_evaluation \
  --dataset_name data/verified.jsonl \
  --predictions_path "$PREDS" \
  --instance_ids $IDS \
  --max_workers 2 \
  --run_id "$RUN" \
  --report_dir "runs/$RUN/eval"
