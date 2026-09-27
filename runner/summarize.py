"""Join the harness verdicts with the runner's per-issue stats into runs/<run-id>/results.md.

Usage: .venv/bin/python runner/summarize.py run1
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(run_id):
    # Every issue attempted in this run, in the order it ran.
    preds = (ROOT / "runs" / run_id / "predictions.jsonl").read_text().splitlines()
    ids = [json.loads(l)["instance_id"] for l in preds]
    rows, totals = [], {"resolved": 0, "wall_s": 0.0, "turns": 0}
    for iid in ids:
        meta = json.loads((ROOT / "runs" / run_id / iid / "meta.json").read_text())
        reports = list((ROOT / "logs" / "run_evaluation" / run_id).glob(f"*/{iid}/report.json"))
        if reports:
            r = json.loads(reports[0].read_text())[iid]
            ts = r.get("tests_status", {})
            f2p, p2p = ts.get("FAIL_TO_PASS", {}), ts.get("PASS_TO_PASS", {})
            verdict = "resolved" if r["resolved"] else "failed"
            f2p_s = f'{len(f2p.get("success", []))}/{len(f2p.get("success", [])) + len(f2p.get("failure", []))}'
            p2p_s = f'{len(p2p.get("success", []))}/{len(p2p.get("success", [])) + len(p2p.get("failure", []))}'
            totals["resolved"] += bool(r["resolved"])
        else:
            verdict, f2p_s, p2p_s = "no report", "-", "-"
        totals["wall_s"] += meta["wall_s"]
        totals["turns"] += meta["num_turns"] or 0
        tools = meta["tool_calls"]
        rows.append(
            f'| {iid} | {verdict} | {f2p_s} | {p2p_s} | {meta["wall_s"] / 60:.1f} | {meta["num_turns"]} '
            f'| {meta["max_prompt_tokens"] // 1000}K | {meta["patch_lines"]} '
            f'| {sum(tools.values())} ({", ".join(f"{k} {v}" for k, v in sorted(tools.items(), key=lambda kv: -kv[1]))}) |'
        )

    n = len(ids)
    out = [
        f"# Results: {run_id}",
        "",
        f'**Resolved {totals["resolved"]}/{n}** by the official SWE-bench harness. '
        f'Agent time {totals["wall_s"] / 60:.0f} min total, {totals["wall_s"] / 60 / n:.1f} min and {totals["turns"] / n:.0f} turns per issue on average.',
        "",
        "| Issue | Verdict | FAIL_TO_PASS | PASS_TO_PASS | Minutes | Turns | Largest prompt | Patch lines | Tool calls |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
    ]
    path = ROOT / "runs" / run_id / "results.md"
    path.write_text("\n".join(out) + "\n")
    print(path.read_text())


if __name__ == "__main__":
    main(sys.argv[1])
