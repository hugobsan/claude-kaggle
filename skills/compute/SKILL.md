---
name: compute
description: Offload heavy computation to Kaggle's free cloud machines (GPU, CPU and RAM) and bring the results back. Use whenever a task is computationally expensive for the local machine — needs a GPU the machine lacks, would take many minutes/hours of local CPU, needs more RAM than is available, or would block the user's machine — and the work can run as a batch script with inputs that can be uploaded or downloaded. Typical fits: ML inference or training, transcription, embeddings, image/audio/video processing, large data transforms, simulations, brute-force searches, any embarrassingly parallel batch. Also use when the user asks to "run this on Kaggle", "use a free GPU", "run it in the cloud", or "don't run this locally". The skill writes a processing plan, builds a parallel job (one worker per GPU or per CPU core), pushes it as a Kaggle notebook, monitors it in the background, and collects outputs (download, or live via a cloudflared tunnel started inside the notebook). Not for interactive/low-latency work, tasks that finish locally in about a minute, or data that must not leave the user's machine.
---

# Run heavy computation on Kaggle

Validated end to end on 2026-10-29 (Kaggle CLI 2.2.5).

## When this beats running locally

Use this skill when **all** of these hold:
- the work is heavy: GPU needed, long CPU time, or high RAM;
- it can run unattended as a script that reads inputs and writes output files;
- sending the inputs to Kaggle is acceptable. Notebooks are private, but the data still leaves the machine. Ask the user if the data looks sensitive.

Expect ~1–2 min of overhead (queueing and boot). Not worth it for jobs that finish locally in about that time.

## 0. Check the environment and the account

```bash
kaggle config view | grep username   # owner for kernel ids; error -> run the `kaggle:setup` skill
kaggle quota                         # this account's accelerator quotas
```
Resources vary by account (paid tiers, verification, policy changes). **Do not trust the numbers below: check `kaggle quota` and the `RESOURCES:` line each job prints first.**

Observed on a free, phone-verified account on 2026-10-29:

| Session | Accelerator flag | CPU | RAM | Disk (/kaggle/working) | Quota |
|---|---|---|---|---|---|
| CPU | none (`enable_gpu: false`) | 4 vCPU | 31 GB | 20 GB | not shown in `kaggle quota` |
| GPU | `--accelerator NvidiaTeslaT4` | 4 vCPU + 2× Tesla T4 (16 GB each) | 31 GB | 20 GB | 30 h/week |
| TPU | e.g. `--accelerator TpuV5E8` (untested) | — | — | — | 20 h/week |

- One CPU session and one GPU session ran at the same time without issue.
- Maximum run time per session is 12 h.
- Internet works with `enable_internet: "true"`. It requires a phone-verified account.
- The image ships Python 3.13 with torch + CUDA preinstalled.
- Pick CPU sessions for CPU-bound work. They don't spend GPU quota.

## 1. Write the plan

Create a job folder (scratch/temp or inside the project). Write `PLAN.md` with:
- the goal, inputs (where they come from) and expected outputs (files written to `/kaggle/working`);
- the processing steps;
- the parallelism: how `TASKS` splits across workers (one per GPU, or one per CPU core);
- session type (CPU or GPU), the estimated time and the `-t` timeout.

Summarize the plan for the user in a few lines and proceed, unless they asked to review it first.

## 2. Build the job

Copy `template/job.py` and `template/kernel-metadata.json` (next to this SKILL.md) into the job folder.

- `kernel-metadata.json`:
  - set `id` to `<username>/<slug>` and `title` to the same slug. Reusing a slug creates a new version of the same notebook;
  - for a CPU session, set `enable_gpu` to `"false"`.
- `job.py`:
  - fill in `SETUP` (pip installs), `TASKS` (work items) and `process(item, device)`. `device` is `"cuda:N"` on GPU sessions and `"cpu"` on CPU sessions;
  - workers are started automatically: one per GPU, or one per CPU core;
  - keep the `if __name__ == "__main__"` guard and the `spawn` context.
- **Inputs**:
  - small inputs: embed them in `job.py`, or download them from a URL in `SETUP`/`process` (internet is on);
  - large inputs: create a private dataset (`kaggle datasets create`), list it in `dataset_sources`, and read it from `/kaggle/input/<slug>`. Not yet validated.
- The tunnel is **optional and off by default** (`SERVE_SECONDS = 0`). See step 5 to choose how results come back.

Syntax check: `python3 -c "import ast;ast.parse(open('job.py').read())"`.

## 3. Push

```bash
cd <job-folder>
kaggle kernels push -p . -t <seconds>                              # CPU session
kaggle kernels push -p . -t <seconds> --accelerator NvidiaTeslaT4  # GPU session (T4 x2)
```
**Always pass `-t`.** The CLI has no cancel command, so the timeout is the only brake.

## 4. Monitor in the background

```bash
# background shell: streams live logs and exits by itself when the session ends
kaggle kernels logs -f <username>/<slug> > <job-folder>/live.log 2>&1
```
Watch the log for both success and failure signals:
```bash
tail -n +1 -F <job-folder>/live.log | grep -E --line-buffered "RESOURCES|INTERNET|TUNNEL_URL|RESULT|DONE|Traceback|Error|Killed|OOM"
```
Wait for the final status (background loop):
```bash
until s=$(kaggle kernels status <username>/<slug> 2>&1); echo "$s" | grep -qiE "COMPLETE|ERROR|CANCEL"; do sleep 20; done; echo "$s"
```
The `SyntaxWarning` lines from mistune/nbconvert in the log are noise from the Kaggle image. Ignore them.

## 5. Collect results

Pick the simplest channel that works, in this order:

1. **Logs**: small results (a metric, a short JSON, a status) can be printed (`print("RESULT:", ...)`) and read straight from `live.log`. Nothing else is needed.
2. **Output download (default for files)**: `kaggle kernels output <username>/<slug> -p <job-folder>/out` downloads everything in `/kaggle/working` plus the run log once the job ends.
3. **cloudflared tunnel (only when needed)**: use it to pull files *while* the job runs (partial or intermediate results from long jobs), or to expose a live service (e.g. a model behind an HTTP API that the agent calls repeatedly). Set `SERVE_SECONDS > 0`, or replace the static file server with your own server. After `TUNNEL_URL:` shows up in the log, run `curl -s <url>/<file>`. The tunnel lives only while the session runs, and it requires internet.
- Check `result.json`: if `summary.failed > 0`, the per-item tracebacks are in `results[].error`.
- Logs or status of a specific version: `kaggle kernels status|logs <username>/<slug>/<version>`.

## Known pitfalls

- Missing `__main__` guard with `spawn`: every worker re-runs the script. The job dies with `BrokenProcessPool` and status ERROR after ~17 s.
- Unknown: whether pushing a new version cancels a running one. Wait for the final status, or use different slugs for parallel jobs.
- Test notebooks pile up in the account. Offer to delete them with `kaggle kernels delete -y <username>/<slug>` (`-y` skips the interactive prompt), and only with the user's confirmation.
