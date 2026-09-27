#!/usr/bin/env bash
# Attempt extra issues one at a time, grading each right away, until the run has
# TARGET resolved issues or the extra list runs out.
# Usage: runner/until_resolved.sh <run-id> [target]      (extra ids: data/extra.json, in order)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$1"
TARGET="${2:-10}"
cd "$ROOT"

resolved_count() {
  .venv/bin/python - "$RUN" <<'EOF'
import json, sys, glob
n = 0
for f in glob.glob(f"logs/run_evaluation/{sys.argv[1]}/*/*/report.json"):
    n += any(v["resolved"] for v in json.load(open(f)).values())
print(n)
EOF
}

for id in $(.venv/bin/python -c "import json; print(' '.join(json.load(open('data/extra.json'))))"); do
  have=$(resolved_count)
  if (( have >= TARGET )); then
    echo "reached $have resolved; stopping"
    break
  fi
  echo "### $have/$TARGET resolved; attempting $id"
  .venv/bin/python runner/run_agent.py --run-id "$RUN" --ids "$id"
  runner/evaluate.sh "$RUN" "$id" > "runs/$RUN/eval/harness-$id.log" 2>&1 || true
  .venv/bin/python -c "import json; print('    verdict:', 'RESOLVED' if json.load(open('logs/run_evaluation/$RUN/claude-code+ornith/$id/report.json'))['$id']['resolved'] else 'failed')" 2>/dev/null \
    || echo "    verdict: no report (see runs/$RUN/eval/harness-$id.log)"
done
echo "final: $(resolved_count) resolved"
