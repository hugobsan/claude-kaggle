# Kaggle Compute: Claude Code plugin

> Unofficial. Not affiliated with or endorsed by Kaggle or Google.

Lets Claude Code offload heavy computation to [Kaggle](https://www.kaggle.com)'s free cloud machines (GPU, CPU and RAM) and bring the results back.

| Skill | What it does |
|---|---|
| `kaggle-compute:setup` | Checks the local environment, installs the Kaggle CLI (after asking), and guides authentication (API token page or OAuth login). |
| `kaggle-compute:run` | Writes a processing plan, builds a parallel job (one worker per GPU or CPU core), pushes it as a private Kaggle notebook, monitors it in the background, collects the outputs and offers to clean up. |

Claude may suggest `kaggle-compute:run` when a task looks too heavy for the local machine (no GPU, long CPU time, not enough RAM). You can also ask directly: *"run this on Kaggle"*.

## Install

```
/plugin marketplace add hugobsan/claude-kaggle
/plugin install kaggle-compute@kaggle-compute
```

## Requirements

- A Kaggle account. Phone verification is needed for internet access inside notebooks.
- Python 3 locally. The setup skill installs the Kaggle CLI after asking you. Validated with Kaggle CLI 2.2.5.
- Linux or macOS shell (bash). Windows: use WSL2.

## What a free account gave us (2026-10-29)

4 vCPU, 31 GB RAM and 20 GB disk per session. GPU sessions add 2× Tesla T4, with a 30 h/week quota. CPU sessions do not use GPU quota. Each session can run up to 12 h. Your account may differ: run `kaggle quota`.

## How results come back

1. Printed in the logs, for small results.
2. Downloaded from `/kaggle/working` when the job ends (the default).
3. Optional: a cloudflared quick tunnel started *inside* the notebook, for live results or to expose a service. The tunnel URL is public, so it is only for non-sensitive outputs.

Jobs always end on their own: a finite work list, a hard timeout (`-t`), and a shutdown route when the tunnel is on.

## Privacy and cleanup

Everything a job uses leaves your machine and is stored in your Kaggle account: input files (uploaded as a private dataset), the job code, logs and outputs. They stay in the private notebook and its version history until deleted. Never put API keys in the job; use Kaggle Secrets. After collecting the results, Claude offers to delete the notebook and any dataset it created (`kaggle kernels delete -y`, `kaggle datasets delete -y`).

## License

MIT
