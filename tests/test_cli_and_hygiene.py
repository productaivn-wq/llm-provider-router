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
    assert __version__ == "1.2.0"
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
            "chatgpt/gpt-6.2-sol",
            "--coding-model",
            "chatgpt/gpt-6.2-astra",
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
        ["connect", "--json"],
        ["connect", "--clients", "agy,claude,codex,cursor", "--dry-run", "--json"],
        ["delegate", "--role", "coding", "Write unit tests", "--json"],
        ["batch", "--tasks-file", "tasks.json", "--max-workers", "4", "--json"],
    ]
    for argv in samples:
        parsed = parser.parse_args(argv)
        assert parsed.command == argv[0]


def test_cli_setup_handles_utf16_and_utf8_bom_stdin_bytes(tmp_path: Path, monkeypatch) -> None:
    class _FakeStdin:
        def __init__(self, raw: bytes) -> None:
            self.buffer = io.BytesIO(raw)

        def isatty(self) -> bool:
            return False

    fake_secret = "-".join(["sk", "bom", "Utf16StdinKey987654321"])
    env_path = tmp_path / ".env"
    global_env = tmp_path / "home" / ".llm_provider_router" / ".env"
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("ROUTER_STATE_DB", str(tmp_path / "state_bom.db"))
    monkeypatch.setattr("sys.stdin", _FakeStdin(fake_secret.encode("utf-16")))

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
    assert f"LITELLM_API_KEY={fake_secret}" in env_path.read_text(encoding="utf-8")
    assert global_env.is_file() and f"LITELLM_API_KEY={fake_secret}" in global_env.read_text(
        encoding="utf-8"
    )


def test_audience_docs_installers_and_public_hygiene() -> None:
    import re

    root = Path(__file__).resolve().parents[1]
    nontech_doc = root / "docs" / "AI_SETUP_PROMPT_NONTECH.md"
    tech_doc = root / "docs" / "AI_SETUP_PROMPT_TECH.md"
    visual_doc = root / "docs" / "VISUAL_GUIDE_VI.md"
    index_doc = root / "docs" / "AI_SETUP_PROMPT.md"
    ps_installer = root / "scripts" / "install.ps1"
    sh_installer = root / "scripts" / "install.sh"

    for p in (nontech_doc, tech_doc, visual_doc, index_doc, ps_installer, sh_installer):
        assert p.is_file(), f"Missing deliverable: {p}"

    assert not (root / "src" / "llm_provider_router" / "webui.py").exists(), "webui.py must be removed"

    # README.md and pyproject.toml must stay pure ASCII so Windows pip install never fails under cp1252/cp1258
    for pkg_file in (root / "README.md", root / "pyproject.toml"):
        raw_txt = pkg_file.read_text(encoding="utf-8")
        assert all(ord(ch) < 128 for ch in raw_txt), f"Non-ASCII char found in {pkg_file.name}"

    nontech_text = nontech_doc.read_text(encoding="utf-8")
    for marker in (
        "archive/refs/heads/main.zip",
        "Activate.ps1",
        "--api-key-stdin",
        "-m llm_provider_router connect",
        "-m llm_provider_router delegate",
        "Phase 7",
        "PYTHONUTF8=1",
    ):
        assert marker in nontech_text, f"Missing non-tech safeguard marker {marker!r}"

    tech_text = tech_doc.read_text(encoding="utf-8")
    for marker in (
        "--api-key-stdin",
        "-m llm_provider_router connect",
        "-m llm_provider_router delegate",
        "LLM-Provider-Router/1.0",
        "Orchestrator",
    ):
        assert marker in tech_text, f"Missing tech marker {marker!r}"

    visual_text = visual_doc.read_text(encoding="utf-8")
    for marker in ("mermaid", "Orchestrator", "llm-router delegate", "llm-router connect"):
        assert marker in visual_text, f"Missing visual guide marker {marker!r}"

    for no_web_ui_file in (root / "README.md", nontech_doc, tech_doc, visual_doc, index_doc, ps_installer, sh_installer):
        txt_check = no_web_ui_file.read_text(encoding="utf-8")
        assert "Mo_Chat_AI" not in txt_check, f"Obsolete Mo_Chat_AI ref in {no_web_ui_file.name}"
        assert "Web Chat UI" not in txt_check, f"Obsolete Web Chat UI ref in {no_web_ui_file.name}"

    from llm_provider_router import VERIFIED_MODELS

    assert len(VERIFIED_MODELS) == 10
    for doc_with_models in (root / "README.md", nontech_doc, tech_doc, visual_doc):
        doc_txt = doc_with_models.read_text(encoding="utf-8")
        for mid in VERIFIED_MODELS:
            assert mid in doc_txt, f"Verified model {mid!r} missing from {doc_with_models.name}"

    # Verify public-repo zero-leak hygiene across README, docs, scripts, src, tests
    forbidden_internal = [
        "".join(["mh", "solution", ".vn"]),
        "".join(["icp", "v.io", ".vn"]),
        "".join(["product", "ai.vn"]),
        "".join(["hrm.", "mh"]),
        "".join(["phuong", "vnn"]),
        "".join(["công ", "danh"]),
        "".join(["văn ", "thông"]),
    ]
    sk_pat = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
    scan_files = (
        [root / "README.md"]
        + sorted((root / "docs").glob("*.md"))
        + sorted((root / "scripts").glob("*"))
        + sorted((root / "src" / "llm_provider_router").glob("*.py"))
        + sorted((root / "tests").glob("*.py"))
    )
    for fpath in scan_files:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        low = content.lower()
        for token in forbidden_internal:
            assert token not in low, f"Public hygiene leak ({token!r}) in {fpath}"
        assert not sk_pat.search(content), f"Raw sk- key literal found in {fpath}"
