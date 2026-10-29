---
name: run
description: Run heavy jobs on Kaggle's free cloud GPUs (2x T4) and CPUs instead of the local machine. Consider it at planning time, BEFORE starting work locally, whenever: the local run would take more than ~5 minutes; you are about to run a neural model (Whisper/speech-to-text, LLMs, embeddings, diffusion, OCR, training) and the machine has no NVIDIA GPU; you are about to download a large model or switch to a smaller/less accurate one just to make local CPU tolerable; or the user can't wait, wants their machine free, or mentions GPU/cloud/Kaggle. Fits any batch work: transcription, inference, audio/video/image processing, data transforms, simulations. Plans the job, runs it in parallel as a private Kaggle notebook, monitors it in the background and brings outputs back. Not for jobs that finish locally in about a minute, interactive work, or data that must not leave the machine.
---

# Run heavy computation on Kaggle

Validated end to end on 2026-10-29 (Kaggle CLI 2.2.5).

## Decide early: before starting any heavy work locally

Run this check while planning, not after a slow local run has started or the user has complained:

1. **Estimate the local run time.** Data size × per-item speed. Check for a GPU with `nvidia-smi`. Neural models on CPU are typically 10–50× slower than on a T4.
2. **Estimate the Kaggle run time.** ~2 min of overhead + upload time + GPU/CPU compute.
3. If the local run takes more than ~5 min, or would block the user's machine, **offer Kaggle first** and show both estimates in one line. Example: "locally ~30 min on CPU; on Kaggle ~5 min with the large model".
4. **Do not lower quality to make local runs bearable** (smaller model, fewer passes) when Kaggle can run the best option fast. Don't download big models locally just to run them on CPU.

## When this beats running locally

Use this skill when **all** of these hold:
- the work is heavy: GPU needed, long CPU time, or high RAM;
- it can run unattended as a script that reads inputs and writes output files;
- sending the inputs to Kaggle is acceptable. Notebooks are private, but the data still leaves the machine: inputs, `job.py`, logs and outputs stay stored in the private notebook (and its version history) and in any dataset you create, until they are deleted. Ask the user if the data looks sensitive.

Expect ~1–2 min of overhead (queueing and boot). Not worth it for jobs that finish locally in about that time.

## 0. Check the environment and the account

```bash
kaggle config view | grep username   # owner for kernel ids; error -> run the `kaggle-compute:setup` skill
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
  - keep the `if __name__ == "__main__"` guard and the `spawn` context;
  - keep heavy imports (torch etc.) inside `process()`, not at the top of the file;
  - **never put API keys or tokens in `job.py`**, `PLAN.md` or the metadata: everything pushed is stored on Kaggle. If the job needs a secret, ask the user to add it as a Kaggle Secret on the notebook and read it with `from kaggle_secrets import UserSecretsClient; UserSecretsClient().get_secret("NAME")`.
- **The job must end on its own.** `TASKS` is finite, and when the tunnel is on, `SERVE_SECONDS` caps how long it stays up after the work. Never write an open-ended loop or a server that only stops on timeout.
- **Inputs**:
  - small inputs: embed them in `job.py`, or download them from a URL in `SETUP`/`process` (internet is on);
  - local files: upload them as a **private dataset** and attach it:
    ```bash
    mkdir <data-dir> && cp <files> <data-dir>/      # e.g. extracted mp3s, not the full videos
    kaggle datasets init -p <data-dir>              # edit dataset-metadata.json: "id": "<username>/<data-slug>", "title"
    kaggle datasets create -p <data-dir> -r zip     # private by default; folders need -r zip|tar
    kaggle datasets status <username>/<data-slug>   # wait for "ready" before pushing the job
    ```
    Add `"<username>/<data-slug>"` to `dataset_sources`. The files appear under `/kaggle/input/`; the job prints the paths on its `INPUT:` line, so check it before trusting a hardcoded path.
- The tunnel is **optional and off by default** (`SERVE_SECONDS = 0`). See step 5 to choose how results come back.

Syntax check: `python3 -c "import ast;ast.parse(open('job.py').read())"`.

## 3. Push

```bash
cd <job-folder>
kaggle kernels push -p . -t <seconds>                              # CPU session
kaggle kernels push -p . -t <seconds> --accelerator NvidiaTeslaT4  # GPU session (T4 x2)
```
**Always pass `-t`.** The CLI has no cancel command, so the timeout is the only brake.

Give the user the notebook link, `https://www.kaggle.com/code/<username>/<slug>`, so they can follow the run or stop it from Kaggle's page.

