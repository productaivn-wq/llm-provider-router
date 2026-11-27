# LLM Provider Router

A clean, zero-dependency Python 3.10+ multi-provider LLM router and loopback OpenAI-compatible HTTP gateway.

- **Zero external runtime dependencies**: pure Python standard library (`urllib.request`, `http.server`, `sqlite3`, `json`).
- **LiteLLM Proxy first + automatic failover**: supports any OpenAI-compatible proxy (`LITELLM_PROXY_URL`) with automatic fallback to `OpenRouter`, `NVIDIA NIM`, `Groq`, `Cerebras`, `OpenAI Direct`, or optional local CLI agents.
- **SQLite WAL cooldowns & spend breaker**: exponential backoff cooldowns per `(provider, model)`, `Retry-After` support, attempt ring log, and optional daily spend limit.
- **Secret redaction by default**: registered keys, Bearer tokens, and key-value secrets are stripped from logs, gateway errors, and CLI output.
- **Loopback OpenAI-compatible gateway**: run `llm-router serve` to expose `http://127.0.0.1:18766/v1` for SDKs, IDE assistants, or automation scripts.

## Quickstart

### 1. Install

```bash
git clone https://github.com/productaivn-wq/llm-provider-router.git
cd llm-provider-router
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e .
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

This writes a `0600` `.env` file locally (ignored by git) and verifies live `/models` connectivity without printing your API key.

### 3. Verify & Run

```bash
llm-router probe --json
llm-router models
llm-router chat "Summarize three best practices for clean API design."
```

## Local OpenAI-Compatible Gateway

Start the loopback HTTP server on `http://127.0.0.1:18766/v1`:

```bash
llm-router serve
```

Then point any OpenAI-compatible client (such as Cursor, Claude Code, Codex, Continue, or the official OpenAI SDK) to:

- `OPENAI_BASE_URL=http://127.0.0.1:18766/v1`
- `OPENAI_API_KEY=local-router` (or set `ROUTER_GATEWAY_TOKEN` in `.env` to require Bearer auth)
- Model: `router/auto` (or `router/coding`, or any upstream model ID returned by `GET /v1/models`)

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

## Copy-Paste Setup Prompt for Your AI Assistant

See [docs/AI_SETUP_PROMPT.md](docs/AI_SETUP_PROMPT.md) for a self-contained prompt you can paste into any AI coding assistant to install and verify `llm-provider-router` automatically.

## Development & Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest -v
```

## License

MIT — see [LICENSE](LICENSE).
