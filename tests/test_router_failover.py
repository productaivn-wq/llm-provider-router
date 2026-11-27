"""Tests for multi-provider failover, custom headers, Retry-After, and error handling."""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from llm_provider_router import (
    AllProvidersFailedError,
    LLMProviderRouter,
    ProviderConfig,
    RouterConfig,
    RouterStateStore,
)
from llm_provider_router.providers import parse_retry_after


class _MockProviderState:
    def __init__(self, handler_fn: Any) -> None:
        self.handler_fn = handler_fn
        self.requests: list[dict[str, Any]] = []


def _start_mock_server(handler_fn: Any) -> tuple[ThreadingHTTPServer, str, _MockProviderState]:
    state = _MockProviderState(handler_fn)

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _respond(
            self, code: int, payload: dict[str, Any], headers: dict[str, str] | None = None
        ) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            state.requests.append(
                {"method": "GET", "path": self.path, "headers": dict(self.headers)}
            )
            code, payload, hdrs = state.handler_fn("GET", self.path, {}, dict(self.headers))
            self._respond(code, payload, hdrs)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or "0")
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            state.requests.append(
                {"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body}
            )
            code, payload, hdrs = state.handler_fn("POST", self.path, body, dict(self.headers))
            self._respond(code, payload, hdrs)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, port = srv.server_address[:2]
    return srv, f"http://{host}:{port}/v1", state


def test_failover_on_429_preserves_user_agent_and_utf8() -> None:
    p1_key = "-".join(["sk", "primary", "SecretKeyValue9999"])
    p2_key = "-".join(["sk", "secondary", "BackupKeyValue9999"])

    def primary_fn(method: str, path: str, body: dict[str, Any], headers: dict[str, str]):
        return 429, {"error": {"message": f"rate limited for key {p1_key}"}}, {"Retry-After": "15"}

    def secondary_fn(method: str, path: str, body: dict[str, Any], headers: dict[str, str]):
        return (
            200,
            {
                "id": "cmpl-2",
                "model": body.get("model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "<think>internal thought</think>Xin chào từ hệ thống dự phòng!",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17},
            },
            {},
        )

    srv1, url1, st1 = _start_mock_server(primary_fn)
    srv2, url2, st2 = _start_mock_server(secondary_fn)
    store = RouterStateStore(":memory:")
    try:
        cfg = RouterConfig(
            providers=[
                ProviderConfig(
                    name="litellm_proxy",
                    display_name="Primary Proxy",
                    base_url=url1,
                    api_key=p1_key,
                    default_model="model-primary",
                    user_agent="Custom-Test-UA/9.9",
                ),
                ProviderConfig(
                    name="openrouter",
                    display_name="Backup Proxy",
                    base_url=url2,
                    api_key=p2_key,
                    default_model="model-backup",
                    user_agent="Custom-Test-UA/9.9",
                ),
            ]
        )
        router = LLMProviderRouter(config=cfg, state_store=store)
        res = router.complete("Hello")
        assert res.provider == "openrouter"
        assert res.content == "Xin chào từ hệ thống dự phòng!"
        assert res.total_tokens == 17
        assert len(res.attempts) == 2
        assert res.attempts[0].ok is False
        assert p1_key not in res.attempts[0].error
        assert st1.requests[0]["headers"].get("User-Agent") == "Custom-Test-UA/9.9"
        assert st2.requests[0]["headers"].get("Authorization") == f"Bearer {p2_key}"
        assert store.is_cooled_down("litellm_proxy", "model-primary")
    finally:
        store.close()
        srv1.shutdown()
        srv1.server_close()
        srv2.shutdown()
        srv2.server_close()


def test_all_providers_failed_redacts_secrets() -> None:
    leaked_key = "-".join(["sk", "fail", "LeakedSecret00001234"])

    def fail_fn(method: str, path: str, body: dict[str, Any], headers: dict[str, str]):
        return 401, {"error": f"invalid api key: {leaked_key}"}, {}

    srv, url, _ = _start_mock_server(fail_fn)
    store = RouterStateStore(":memory:")
    try:
        cfg = RouterConfig(
            providers=[
                ProviderConfig(
                    name="litellm_proxy",
                    display_name="Primary Proxy",
                    base_url=url,
                    api_key=leaked_key,
                    default_model="m1",
                    fallback_models=("m2",),
                )
            ]
        )
        router = LLMProviderRouter(config=cfg, state_store=store)
        with pytest.raises(AllProvidersFailedError) as exc_info:
            router.complete("Hi")
        msg = str(exc_info.value)
        assert leaked_key not in msg
        assert "***REDACTED***" in msg
        # On 401 auth failure, stops immediately without retrying extra models on same tier
        assert len(exc_info.value.attempts) == 1
    finally:
        store.close()
        srv.shutdown()
        srv.server_close()


def test_empty_choices_malformed_json_and_transient_retry() -> None:
    calls = {"primary": 0}

    class _RawHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or "0")
            self.rfile.read(length)
            calls["primary"] += 1
            if calls["primary"] == 1:
                body = b"{not-valid-json"
            else:
                body = json.dumps({"id": "empty", "choices": []}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    bad_srv = ThreadingHTTPServer(("127.0.0.1", 0), _RawHandler)
    threading.Thread(target=bad_srv.serve_forever, daemon=True).start()
    bad_url = f"http://127.0.0.1:{bad_srv.server_address[1]}/v1"

    retry_state = {"count": 0}

    def transient_then_ok(method: str, path: str, body: dict[str, Any], headers: dict[str, str]):
        retry_state["count"] += 1
        if retry_state["count"] == 1:
            return 503, {"error": "temporary overload"}, {}
        return (
            200,
            {
                "id": "cmpl-recovered",
                "model": body.get("model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Recovered after 503"},
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6},
            },
            {},
        )

    ok_srv, ok_url, _ = _start_mock_server(transient_then_ok)
    store = RouterStateStore(":memory:")
    try:
        cfg = RouterConfig(
            providers=[
                ProviderConfig(
                    name="litellm_proxy",
                    display_name="Bad Primary",
                    base_url=bad_url,
                    api_key="-".join(["sk", "bad", "TestKey00001"]),
                    default_model="m1",
                ),
                ProviderConfig(
                    name="openrouter",
                    display_name="Transient Backup",
                    base_url=ok_url,
                    api_key="-".join(["sk", "ok", "TestKey00002"]),
                    default_model="m2",
                ),
            ]
        )
        router = LLMProviderRouter(config=cfg, state_store=store)
        res = router.complete("Test resilience")
        assert res.provider == "openrouter"
        assert res.content == "Recovered after 503"
        assert retry_state["count"] == 2
    finally:
        store.close()
        bad_srv.shutdown()
        bad_srv.server_close()
        ok_srv.shutdown()
        ok_srv.server_close()


def test_parse_retry_after_seconds_and_http_date() -> None:
    assert parse_retry_after("15") == 15.0
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after(None) is None
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30)
    parsed = parse_retry_after(email.utils.format_datetime(future))
    assert parsed is not None and 20.0 <= parsed <= 35.0
