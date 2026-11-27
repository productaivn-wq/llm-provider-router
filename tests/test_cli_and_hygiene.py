"""Tests for CLI commands, secret-free setup output, and package code hygiene."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

from llm_provider_router import __version__, cli


def test_cli_setup_writes_env_without_echoing_secret(tmp_path: Path, capsys, monkeypatch) -> None:
    fake_secret = "-".join(["sk", "cli", "VerySecretTestKey12345"])
    env_path = tmp_path / ".env"
    monkeypatch.setenv("ROUTER_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setattr("sys.stdin", io.StringIO(fake_secret))

    rc = cli.main(
        [
            "setup",
            "--url",
            "https://proxy.example.com/v1",
            "--api-key-stdin",
            "--env-file",
            str(env_path),
            "--json",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert fake_secret not in captured.out
    assert fake_secret not in captured.err

    data = json.loads(captured.out)
    assert data["ok"] is True
    assert data["api_key_configured"] is True

    written = env_path.read_text(encoding="utf-8")
    assert f"LITELLM_API_KEY={fake_secret}" in written
    assert "LITELLM_PROXY_URL=https://proxy.example.com/v1" in written

    # Re-running setup without passing a new key preserves existing LITELLM_API_KEY
    rc2 = cli.main(
        [
            "setup",
            "--url",
            "https://proxy2.example.com/v1",
            "--env-file",
            str(env_path),
            "--json",
        ]
    )
    assert rc2 == 0
    capsys.readouterr()
    written2 = env_path.read_text(encoding="utf-8")
    assert f"LITELLM_API_KEY={fake_secret}" in written2
    assert "LITELLM_PROXY_URL=https://proxy2.example.com/v1" in written2


def test_cli_status_and_reset_cooldowns(tmp_path: Path, capsys, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LITELLM_PROXY_URL=http://127.0.0.1:18999/v1\n", encoding="utf-8")
    monkeypatch.setenv("ROUTER_STATE_DB", str(tmp_path / "state.db"))

    assert cli.main(["status", "--env-file", str(env_path), "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["ok"] is True

    assert cli.main(["reset-cooldowns", "--env-file", str(env_path)]) == 0
    rc_out = json.loads(capsys.readouterr().out)
    assert rc_out["ok"] is True


def test_source_tree_has_clean_ast_and_no_print_leaks() -> None:
    assert __version__ == "1.0.0"
    src_dir = Path(__file__).resolve().parents[1] / "src" / "llm_provider_router"
    for py_file in sorted(src_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.ExceptHandler) or node.type is not None, (
                f"Bare except in {py_file.name}"
            )
            if py_file.name != "cli.py" and isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "print", f"Disallowed print() in {py_file.name}"
                    assert node.func.id not in ("eval", "exec"), (
                        f"Disallowed {node.func.id}() in {py_file.name}"
                    )


def test_documented_cli_commands_parse_cleanly() -> None:
    parser = cli.build_parser()
    samples = [
        [
            "setup",
            "--url",
            "https://your-litellm-proxy.example.com/v1",
            "--api-key-stdin",
            "--model",
            "chatgpt/gpt-5.3-instant",
            "--coding-model",
            "chatgpt/gpt-5.3-codex",
            "--user-agent",
            "LLM-Provider-Router/1.0",
            "--probe",
            "--json",
        ],
        ["probe", "--json"],
        ["models"],
        ["chat", "Reply OK if connected"],
        ["serve"],
        ["status", "--json"],
        ["reset-cooldowns"],
    ]
    for argv in samples:
        parsed = parser.parse_args(argv)
        assert parsed.command == argv[0]
