# AI Assistant Setup Prompts (Audience-Segmented)

Choose the 1-shot setup guide matching your role and paste it into your AI assistant (Antigravity, Claude Code, Codex, Cursor, or GitHub Copilot):

- **Visual Overview ("Why Install & What To Do Next?" in Vietnamese)**:
  - See [docs/VISUAL_GUIDE_VI.md](VISUAL_GUIDE_VI.md)
- **Non-Tech Users** (Business, Product, HR, Finance, Ops, Leadership — zero terminal knowledge needed, UTF-8/BOM safe, 7-phase autonomous runbook + Web Chat UI `Mo_Chat_AI` launcher):
  - See [docs/AI_SETUP_PROMPT_NONTECH.md](AI_SETUP_PROMPT_NONTECH.md)
- **Tech Users** (DEV, DevOps, Security, Data — UTF-8 safe CLI, `llm-router connect` background gateway + Codex/Continue/env auto-wiring + SDK):
  - See [docs/AI_SETUP_PROMPT_TECH.md](AI_SETUP_PROMPT_TECH.md)
- **1-Command Native Installers** (optional direct scripts without AI prompt):
  - Windows PowerShell: `scripts/install.ps1`
  - macOS / Linux: `scripts/install.sh`

## Quick Default 1-Shot Prompt (Tech)

Replace `<PROXY_URL>` and `<YOUR_API_KEY>` with your own credentials:

```text
Please set up `llm-provider-router` cleanly on this machine so I have a working AI LLM provider ready to use:

1. Clone https://github.com/productaivn-wq/llm-provider-router.git into a local folder (e.g., ~/llm-provider-router; fallback to archive/refs/heads/main.zip if git is unavailable) and cd into it.
2. Ensure Python 3.10+ and create `.venv`. On Windows, avoid `Activate.ps1` ExecutionPolicy issues and run `.venv\Scripts\python.exe -m pip install -e .` (or `.venv/bin/python -m pip install -e .` on POSIX).
3. Configure my credentials securely via stdin using Python `subprocess` (do NOT echo or commit my API key, and keep `.env` permissions restricted):
   Run:
   <VENV_PY> -m llm_provider_router setup --url <PROXY_URL> --api-key-stdin --model chatgpt/gpt-5.3-instant --coding-model chatgpt/gpt-5.3-codex --user-agent LLM-Provider-Router/1.0 --probe --json
   passing this API key via stdin: <YOUR_API_KEY>
4. Run `<VENV_PY> -m llm_provider_router models` and `<VENV_PY> -m llm_provider_router chat "Reply OK if connected"` to verify end-to-end inference works.
5. Run `<VENV_PY> -m llm_provider_router connect --start-gateway --json` to start the background gateway, generate `Mo_Chat_AI` / `Mo_Cong_AI` launchers, and auto-wire local tools. Verify `http://127.0.0.1:18766/` (Web Chat UI) and `http://127.0.0.1:18766/v1/models` return HTTP 200, keep all API keys masked, and explain what was auto-connected vs the 3-field switch (`http://127.0.0.1:18766/v1`, `local-router`, `router/auto`) for GUI apps.
```
