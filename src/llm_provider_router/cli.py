"""Command-line interface (`llm-router`) for setup, status, probing, chat, and local gateway."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from .config import (
    default_global_env_path,
    load_dotenv_file,
    normalize_openai_base_url,
    redact_secrets,
    register_runtime_secret,
    sanitize_header_value,
    validate_outbound_url,
)
from .connect import connect_clients
from .gateway import LocalOpenAIGateway
from .providers import AllProvidersFailedError
from .router import LLMProviderRouter


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _read_stdin_text_safe() -> str:
    """Read stdin safely across UTF-8, UTF-8 BOM, Windows UTF-16 LE/BE BOM, and StringIO."""
    buf = getattr(sys.stdin, "buffer", None)
    if buf is not None:
        raw = buf.read()
        if isinstance(raw, bytes):
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                return raw.decode("utf-16", errors="replace")
            if raw.startswith(b"\xef\xbb\xbf"):
                return raw.decode("utf-8-sig", errors="replace")
            return raw.decode("utf-8", errors="replace")
    return sys.stdin.read()


def _write_env_secure(path: Path, values: dict[str, str]) -> None:
    """Write a `0600` `.env` file preserving non-conflicting existing entries."""
    existing: dict[str, str] = {}
    if path.is_file():
        existing = load_dotenv_file(path, override=False)
    merged = dict(existing)
    merged.update({k: v for k, v in values.items() if v != ""})

    ordered_keys = [
        "LITELLM_PROXY_URL",
        "LITELLM_API_KEY",
        "LITELLM_MODEL",
        "LITELLM_CODING_MODEL",
        "LITELLM_USER_AGENT",
        "LITELLM_TIMEOUT",
        "OPENROUTER_API_KEY",
        "NVIDIA_API_KEY",
        "GROQ_API_KEY",
        "CEREBRAS_API_KEY",
        "OPENAI_API_KEY",
        "ROUTER_GATEWAY_HOST",
        "ROUTER_GATEWAY_PORT",
        "ROUTER_GATEWAY_TOKEN",
    ]
    lines: list[str] = []
    seen: set[str] = set()
    for k in ordered_keys:
        if k in merged:
            lines.append(f"{k}={merged[k]}")
            seen.add(k)
    for k, v in merged.items():
        if k not in seen:
            lines.append(f"{k}={v}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _cmd_setup(args: argparse.Namespace) -> int:
    try:
        proxy_url = normalize_openai_base_url(
            sanitize_header_value(args.url or "", field_name="proxy URL", require_ascii=True)
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not proxy_url and sys.stdin.isatty():
        proxy_url = normalize_openai_base_url(
            sanitize_header_value(
                input("LiteLLM Proxy URL (e.g. https://proxy.example.com/v1): "),
                field_name="proxy URL",
                require_ascii=True,
            )
        )
    ok_url, reason = validate_outbound_url(proxy_url, allow_loopback=True)
    if not ok_url:
        print(json.dumps({"ok": False, "error": f"Invalid proxy URL: {reason}"}), file=sys.stderr)
        return 2

    raw_api_key = args.api_key or ""
    if not raw_api_key and args.api_key_stdin:
        raw_api_key = _read_stdin_text_safe()
    if not raw_api_key and sys.stdin.isatty():
        raw_api_key = getpass.getpass("Personal API Key (input hidden): ")

    try:
        api_key = (
            sanitize_header_value(raw_api_key, field_name="API key", require_ascii=True)
            if raw_api_key.strip()
            else ""
        )
        user_agent = (
            sanitize_header_value(args.user_agent, field_name="User-Agent", require_ascii=True)
            or "LLM-Provider-Router/1.0"
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    if api_key:
        register_runtime_secret(api_key)

    env_path = Path(args.env_file).expanduser()
    updates: dict[str, str] = {
        "LITELLM_PROXY_URL": proxy_url,
        "LITELLM_MODEL": args.model,
        "LITELLM_CODING_MODEL": args.coding_model,
        "LITELLM_USER_AGENT": user_agent,
    }
    if api_key:
        updates["LITELLM_API_KEY"] = api_key

    _write_env_secure(env_path, updates)
    global_env_path = default_global_env_path()
    synced_global = False
    if not getattr(args, "no_global_env", False) and env_path.resolve() != global_env_path.resolve():
        _write_env_secure(global_env_path, updates)
        synced_global = True

    summary: dict[str, Any] = {
        "ok": True,
        "env_file": str(env_path),
        "global_env_file": str(global_env_path) if synced_global else str(env_path),
        "proxy_url": proxy_url,
        "default_model": args.model,
        "coding_model": args.coding_model,
        "api_key_configured": bool(api_key or env_path.is_file()),
    }

    if args.probe:
        with LLMProviderRouter(env_file=env_path) as router:
            summary["probe"] = router.probe()
        if not summary["probe"].get("ok"):
            summary["ok"] = False

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Configured {env_path} for {proxy_url} (API key saved securely, never echoed).")
        if "probe" in summary:
            p = summary["probe"]
            print(
                f"Live probe: ok={p.get('ok')} healthy={p.get('healthy_count')}/{p.get('configured_count')}"
            )

    return 0 if summary["ok"] else 1


def _cmd_status(args: argparse.Namespace) -> int:
    with LLMProviderRouter(env_file=args.env_file) as router:
        data = router.status()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        active = [p["name"] for p in data["providers"] if p["available"]]
        print(
            f"Router ready={data['ok']} | active_providers={active} | cooldowns={len(data['active_cooldowns'])}"
        )
    return 0 if data["ok"] else 1


def _cmd_probe(args: argparse.Namespace) -> int:
    with LLMProviderRouter(env_file=args.env_file) as router:
        data = router.probe(timeout=args.timeout)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for p in data["providers"]:
            print(
                f"[{p['provider']}] ok={p['ok']} http={p['http_status']} models={p['models_count']} ({p['latency_ms']}ms)"
            )
    return 0 if data["ok"] else 1


def _cmd_models(args: argparse.Namespace) -> int:
    with LLMProviderRouter(env_file=args.env_file) as router:
        models = router.list_models(provider=args.provider)
    if args.json:
        print(json.dumps({"count": len(models), "models": models}, ensure_ascii=False, indent=2))
    else:
        for m in models:
            print(f"{m['provider']}\t{m['id']}")
        if not models:
            print("No models returned. Run 'llm-router probe --json' to inspect connectivity.")
    return 0


def _cmd_chat(args: argparse.Namespace) -> int:
    with LLMProviderRouter(env_file=args.env_file) as router:
        try:
            res = router.complete(
                args.prompt,
                system_prompt=args.system,
                model=args.model,
                for_coding=args.coding,
                timeout=args.timeout,
            )
        except AllProvidersFailedError as exc:
            err = {"ok": False, "error": redact_secrets(str(exc))}
            print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
            return 1

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "provider": res.provider,
                    "model": res.model,
                    "content": res.content,
                    "usage": {
                        "prompt_tokens": res.prompt_tokens,
                        "completion_tokens": res.completion_tokens,
                        "total_tokens": res.total_tokens,
                    },
                    "latency_ms": round(res.latency_ms, 2),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(res.content)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    with LLMProviderRouter(env_file=args.env_file) as router:
        host = args.host or router.config.gateway_host
        port = router.config.gateway_port if args.port is None else args.port
        gw = LocalOpenAIGateway(
            router, host=host, port=port, gateway_token=router.config.gateway_token
        )
        bound_host, bound_port = gw.server_address[:2]
        print(
            f"LLM Router gateway listening on http://{bound_host}:{bound_port}/v1 (Ctrl+C to stop)"
        )
        try:
            gw.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            gw.server_close()
    return 0


def _cmd_reset_cooldowns(args: argparse.Namespace) -> int:
    with LLMProviderRouter(env_file=args.env_file) as router:
        cleared = router.state.clear_cooldowns(provider=args.provider)
    print(json.dumps({"ok": True, "cleared": cleared}))
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    res = connect_clients(
        env_file=Path(args.env_file).expanduser() if args.env_file else None,
        install_dir=Path(args.install_dir).expanduser() if args.install_dir else None,
        start_gateway=bool(args.start_gateway),
        clients=args.clients,
        open_ui=bool(args.open_ui),
        dry_run=bool(args.dry_run),
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(
            f"Gateway ready at {res['gateway_url']} | Chat UI: {res['chat_ui_url']} "
            f"(running={res['gateway'].get('running')})"
        )
    return 0 if res.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="llm-router", description="Zero-dependency multi-provider LLM Router CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup", help="Write local 0600 .env configuration cleanly")
    p_setup.add_argument("--url", help="LiteLLM or OpenAI-compatible proxy base URL")
    p_setup.add_argument(
        "--api-key", help="API key (prefer --api-key-stdin or prompt to keep shell history clean)"
    )
    p_setup.add_argument("--api-key-stdin", action="store_true", help="Read API key from stdin")
    p_setup.add_argument("--model", default="chatgpt/gpt-5.3-instant", help="Default chat model")
    p_setup.add_argument(
        "--coding-model", default="chatgpt/gpt-5.3-codex", help="Default coding model"
    )
    p_setup.add_argument(
        "--user-agent", default="LLM-Provider-Router/1.0", help="HTTP User-Agent header"
    )
    p_setup.add_argument("--env-file", default=".env", help="Target .env file path")
    p_setup.add_argument(
        "--no-global-env",
        action="store_true",
        help="Do not sync settings to ~/.llm_provider_router/.env",
    )
    p_setup.add_argument("--probe", action="store_true", help="Run live probe after writing .env")
    p_setup.add_argument("--json", action="store_true", help="Emit JSON output")
    p_setup.set_defaults(func=_cmd_setup)

    p_status = sub.add_parser(
        "status", help="Show configured providers, cooldowns, and daily spend"
    )
    p_status.add_argument("--env-file", default=None, help="Path to .env file")
    p_status.add_argument("--json", action="store_true", help="Emit JSON output")
    p_status.set_defaults(func=_cmd_status)

    p_probe = sub.add_parser(
        "probe", help="Test live connectivity and auth across configured providers"
    )
    p_probe.add_argument("--env-file", default=None, help="Path to .env file")
    p_probe.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_probe.add_argument("--json", action="store_true", help="Emit JSON output")
    p_probe.set_defaults(func=_cmd_probe)

    p_models = sub.add_parser("models", help="List live models from configured providers")
    p_models.add_argument("--env-file", default=None, help="Path to .env file")
    p_models.add_argument("--provider", default=None, help="Filter to a single provider name")
    p_models.add_argument("--json", action="store_true", help="Emit JSON output")
    p_models.set_defaults(func=_cmd_models)

    p_chat = sub.add_parser("chat", help="Send a single chat prompt through the router")
    p_chat.add_argument("prompt", help="User prompt text")
    p_chat.add_argument("--system", default=None, help="Optional system prompt")
    p_chat.add_argument("--model", default=None, help="Model name or router/auto | router/coding")
    p_chat.add_argument("--coding", action="store_true", help="Prefer coding model")
    p_chat.add_argument("--timeout", type=float, default=None, help="Request timeout in seconds")
    p_chat.add_argument("--env-file", default=None, help="Path to .env file")
    p_chat.add_argument("--json", action="store_true", help="Emit JSON output")
    p_chat.set_defaults(func=_cmd_chat)

    p_serve = sub.add_parser("serve", help="Run loopback OpenAI-compatible HTTP gateway")
    p_serve.add_argument("--host", default=None, help="Loopback host (127.0.0.1, localhost, ::1)")
    p_serve.add_argument("--port", type=int, default=None, help="Listening port (default 18766)")
    p_serve.add_argument("--env-file", default=None, help="Path to .env file")
    p_serve.set_defaults(func=_cmd_serve)

    p_reset = sub.add_parser("reset-cooldowns", help="Clear persisted provider cooldown timers")
    p_reset.add_argument("--provider", default=None, help="Optional single provider to clear")
    p_reset.add_argument("--env-file", default=None, help="Path to .env file")
    p_reset.set_defaults(func=_cmd_reset_cooldowns)

    p_connect = sub.add_parser(
        "connect",
        help="Start background gateway, generate 1-click Web Chat UI launchers, and auto-wire local AI tools",
    )
    p_connect.add_argument(
        "--start-gateway",
        dest="start_gateway",
        action="store_true",
        default=True,
        help="Start detached loopback gateway in background if not running (default)",
    )
    p_connect.add_argument(
        "--no-start-gateway",
        dest="start_gateway",
        action="store_false",
        help="Only write launchers and wire tool configs without spawning gateway",
    )
    p_connect.add_argument(
        "--clients",
        default="auto",
        help="Comma-separated clients to auto-wire: auto, shell, codex, continue",
    )
    p_connect.add_argument("--install-dir", default=None, help="Folder for 1-click launchers")
    p_connect.add_argument("--env-file", default=None, help="Path to .env file")
    p_connect.add_argument("--open-ui", action="store_true", help="Open Web Chat UI in browser")
    p_connect.add_argument("--dry-run", action="store_true", help="Preview without modifying files")
    p_connect.add_argument("--json", action="store_true", help="Emit JSON output")
    p_connect.set_defaults(func=_cmd_connect)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    _configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
