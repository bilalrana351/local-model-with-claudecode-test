Claude Code, driven by a local open-weight model, resolved 10 SWE-bench Verified issues out of 13 attempted. Everything runs on one MacBook Pro (M4 Pro, 24 GB). No cloud model is called.

## Pieces

| Part | What | Where |
|---|---|---|
| Model | [Ornith-1.5-35B-A3B](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B) (MoE, 3B active), APEX Compact GGUF, 16.5 GB | Ollama, model name `ornith`, built from `model/Modelfile` |
| Serving | Ollama 0.34 with its Anthropic-compatible `/v1/messages` endpoint, 64K context, `qwen3.5` renderer and parser | `localhost:11434` |
| Agent | Claude Code 2.1.283 pointed at Ollama through `ANTHROPIC_BASE_URL` | `bin/claude-local` (host), `tools/claude-linux-x64` (containers) |
| Tasks | 10 issues sampled with seed 42 from the 16 Django 3.0 issues tagged "<15 min fix", then the rest of that pool in seeded order until 10 were resolved | `data/selected.json`, `data/extra.json` |
| Runner | Starts each issue's official SWE-bench container, runs the agent inside it, saves the diff | `runner/run_agent.py` |
| Grading | Official `swebench` 5.0.2 harness | `runner/evaluate.sh` |

## Setup

Needs an Apple Silicon Mac with 24 GB+ of memory, [Ollama](https://ollama.com) 0.34+, Docker Desktop, [uv](https://docs.astral.sh/uv/), and about 40 GB of free disk. The large pieces are not in this repo; these commands fetch them.

```bash
# 1. Model: download the GGUF (16.5 GB) next to the Modelfile, then build it (see model/Modelfile for the renderer fix)
curl -L -o model/Ornith-1.5-35B-A3B-APEX-Compact.gguf \
  https://huggingface.co/mudler/Ornith-1.5-35B-A3B-APEX-GGUF/resolve/main/Ornith-1.5-35B-A3B-APEX-Compact.gguf
ollama create ornith -f model/Modelfile

# 2. Python env and the SWE-bench Verified dataset
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python swebench datasets
.venv/bin/python -c "from datasets import load_dataset; load_dataset('SWE-bench/SWE-bench_Verified', split='test').to_json('data/verified.jsonl')"

# 3. Linux Claude Code binary that runs inside the containers (version 2.1.283)
mkdir -p tools && curl -L -o tools/claude-linux-x64 \
  https://downloads.claude.ai/claude-code-releases/2.1.283/linux-x64/claude && chmod +x tools/claude-linux-x64

# 4. SWE-bench images for the 10 selected issues and the 6-issue extra pool (x86_64, run under emulation on Apple Silicon)
for id in $(.venv/bin/python -c "import json; print(' '.join(json.load(open('data/selected.json')) + json.load(open('data/extra.json'))))"); do
  docker pull --platform linux/amd64 "swebench/sweb.eval.x86_64.${id/__/_1776_}:latest"
done
```

The runner creates the isolated Docker network and the socat relay itself on first use.

## Run

```bash
.venv/bin/python runner/run_agent.py --run-id run1     # agent attempts, writes runs/run1/
runner/evaluate.sh gold                                # sanity check: reference patches should all pass
runner/evaluate.sh run1                                # grade the agent's patches
runner/until_resolved.sh run1 10                       # attempt data/extra.json one by one until 10 resolved
.venv/bin/python runner/summarize.py run1              # results table: runs/run1/results.md
```

## Result

10 resolved out of 13 attempted (the first 10 gave 7/10; 3 extras from the same pool all resolved). Details in `runs/run1/results.md`.

Each issue gets `runs/<run-id>/<instance_id>/` with the prompt, the full stream-json transcript, the patch, and `meta.json` (turns, time, tool calls, largest prompt).

## Design notes

- **Agent runs inside the issue's container.** The official image already has the repo at `/testbed` on the right commit plus the conda env the tests need, so the agent can run Django's test suite. The container is also the sandbox that makes `--dangerously-skip-permissions` acceptable.
- **No internet in the agent's container.** Containers sit on an internal Docker network (`swe-isolated`). A socat relay aliased as `host.docker.internal` forwards only port 11434 to Ollama, so the agent cannot fetch the upstream fix. This was added mid-run: on `django__django-11433` the agent tried `pip download django==3.0` "to find the actual upstream fix". The download timed out, the attempt was discarded (`runs/run1-aborted/`), and the issue was rerun isolated. In the isolated rerun it tried `WebFetch` on Django's `forms/models.py` on GitHub, which was blocked. The six issues finished before that made no network calls, which was checked in their transcripts.
- **The patch excludes `tests/`.** The harness applies the hidden test patch on top, and edits to test files could conflict with it. The prompt also tells the agent not to touch tests.
- **No hints.** The prompt has only the issue text, not SWE-bench's `hints_text`, which matches the standard setting.
- **Chat template fix.** The GGUF's embedded Jinja template rejects system messages after the first one, and Claude Code sends those. Ollama's built-in `qwen3.5` renderer and parser handle them.
- **64K context.** 128K pushed the model partly onto the CPU on 24 GB. `meta.json` records the largest prompt per issue, so any run that came close to the limit is visible.
