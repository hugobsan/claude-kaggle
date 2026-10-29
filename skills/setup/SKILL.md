---
name: setup
description: Prepare the local machine to offload computation to Kaggle's free cloud machines (Kaggle CLI + authentication). Use before the `kaggle-compute:run` skill when `kaggle` is not installed, when Kaggle commands fail with "Authentication required", or when the user asks to set up or connect Kaggle. Asks the user before installing anything.
---

# Kaggle setup

Validated on 2026-10-29 (Kaggle CLI 2.2.5).

## 1. Check (read-only)

```bash
command -v kaggle uv pipx; kaggle --version
ls ~/.kaggle/ 2>/dev/null           # access_token (new) or kaggle.json (legacy); never print their contents
kaggle config view | grep username  # error/"Authentication required" -> needs auth
```

Requirements on the **agent's machine**: Python 3, Kaggle CLI ≥ 1.8, authentication. Nothing else.
`cloudflared` is **not** a local requirement. Jobs download and run it *inside* the Kaggle notebook.

## 2. Install the CLI (ask first)

List what is missing and ask the user for confirmation. Then use the first one available:

```bash
uv tool install kaggle      # isolated install, no PEP 668 conflicts
pipx install kaggle
pip install --user kaggle   # last resort; may need --break-system-packages on distros that enforce PEP 668
```

## 3. Authenticate: offer both options

Ask the user which one they prefer.

**A) API token from the settings page**
- If a browser automation tool is available (e.g. claude-in-chrome), open `https://www.kaggle.com/settings/api` (tab *API Tokens*).
- If the user asks you to generate the token: get an explicit yes first (it changes their account), click **Generate New Token**, and name it (e.g. `claude-agent`).
- The modal shows a ready-made command (second block, copy button):
  `mkdir -p ~/.kaggle && echo KGAT_... > ~/.kaggle/access_token && chmod 600 ~/.kaggle/access_token`
  Ask the user to copy it and run it in their own terminal. In Claude Code, they can paste it after a `! ` prefix.
- **Do not read the token from the page yourself** (DOM, JS, page text). Agent safety classifiers block it as credential extraction, and the token should never pass through the agent. Never echo token values.
- Without browser automation, give the user the steps: kaggle.com → avatar → Settings → *API Tokens* → Generate New Token → run the command shown in the modal.

**B) OAuth login (no token to manage)**
- The user runs `kaggle auth login --no-launch-browser` in their terminal, opens the link, authorizes, and pastes the code back. Credentials are cached locally.

For CI or ephemeral environments, `export KAGGLE_API_TOKEN=KGAT_...` also works.

## 4. Verify

```bash
kaggle config view | grep -E "username|auth_method"
kaggle quota          # accelerator quotas for THIS account (paid or verified tiers may differ)
```

Notebook internet (needed for pip installs, downloads and tunnels) requires a phone-verified account: kaggle.com → Settings → Account → Phone verification. A job that prints `INTERNET: False` means this step is missing.

Done. Continue with the **`kaggle-compute:run`** skill.
