# AI Assistant Setup Prompts (Audience-Segmented)

Choose the 1-shot setup guide matching your role and paste it into your AI assistant (Antigravity, Claude Code, Codex, or Cursor):

- **Visual Overview ("Why Install & What To Do Next?" in Vietnamese)**:
  - See [docs/VISUAL_GUIDE_VI.md](VISUAL_GUIDE_VI.md)
- **Non-Tech Users** (Business, Product, HR, Finance, Ops, Leadership — zero terminal knowledge needed, UTF-8/BOM safe, 7-phase autonomous runbook that wires your current AI assistant as Orchestrator + OpenAI Sub-Agent):
  - See [docs/AI_SETUP_PROMPT_NONTECH.md](AI_SETUP_PROMPT_NONTECH.md)
- **Tech Users** (DEV, DevOps, Security, Data — UTF-8 safe CLI, `llm-router connect` auto-wiring for AGY / Claude / Codex / Cursor, `delegate` & `batch` sub-agents + SDK):
  - See [docs/AI_SETUP_PROMPT_TECH.md](AI_SETUP_PROMPT_TECH.md)
- **1-Command Native Installers** (optional direct scripts without AI prompt):
  - Windows PowerShell: `scripts/install.ps1`
  - macOS / Linux: `scripts/install.sh`

## Quick Default 1-Shot Prompt (Tech)

Replace `<PROXY_URL>` and `<YOUR_API_KEY>` with your own credentials:

```text
Set up `llm-provider-router` and auto-wire Orchestrator -> OpenAI Sub-Agent offloading on this machine:

1. Force UTF-8 (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`), clone https://github.com/productaivn-wq/llm-provider-router.git into `~/llm-provider-router` (or `%USERPROFILE%\llm-provider-router`; fallback to archive/refs/heads/main.zip if git is unavailable), and create `.venv` without running `Activate.ps1`.
2. Run `<VENV_PY> -m pip install -e .` and configure credentials cleanly via stdin using Python `subprocess` (never echo or commit API keys):
   `<VENV_PY> -m llm_provider_router setup --url <PROXY_URL> --api-key-stdin --model chatgpt/gpt-6.2-sol --coding-model chatgpt/gpt-6.2-astra --user-agent LLM-Provider-Router/1.0 --probe --json`
   API Key via stdin: `<YOUR_API_KEY>`
3. Auto-wire rules & skills for Antigravity, Claude Code, Codex, and Cursor:
   `<VENV_PY> -m llm_provider_router connect --install-dir "<TARGET_DIR>" --python-exe "<VENV_PY>" --json`
4. Verify live OpenAI sub-agent delegation end-to-end:
   `<VENV_PY> -m llm_provider_router delegate --role coding "Reply OK if connected" --json`
5. Report what was auto-wired (`auto_connected`), model count, and remind the user to open a new chat session so the new Orchestrator -> OpenAI Sub-Agent rules take effect immediately. Mask all API keys.
```
