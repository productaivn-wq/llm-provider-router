# One-Shot AI Setup Prompt — Tech Audience (Orchestrator + OpenAI Sub-Agent)

Visual guide ("Why & What To Do Next"): [docs/VISUAL_GUIDE_VI.md](VISUAL_GUIDE_VI.md)

Paste this streamlined 1-shot prompt into your AI coding assistant (Antigravity, Claude Code, Codex, or Cursor), replacing `<PROXY_URL>` and `<YOUR_API_KEY>`:

```text
Set up `llm-provider-router` and auto-wire Orchestrator -> OpenAI Sub-Agent offloading on this machine in ONE automated pass (UTF-8/BOM safe, zero raw key leaks):

1. Force UTF-8 first:
   - PowerShell: `[Console]::InputEncoding = [Console]::OutputEncoding = $OutputEncoding = [System.Text.UTF8Encoding]::new($false); $env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'`
   - POSIX: `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 LANG=C.UTF-8`
2. Target directory: `%USERPROFILE%\llm-provider-router` (Windows) or `~/llm-provider-router` (macOS/Linux).
   Clone `https://github.com/productaivn-wq/llm-provider-router.git` (or `git pull --ff-only`; fallback to `archive/refs/heads/main.zip` if `git` is missing).
3. Ensure Python 3.10+ (skip WindowsApps Store stub). Create `.venv` without running `Activate.ps1`:
   - `<VENV_PY>` = `.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (POSIX)
   - `<VENV_PY> -m pip install --upgrade pip`
   - `<VENV_PY> -m pip install -e .`
4. Configure local + global `~/.llm_provider_router/.env` cleanly via Python `subprocess.run(..., input=API_KEY, encoding="utf-8", text=True)`:
   - `<VENV_PY> -m llm_provider_router setup --url <PROXY_URL> --api-key-stdin --model chatgpt/gpt-5.3-instant --coding-model chatgpt/gpt-5.3-codex --user-agent LLM-Provider-Router/1.0 --probe --json`
   - API Key (stdin only, never echo): `<YOUR_API_KEY>`
5. Auto-wire Orchestrator rules & skills so this assistant stays Orchestrator while delegating sub-agent tasks to OpenAI:
   - `<VENV_PY> -m llm_provider_router connect --install-dir "<TARGET_DIR>" --python-exe "<VENV_PY>" --json` (also pass `--workspace "<CURRENT_WORKSPACE_DIR>"` if inside a project repo)
6. Verify live delegation end-to-end:
   - `<VENV_PY> -m llm_provider_router models --json`
   - `<VENV_PY> -m llm_provider_router delegate --role coding "Reply OK with the active OpenAI model name" --json` (`ok: true`)
7. Reply with a clear Vietnamese visual summary (masking all keys):
   - Why this setup is active (Claude/AGY/Codex/Cursor stays Orchestrator; heavy drafting/analysis/coding/review/batch subtasks offload to OpenAI via `delegate` & `batch`).
   - Exact files/rules wired (`auto_connected` paths) and verified `models` count + `delegate` test result.
   - Exact next step: open a **new chat session** in your current AI assistant so the new rule/skill loads, and optionally run a 1-sentence delegation check.
```

## Quick CLI Sub-Agent Reference (Tech)

- **Single OpenAI Sub-Agent Task**:
  - `llm-router delegate --role coding "Implement unit tests for parser.py" --context-file src/parser.py --json`
  - Roles: `general`, `writing`, `analysis`, `coding`, `review`
- **Parallel Batch Fan-Out**:
  - `llm-router batch --tasks-file tasks.json --max-workers 4 --json`
- **Direct OpenAI-Compatible Client Headers (optional)**:
  - `OPENAI_BASE_URL=<PROXY_URL>`
  - `OPENAI_API_KEY=<YOUR_API_KEY>`
  - `User-Agent: LLM-Provider-Router/1.0`
