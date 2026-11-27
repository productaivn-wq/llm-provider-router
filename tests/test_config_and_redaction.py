"""Tests for configuration loading, strict secret redaction, and URL safety validation."""

from __future__ import annotations

from pathlib import Path

from llm_provider_router.config import (
    REDACTED,
    RouterConfig,
    load_dotenv_file,
    redact_secrets,
    register_runtime_secret,
    validate_outbound_url,
)


def test_dotenv_parsing_quotes_comments_and_export(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TEST_ROUTER_VAR_A", raising=False)
    monkeypatch.delenv("TEST_ROUTER_VAR_B", raising=False)
    monkeypatch.setenv("TEST_ROUTER_EXISTING", "keep-original")

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Top comment\n"
        'export TEST_ROUTER_VAR_A="hello # not comment" # inline comment\n'
        "TEST_ROUTER_VAR_B='single quoted\\nliteral'\n"
        "TEST_ROUTER_EXISTING=overwritten\n",
        encoding="utf-8",
    )

    loaded = load_dotenv_file(env_file, override=False)
    assert loaded["TEST_ROUTER_VAR_A"] == "hello # not comment"
    assert loaded["TEST_ROUTER_VAR_B"] == "single quoted\\nliteral"
    assert loaded["TEST_ROUTER_EXISTING"] == "overwritten"
    # Existing process env is preserved when override=False
    import os

    assert os.environ["TEST_ROUTER_EXISTING"] == "keep-original"

    load_dotenv_file(env_file, override=True)
    assert os.environ["TEST_ROUTER_EXISTING"] == "overwritten"


def test_redact_secrets_masks_zero_prefix_suffix() -> None:
    tok_sk = "-".join(["sk", "proj", "SyntheticTokenAlpha987654321"])
    tok_gh = "ghp_" + "SyntheticGitHubToken987654321"
    tok_bearer = "CustomOpaqueSecretValue987654321"
    register_runtime_secret(tok_bearer)

    sample = (
        f"Authorization: Bearer {tok_sk} "
        f"url=https://example.com/v1?api_key={tok_gh} "
        f"leaked={tok_bearer} "
        f"LITELLM_API_KEY={tok_sk}"
    )
    redacted = redact_secrets(sample)
    assert tok_sk not in redacted
    assert tok_gh not in redacted
    assert tok_bearer not in redacted
    assert "Alpha" not in redacted
    assert "987654321" not in redacted
    assert REDACTED in redacted


def test_validate_outbound_url_blocks_metadata_and_bad_schemes() -> None:
    ok_https, _ = validate_outbound_url("https://api.example.com/v1")
    assert ok_https

    ok_loop, _ = validate_outbound_url("http://127.0.0.1:18766/v1", allow_loopback=True)
    assert ok_loop

    bad_loop, _ = validate_outbound_url("http://127.0.0.1:18766/v1", allow_loopback=False)
    assert not bad_loop

    for bad in (
        "file:///etc/passwd",
        "ftp://example.com/data",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://0.0.0.0:8080/v1",
        "",
    ):
        ok, _ = validate_outbound_url(bad)
        assert not ok, f"Expected blocked URL: {bad}"


def test_router_config_from_env_builds_providers(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    synthetic_key = "-".join(["sk", "demo", "ConfiguredKey0000123456"])
    env_file.write_text(
        "LITELLM_PROXY_URL=https://proxy.example.com/v1/\n"
        f"LITELLM_API_KEY={synthetic_key}\n"
        "LITELLM_MODEL=chatgpt/gpt-5.3-instant\n"
        "LITELLM_CODING_MODEL=chatgpt/gpt-5.3-codex\n"
        "LITELLM_USER_AGENT=Custom-Router-Test/2.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ROUTER_STATE_DB", str(tmp_path / "state.db"))
    cfg = RouterConfig.from_env(env_file=env_file, override_env=True)
    primary = cfg.providers[0]
    assert primary.name == "litellm_proxy"
    assert primary.base_url == "https://proxy.example.com/v1"
    assert primary.is_configured()
    assert primary.user_agent == "Custom-Router-Test/2.0"
    assert primary.candidate_models(for_coding=False)[0] == "chatgpt/gpt-5.3-instant"
    assert primary.candidate_models(for_coding=True)[0] == "chatgpt/gpt-5.3-codex"