## 4. Monitor in the background

```bash
# background shell: streams live logs and exits by itself when the session ends
kaggle kernels logs -f <username>/<slug> > <job-folder>/live.log 2>&1
```
Watch the log for both success and failure signals:
```bash
tail -n +1 -F <job-folder>/live.log | grep -E --line-buffered "RESOURCES|INTERNET|TUNNEL_URL|RESULT|DONE|Traceback|Error|Killed|OOM"
```
When `logs -f` exits, the script is done, but Kaggle may report `RUNNING` for a short while as it saves the outputs. Poll for a bounded time:
```bash
for i in $(seq 12); do s=$(kaggle kernels status <username>/<slug> 2>&1); echo "$s" | grep -q RUNNING || break; sleep 10; done; echo "$s"
# expect: has status "KernelWorkerStatus.COMPLETE" (or ERROR / CANCEL...)
```
If the output has no `KernelWorkerStatus`, the CLI itself failed (auth, network): fix that and retry the status, the job is not necessarily broken. To bound the wait, start the stream as `timeout <-t + 600> kaggle kernels logs -f ...`.
The `SyntaxWarning` lines from mistune/nbconvert in the log are noise from the Kaggle image. Ignore them.

## 5. Collect results

Pick the simplest channel that works, in this order:

1. **Logs**: small results (a metric, a short JSON, a status) can be printed (`print("RESULT:", ...)`) and read straight from `live.log`. Nothing else is needed.
2. **Output download (default for files)**: `kaggle kernels output <username>/<slug> -p <job-folder>/out` downloads everything in `/kaggle/working` plus the run log once the job ends.
3. **cloudflared tunnel (only when needed)**: use it to pull files *while* the job runs (partial or intermediate results from long jobs), or to expose a live service (e.g. a model behind an HTTP API that the agent calls repeatedly). Set `SERVE_SECONDS > 0`, or replace the static file server with your own server. After `TUNNEL_URL:` shows up in the log, run `curl -s <url>/<file>`. The tunnel requires internet.
   - **The tunnel is public**: anyone with the URL can read everything in `/kaggle/working`. Enable it only for non-sensitive outputs, and ask the user first.
   - **Shut it down when done**: `curl -s <url>/__shutdown` ends the job right away instead of waiting out `SERVE_SECONDS`. A custom server must keep an equivalent stop route.
- Check `result.json`: if `summary.failed > 0`, the per-item tracebacks are in `results[].error`. If `summary.crash` is set, a worker died (often out of memory); `missing` counts the items that never ran, and the finished ones are kept in `items-*.jsonl`.
- Logs or status of a specific version: `kaggle kernels status|logs <username>/<slug>/<version>`.

## 6. Shut down and clean up

Once the outputs are collected:
1. Make sure nothing is still running: the status is final, and a tunnel job got its `/__shutdown`.
2. Offer to delete what was created, and only with the user's confirmation:
   - the notebook: `kaggle kernels delete -y <username>/<slug>` (`-y` skips the interactive prompt);
   - any input dataset: `kaggle datasets delete -y <username>/<data-slug>`.

## Known pitfalls

- Missing `__main__` guard with `spawn`: every worker re-runs the script. The job dies with `BrokenProcessPool` and status ERROR after ~17 s.
- Unknown: whether pushing a new version cancels a running one. Wait for the final status, or use different slugs for parallel jobs.
