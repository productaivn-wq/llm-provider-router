# AI Assistant Setup Prompts (Audience-Segmented)

Choose the 1-shot setup guide matching your role and paste it into your AI assistant (Antigravity, Claude Code, Codex, Cursor, or GitHub Copilot):

- **Non-Tech Users** (Business, Product, HR, Finance, Ops, Leadership — zero terminal knowledge needed, 7-phase autonomous runbook with automatic Python/ZIP fallbacks and 1-click launcher):
  - See [docs/AI_SETUP_PROMPT_NONTECH.md](AI_SETUP_PROMPT_NONTECH.md)
- **Tech Users** (DEV, DevOps, Security, Data — streamlined CLI + loopback gateway & SDK integration):
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
4. Run `<VENV_PY> -m llm_provider_router models` and `<VENV_PY> -m llm-provider-router chat "Reply OK if connected"` to verify end-to-end inference works.
5. Create a 1-click launcher (`Mo_Cong_AI.bat` or `Mo_Cong_AI.command`) to run `<VENV_PY> -m llm_provider_router serve` on `http://127.0.0.1:18766/v1`, verify `/v1/models` returns 200, and keep all API keys masked in any output.
```
