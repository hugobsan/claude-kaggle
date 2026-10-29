# kaggle — Claude Code plugin

Lets Claude Code offload heavy computation to [Kaggle](https://www.kaggle.com)'s free cloud machines (GPU, CPU and RAM) and bring the results back.

| Skill | What it does |
|---|---|
| `kaggle:setup` | Checks the local environment, installs the Kaggle CLI (after asking), and guides authentication (API token page or OAuth login). |
| `kaggle:compute` | Writes a processing plan, builds a parallel job (one worker per GPU or CPU core), pushes it as a private Kaggle notebook, monitors it in the background and collects the outputs. |

Claude picks `kaggle:compute` on its own when a task is too heavy for the local machine (no GPU, long CPU time, not enough RAM). You can also ask directly: *"run this on Kaggle"*.

## Install

```
/plugin marketplace add hugobsan/claude-kaggle
/plugin install kaggle@kaggle
```

## Requirements

- A Kaggle account. Phone verification is needed for internet access inside notebooks.
- Python 3 locally. The setup skill installs the Kaggle CLI (≥ 1.8) after asking you.

## What a free account gave us (2026-10-29)

4 vCPU, 31 GB RAM and 20 GB disk per session. GPU sessions add 2× Tesla T4, with a 30 h/week quota. CPU sessions do not use GPU quota. Each session can run up to 12 h. Your account may differ: run `kaggle quota`.

## How results come back

1. Printed in the logs, for small results.
2. Downloaded from `/kaggle/working` when the job ends (the default).
3. Optional: a cloudflared quick tunnel started *inside* the notebook, for live results or to expose a service.

## License

MIT
