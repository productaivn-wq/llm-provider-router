# LLM Provider Router

A clean, zero-dependency Python 3.10+ multi-provider LLM router and **Orchestrator + OpenAI Sub-Agent** delegation engine for Antigravity (AGY), Claude Code, Codex, and Cursor.

- **Zero external runtime dependencies**: pure Python standard library (`urllib.request`, `http.server`, `sqlite3`, `json`).
- **Orchestrator + OpenAI Sub-Agent architecture**: keep Antigravity, Claude Code, Codex, or Cursor as your main reasoning **Orchestrator** while automatically offloading sub-agent tasks (`llm-router delegate` and parallel `llm-router batch`) to company OpenAI models (`chatgpt/gpt-6.2-sol`, `chatgpt/gpt-6.2-astra`) with automatic failover across 10 verified models.
- **Automatic rule & skill wiring (`llm-router connect`)**: installs always-on rules/skills across Antigravity (`~/.gemini/config/rules/llm-router-subagent.md` + `SKILL.md`), Claude Code (`~/.claude/CLAUDE.md` + `agents/openai-worker.md`), Codex (`~/.codex/AGENTS.md` + `config.toml`), and Cursor (`.cursor/rules/llm-router-subagent.mdc`).
- **UTF-8 / BOM safe on Windows**: automatically handles UTF-8 BOM, UTF-16 LE/BE BOM, smart quotes, and zero-width characters in `.env`, stdin, context files, and HTTP headers.
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
  --model chatgpt/gpt-6.2-sol \
  --coding-model chatgpt/gpt-6.2-astra \
  --probe
```

This writes a `0600` `.env` file locally plus `~/.llm_provider_router/.env` (so `llm-router` works from any working directory) and verifies live `/models` connectivity without printing your API key.

## Verified Working Models (10/25 HTTP 200 OK)

Default chat (`general` / `writing` / `analysis`) uses `chatgpt/gpt-6.2-sol`; default coding (`coding` / `review`) uses `chatgpt/gpt-6.2-astra`, with automatic failover across all 10 verified models:

- `chatgpt/gpt-6.2-sol` (default chat)
- `chatgpt/gpt-6.2-astra` (default coding)
- `chatgpt/gpt-6-sol`
- `chatgpt/gpt-6-astra`
- `chatgpt/gpt-6-luna`
- `chatgpt/gpt-6.1-sol`
- `chatgpt/gpt-6.1-terra`
- `chatgpt/gpt-5.6-sol`
- `chatgpt/gpt-5.6-luna`
- `chatgpt/gpt-5.6-terra`

### 3. Auto-Wire Orchestrator Rules & Test OpenAI Sub-Agent Delegation

```bash
llm-router connect --json
llm-router delegate --role writing "Confirm OpenAI sub-agent connection in one sentence." --json
llm-router delegate --role coding "Write a Python function to parse ISO-8601 UTC timestamps." --json
```

For parallel fan-out across independent sub-tasks:

```bash
llm-router batch --tasks-file tasks.json --max-workers 4 --json
```

### Direct OpenAI-Compatible Client Usage (Optional)

If a script or client needs raw OpenAI proxy credentials:

- **Base URL**: `https://your-litellm-proxy.example.com/v1`
- **API Key**: `<YOUR_API_KEY>`
- **Header (`User-Agent`)**: `LLM-Provider-Router/1.0`

## Python SDK

```python
from llm_provider_router import LLMProviderRouter, run_delegate

res = run_delegate("Summarize key risks concisely.", role="analysis")
print(res["content"])

with LLMProviderRouter() as router:
    out = router.complete("Write a haiku about reliable systems.")
    print(f"Served by {out.provider} / {out.model}")
```

## 1-Shot Setup Prompts, Visual Guide & Installers

- **Visual Guide ("Why Install & What To Do Next?" in Vietnamese)**: [docs/VISUAL_GUIDE_VI.md](docs/VISUAL_GUIDE_VI.md)
- **Non-Tech Users (1-Shot Autonomous Runbook)**: [docs/AI_SETUP_PROMPT_NONTECH.md](docs/AI_SETUP_PROMPT_NONTECH.md)
- **Tech Users (1-Shot Runbook + Delegate/Batch + SDK)**: [docs/AI_SETUP_PROMPT_TECH.md](docs/AI_SETUP_PROMPT_TECH.md)
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
