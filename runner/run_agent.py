"""Run Claude Code (on the local Ollama model) against SWE-bench Verified issues.

Each issue runs inside its official SWE-bench container: the repo is already at
/testbed on the right commit with a working test environment. The agent edits
the code there, and its `git diff` becomes the prediction that the official
harness grades afterwards (see runner/evaluate.sh).

Usage:
  .venv/bin/python runner/run_agent.py --run-id run1 [--ids django__django-10880 ...]
"""

import argparse
import collections
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_BIN = ROOT / "tools" / "claude-linux-x64"
MODEL = "ornith"

# Agent containers sit on an internal network with no route out. The only thing
# they can reach is a relay container that forwards port 11434 to Ollama on the
# host, so the agent cannot look up the upstream fix online.
NETWORK = "swe-isolated"
PROXY = "swe-ollama-proxy"

# Environment for Claude Code inside the container. Same idea as bin/claude-local:
# every model alias points at the local model.
AGENT_ENV = {
    # Resolves to the relay on the internal network (see ensure_isolated_network).
    "ANTHROPIC_BASE_URL": "http://host.docker.internal:11434",
    "ANTHROPIC_AUTH_TOKEN": "ollama",
    "ANTHROPIC_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
    "CLAUDE_CODE_SUBAGENT_MODEL": MODEL,
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    # Lets --dangerously-skip-permissions run as root; the container is the sandbox.
    "IS_SANDBOX": "1",
    # Put the repo's conda env first so `python` runs the Django under test.
    "PATH": "/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ensure_isolated_network():
    if sh(["docker", "network", "inspect", NETWORK]).returncode != 0:
        sh(["docker", "network", "create", "--internal", NETWORK])
    running = sh(["docker", "inspect", "-f", "{{.State.Running}}", PROXY]).stdout.strip()
    if running != "true":
        sh(["docker", "rm", "-f", PROXY])
        r = sh(["docker", "run", "-d", "--name", PROXY,
                "--add-host", "host.docker.internal:host-gateway",
                "alpine/socat", "tcp-listen:11434,fork,reuseaddr", "tcp-connect:host.docker.internal:11434"])
        if r.returncode != 0:
            raise RuntimeError(f"relay failed to start: {r.stderr}")
        # Ollama only answers Host headers it trusts, so the relay takes the
        # host.docker.internal name inside the isolated network.
        sh(["docker", "network", "connect", "--alias", "host.docker.internal", NETWORK, PROXY])


def check_isolation(name):
    """Fail loudly unless the container reaches Ollama but not the internet."""
    probe = ("import urllib.request as u\n"
             "def ok(url):\n"
             "    try: u.urlopen(url, timeout=8); return True\n"
             "    except Exception: return False\n"
             "print(ok('http://host.docker.internal:11434/api/version'), ok('https://pypi.org/simple/'))")
    out = sh(["docker", "exec", name, "/opt/miniconda3/envs/testbed/bin/python", "-c", probe]).stdout.split()
    if out != ["True", "False"]:
        raise RuntimeError(f"isolation check failed (ollama, internet) = {out}")


def load_instances(ids):
    rows = {}
    with open(ROOT / "data" / "verified.jsonl") as f:
        for line in f:
            r = json.loads(line)
            rows[r["instance_id"]] = r
    return [rows[i] for i in ids]


def summarize(transcript_path):
    """Pull turn counts, tool usage and the largest prompt from a stream-json transcript."""
    tools = collections.Counter()
    max_prompt = 0
    result = {}
    for line in transcript_path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            msg = ev.get("message", {})
            u = msg.get("usage", {})
            prompt = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            max_prompt = max(max_prompt, prompt)
            for block in msg.get("content", []):
                if block.get("type") == "tool_use":
                    tools[block.get("name")] += 1
        elif ev.get("type") == "result":
            result = ev
    return {
        "num_turns": result.get("num_turns"),
        "agent_duration_s": round(result.get("duration_ms", 0) / 1000, 1),
        "is_error": result.get("is_error"),
        "stop": result.get("subtype") or result.get("terminal_reason"),
        "output_tokens": result.get("usage", {}).get("output_tokens"),
        "max_prompt_tokens": max_prompt,
        "tool_calls": dict(tools),
        "final_message": (result.get("result") or "")[:2000],
    }


def run_one(inst, run_dir, max_turns, timeout, keep):
    iid = inst["instance_id"]
    out = run_dir / iid
    out.mkdir(parents=True, exist_ok=True)
    name = f"swe-agent-{iid}"

    sh(["docker", "rm", "-f", name])
    started = sh([
        "docker", "run", "-d", "--platform", "linux/amd64", "--name", name,
        "--network", NETWORK,
        "-v", f"{CLAUDE_BIN}:/usr/local/bin/claude:ro",
        inst["image"], "tail", "-f", "/dev/null",
    ])
    if started.returncode != 0:
        raise RuntimeError(f"container failed to start: {started.stderr}")

    # The images add a mode-only "SWE-bench" commit on top of the base commit.
    heads = sh(["docker", "exec", name, "git", "-C", "/testbed", "rev-parse", "HEAD", "HEAD~1"]).stdout.split()
    if inst["base_commit"] not in heads:
        raise RuntimeError(f"/testbed is at {heads}, expected {inst['base_commit']}")
    check_isolation(name)

    prompt = (ROOT / "runner" / "prompt.md").read_text().format(problem_statement=inst["problem_statement"].strip())
    (out / "prompt.md").write_text(prompt)

    cmd = ["docker", "exec", "-i", "-w", "/testbed"]
    for k, v in AGENT_ENV.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += [name, "claude", "-p", "--model", MODEL, "--dangerously-skip-permissions",
            "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns)]

    t0 = time.time()
    timed_out = False
    with open(out / "transcript.jsonl", "w") as tf, open(out / "stderr.txt", "w") as ef:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=tf, stderr=ef, text=True)
        try:
            proc.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            sh(["docker", "exec", name, "pkill", "-f", "claude"])
            proc.kill()
            proc.wait()
    wall = round(time.time() - t0, 1)

    # Only tracked, non-test files count: the harness applies its own test patch on top.
    patch = sh(["docker", "exec", name, "git", "-C", "/testbed", "diff", "--", ".", ":(exclude)tests"]).stdout
    (out / "patch.diff").write_text(patch)
    status = sh(["docker", "exec", name, "git", "-C", "/testbed", "status", "--porcelain"]).stdout

    meta = {
        "instance_id": iid,
        "wall_s": wall,
        "timed_out": timed_out,
        "patch_lines": patch.count("\n"),
        "empty_patch": not patch.strip(),
        "touched_tests": any(l[3:].startswith("tests/") for l in status.splitlines()),
        "untracked_files": [l[3:] for l in status.splitlines() if l.startswith("??")],
        **summarize(out / "transcript.jsonl"),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    if not keep:
        sh(["docker", "rm", "-f", name])
    return patch, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--ids", nargs="*", help="default: data/selected.json")
    ap.add_argument("--max-turns", type=int, default=80)
    ap.add_argument("--timeout", type=int, default=45 * 60, help="seconds per issue")
    ap.add_argument("--keep", action="store_true", help="keep containers for debugging")
    args = ap.parse_args()

    ensure_isolated_network()
    ids = args.ids or json.loads((ROOT / "data" / "selected.json").read_text())
    run_dir = ROOT / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    preds_path = run_dir / "predictions.jsonl"
    done = set()
    if preds_path.exists():
        done = {json.loads(l)["instance_id"] for l in preds_path.read_text().splitlines()}

    for inst in load_instances(ids):
        iid = inst["instance_id"]
        if iid in done:
            print(f"skip {iid} (already in predictions)")
            continue
        print(f"=== {iid}", flush=True)
        try:
            patch, meta = run_one(inst, run_dir, args.max_turns, args.timeout, args.keep)
        except Exception as e:
            print(f"    ERROR: {e}", flush=True)
            continue
        with open(preds_path, "a") as f:
            f.write(json.dumps({"instance_id": iid, "model_name_or_path": f"claude-code+{MODEL}", "model_patch": patch}) + "\n")
        print(f"    {meta['wall_s']}s, {meta['num_turns']} turns, patch {meta['patch_lines']} lines, "
              f"max prompt {meta['max_prompt_tokens']} tok, timed_out={meta['timed_out']}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
