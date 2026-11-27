# AI Assistant Setup Prompt

Paste the prompt below into your AI coding assistant (Claude Code, Codex, Cursor, Antigravity, or Copilot) and replace `<PROXY_URL>` and `<YOUR_API_KEY>` with your own credentials:

```text
Please set up `llm-provider-router` cleanly on this machine so I have a working AI LLM provider ready to use:

1. Clone https://github.com/productaivn-wq/llm-provider-router.git into a local folder (e.g., ~/tools/llm-provider-router) and cd into it.
2. Create a Python 3.10+ virtual environment (`.venv`), activate it, and install the package (`pip install -e .`).
3. Configure my credentials securely via stdin (do NOT echo or commit my API key, and keep `.env` permissions restricted):
   Run:
   llm-router setup --url <PROXY_URL> --api-key-stdin --model chatgpt/gpt-5.3-instant --coding-model chatgpt/gpt-5.3-codex --user-agent LLM-Provider-Router/1.0 --probe --json
   using this API key via stdin: <YOUR_API_KEY>
4. Run `llm-router models` and a quick test prompt with `llm-router chat "Reply OK if connected"` to verify end-to-end inference works.
5. Tell me the installed directory path, available models count, test output, and how to start the optional local OpenAI-compatible gateway (`llm-router serve` on http://127.0.0.1:18766/v1) if my IDE tools need a local endpoint. Keep all API keys masked in any output.
```
