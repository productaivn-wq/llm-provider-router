# One-Shot AI Setup Prompt — Tech Audience (DEV / DEVOPS / SEC / DATA)

Visual guide ("Why & What To Do Next"): [docs/VISUAL_GUIDE_VI.md](VISUAL_GUIDE_VI.md)

Paste this streamlined 1-shot prompt into your AI coding assistant (Antigravity, Claude Code, Codex, Cursor, or Copilot), replacing `<PROXY_URL>` and `<YOUR_API_KEY>`:

```text
Set up and auto-connect `llm-provider-router` on this machine in ONE automated pass (Zero UTF-8/BOM bugs, persistent background gateway, Web UI + tool auto-wiring):

1. Force UTF-8 first:
   - PowerShell: `[Console]::InputEncoding = [Console]::OutputEncoding = $OutputEncoding = [System.Text.UTF8Encoding]::new($false); $env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'`
   - POSIX: `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 LANG=C.UTF-8`
2. Target directory: `%USERPROFILE%\llm-provider-router` (Windows) or `~/llm-provider-router` (macOS/Linux).
   Clone `https://github.com/productaivn-wq/llm-provider-router.git` (or `git pull --ff-only`; fallback to `archive/refs/heads/main.zip` if `git` is missing).
3. Ensure Python 3.10+ (skip WindowsApps Store stub). Create `.venv` without running `Activate.ps1`:
   - `<VENV_PY>` = `.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (POSIX)
   - `<VENV_PY> -m pip install --upgrade pip`
   - `<VENV_PY> -m pip install -e .`
4. Configure local + global `~/.llm_provider_router/.env` cleanly via Python `subprocess.run(..., input=API_KEY, encoding="utf-8", text=True)` (zero shell escaping or BOM leaks):
   - `<VENV_PY> -m llm_provider_router setup --url <PROXY_URL> --api-key-stdin --model chatgpt/gpt-5.3-instant --coding-model chatgpt/gpt-5.3-codex --user-agent LLM-Provider-Router/1.0 --probe --json`
   - API Key (stdin only, never echo): `<YOUR_API_KEY>`
5. Verify CLI inference:
   - `<VENV_PY> -m llm_provider_router probe --json` (`ok: true`)
   - `<VENV_PY> -m llm_provider_router models --json` (check count)
   - `<VENV_PY> -m llm_provider_router chat "Reply OK if connected" --coding --json`
6. Start detached background gateway, create `Mo_Chat_AI.bat`/`Mo_Cong_AI.bat` (or `.command`), and auto-wire local tools (`OPENAI_BASE_URL`, `~/.codex/config.toml`, `~/.continue/config.json`):
   - `<VENV_PY> -m llm_provider_router connect --start-gateway --install-dir "<TARGET_DIR>" --json`
   - Verify BOTH `GET http://127.0.0.1:18766/` (Web Chat UI) and `GET http://127.0.0.1:18766/v1/models` return HTTP 200.
7. Print a clear Vietnamese next-steps summary (masking all keys):
   - Install folder, model count, chat test result, and `Mo_Chat_AI` / `http://127.0.0.1:18766/` link.
   - Exact list from `connect --json` of which local configs (`auto_connected`) were auto-wired (`OPENAI_BASE_URL`, Codex, Continue).
   - Honest note + 3-field switch (`http://127.0.0.1:18766/v1`, `local-router`, `router/coding` or `router/auto`) if they also want closed GUI IDE apps (Cursor, Antigravity, Cline) to route through the gateway.
```

## Quick Direct Usage Reference (Tech)

- **Web Chat UI & Visual Connection Hub**: `http://127.0.0.1:18766/` (when background gateway is running via `llm-router connect`)
- **Direct Proxy Client (no local daemon needed)**:
  - `OPENAI_BASE_URL=<PROXY_URL>`
  - `OPENAI_API_KEY=<YOUR_API_KEY>`
  - `User-Agent: LLM-Provider-Router/1.0`
- **Local Loopback Gateway (automatic cooldowns & failover)**:
  - Run `llm-router connect --start-gateway` (or `llm-router serve`) -> `http://127.0.0.1:18766/v1`
  - `OPENAI_API_KEY=local-router` (or custom `ROUTER_GATEWAY_TOKEN`)
  - Models: `router/auto`, `router/coding`, `router/fast`, or any upstream model ID
