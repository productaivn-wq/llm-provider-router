# One-Shot AI Setup Prompt — Tech Audience (DEV / DEVOPS / SEC / DATA)

Paste this streamlined 1-shot prompt into your AI coding assistant (Antigravity, Claude Code, Codex, Cursor, or Copilot), replacing `<PROXY_URL>` and `<YOUR_API_KEY>`:

```text
Set up `llm-provider-router` cleanly on this machine in one automated pass:

1. Target directory: `%USERPROFILE%\llm-provider-router` (Windows) or `~/llm-provider-router` (macOS/Linux).
   Clone `https://github.com/productaivn-wq/llm-provider-router.git` (or pull `--ff-only` if already present; fallback to downloading `archive/refs/heads/main.zip` if `git` is unavailable).
2. Ensure Python 3.10+ is used (skip WindowsApps Store stub). Create `.venv` cleanly.
   Do NOT rely on `Activate.ps1` on Windows; invoke `.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (POSIX) directly:
   - `<VENV_PY> -m pip install --upgrade pip`
   - `<VENV_PY> -m pip install -e .`
3. Write a `0600` `.env` via Python `subprocess.run(..., input=API_KEY, text=True)` so no key hits shell history or stdout:
   - Run `<VENV_PY> -m llm_provider_router setup --url <PROXY_URL> --api-key-stdin --model chatgpt/gpt-5.3-instant --coding-model chatgpt/gpt-5.3-codex --user-agent LLM-Provider-Router/1.0 --probe --json`
   - API Key (stdin only, never print): `<YOUR_API_KEY>`
4. Verify end-to-end:
   - `<VENV_PY> -m llm_provider_router probe --json` (must report `ok: true`)
   - `<VENV_PY> -m llm_provider_router models --json` (list count)
   - `<VENV_PY> -m llm_provider_router chat "Reply OK if connected" --coding --json`
5. Create launcher `Mo_Cong_AI.bat` (Windows) or `Mo_Cong_AI.command` (POSIX, `chmod +x`) running `<VENV_PY> -m llm_provider_router serve`, and verify `GET http://127.0.0.1:18766/v1/models` returns HTTP 200.
6. Report concise setup summary (install path, model count, chat test result, direct proxy headers `User-Agent: LLM-Provider-Router/1.0`, loopback gateway `http://127.0.0.1:18766/v1` with `router/auto` & `router/coding`, and OpenAI SDK snippet). Mask all API keys.
```

## Quick Direct Usage Reference (Tech)

- **Direct Proxy Client (no local daemon needed)**:
  - `OPENAI_BASE_URL=<PROXY_URL>`
  - `OPENAI_API_KEY=<YOUR_API_KEY>`
  - `User-Agent: LLM-Provider-Router/1.0`
- **Local Loopback Gateway (automatic cooldowns & failover)**:
  - Run `llm-router serve` -> `http://127.0.0.1:18766/v1`
  - `OPENAI_API_KEY=local-router` (or custom `ROUTER_GATEWAY_TOKEN`)
  - Models: `router/auto`, `router/coding`, or any upstream model ID
