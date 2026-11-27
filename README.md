# LLM Provider Router

A clean, zero-dependency Python 3.10+ multi-provider LLM router, loopback OpenAI-compatible HTTP gateway, and built-in local Web Chat UI.

- **Zero external runtime dependencies**: pure Python standard library (`urllib.request`, `http.server`, `sqlite3`, `json`).
- **UTF-8 / BOM safe on Windows**: automatically handles UTF-8 BOM, UTF-16 BOM, smart quotes, and zero-width characters in `.env`, stdin, and HTTP headers.
- **LiteLLM Proxy first + automatic failover**: supports any OpenAI-compatible proxy (`LITELLM_PROXY_URL`) with automatic fallback to `OpenRouter`, `NVIDIA NIM`, `Groq`, `Cerebras`, `OpenAI Direct`, or optional local CLI agents.
- **Built-in Web Chat UI & 1-click `connect`**: `llm-router connect` starts a persistent detached gateway in the background, serves a Vietnamese Web Chat UI + Connection Hub at `http://127.0.0.1:18766/`, generates `Mo_Chat_AI` / `Mo_Cong_AI` launchers, and safely auto-wires detected local tools (`OPENAI_BASE_URL`, `~/.codex/config.toml`, `~/.continue/config.json`).
- **SQLite WAL cooldowns & spend breaker**: exponential backoff cooldowns per `(provider, model)`, `Retry-After` support, attempt ring log, and optional daily spend limit.
- **Secret redaction by default**: registered keys, Bearer tokens, and key-value secrets are stripped from logs, gateway errors, and CLI output.

## Quickstart

### 1. Install

```bash
git clone https://github.com/productaivn-wq/llm-provider-router.git
cd llm-provider-router
python -m venv .venv
# Windows: .\.venv\Scripts\python.exe -m pip install -e .
# Linux/macOS: ./.venv/bin/python -m pip install -e .
```

### 2. Configure with your proxy URL and API key

```bash
printf "%s" "<YOUR_API_KEY>" | llm-router setup \
  --url https://your-litellm-proxy.example.com/v1 \
  --api-key-stdin \
  --model chatgpt/gpt-5.3-instant \
  --coding-model chatgpt/gpt-5.3-codex \
  --probe
```

This writes a `0600` `.env` file locally (plus global `~/.llm_provider_router/.env` so `llm-router` works from any folder) and verifies live `/models` connectivity without printing your API key.

### 3. Auto-Connect Tools, Start Background Gateway & Open Web Chat UI

```bash
llm-router connect --start-gateway --json
```

Then open `http://127.0.0.1:18766/` (or double-click `Mo_Chat_AI.bat` / `Mo_Chat_AI.command`) to chat immediately or copy the 3-field connection settings (`http://127.0.0.1:18766/v1`, `local-router`, `router/auto`) into Cursor, Antigravity, Cline, or ChatBox.

### 4. Verify CLI

```bash
llm-router probe --json
llm-router models
llm-router chat "Summarize three best practices for clean API design."
```

### Direct OpenAI-Compatible Client Usage (No Local Server Required)

If your tool already supports custom base URLs directly, point it straight at your LiteLLM proxy:

- **Base URL**: `https://your-litellm-proxy.example.com/v1`
- **API Key**: `<YOUR_API_KEY>`
- **Header (`User-Agent`)**: `LLM-Provider-Router/1.0`

## Python SDK

```python
from llm_provider_router import LLMProviderRouter

with LLMProviderRouter() as router:
    res = router.complete("Write a haiku about reliable systems.")
    print(res.content)
    print(f"Served by {res.provider} / {res.model} in {res.latency_ms:.0f}ms")
```

## 1-Shot Setup Prompts, Visual Guide & Installers

- **Visual Guide ("Why Install & What To Do Next?" in Vietnamese)**: [docs/VISUAL_GUIDE_VI.md](docs/VISUAL_GUIDE_VI.md)
- **Non-Tech Users (1-Shot Autonomous Runbook + Web Chat UI)**: [docs/AI_SETUP_PROMPT_NONTECH.md](docs/AI_SETUP_PROMPT_NONTECH.md)
- **Tech Users (CLI + Auto-Connect + IDE Gateway + SDK)**: [docs/AI_SETUP_PROMPT_TECH.md](docs/AI_SETUP_PROMPT_TECH.md)
- **Prompt Index**: [docs/AI_SETUP_PROMPT.md](docs/AI_SETUP_PROMPT.md)
- **Native 1-Command Scripts**: [scripts/install.ps1](scripts/install.ps1) (Windows) and [scripts/install.sh](scripts/install.sh) (macOS/Linux)

## Development & Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest -v
```

## License

MIT - see [LICENSE](LICENSE).
