"""Tests for the loopback OpenAI-compatible HTTP gateway."""

from __future__ import annotations

import concurrent.futures
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from llm_provider_router import (
    LLMProviderRouter,
    LocalOpenAIGateway,
    ProviderConfig,
    RouterConfig,
    RouterStateStore,
)


def _start_upstream() -> tuple[ThreadingHTTPServer, str]:
    class _H(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _json(self, code: int, data: dict[str, Any]) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/v1/models":
                self._json(200, {"data": [{"id": "chatgpt/gpt-5.3-instant", "owned_by": "proxy"}]})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or "0")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            self._json(
                200,
                {
                    "id": "cmpl-router-1",
                    "model": body.get("model"),
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": "Gateway OK"}}
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                },
            )

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h, p = srv.server_address[:2]
    return srv, f"http://{h}:{p}/v1"


def test_gateway_rejects_non_loopback_host() -> None:
    store = RouterStateStore(":memory:")
    try:
        router = LLMProviderRouter(config=RouterConfig(), state_store=store)
        with pytest.raises(ValueError):
            LocalOpenAIGateway(router, host="0.0.0.0", port=0)
    finally:
        store.close()


def test_gateway_auth_models_and_chat_roundtrip() -> None:
    upstream, up_url = _start_upstream()
    store = RouterStateStore(":memory:")
    up_key = "-".join(["sk", "up", "MockUpstreamKey9999"])
    gw_token = "local-gateway-token-9999"

    cfg = RouterConfig(
        providers=[
            ProviderConfig(
                name="litellm_proxy",
                display_name="Upstream",
                base_url=up_url,
                api_key=up_key,
                default_model="chatgpt/gpt-5.3-instant",
                coding_model="chatgpt/gpt-5.3-codex",
            )
        ]
    )
    router = LLMProviderRouter(config=cfg, state_store=store)
    gw = LocalOpenAIGateway(router, host="127.0.0.1", port=0, gateway_token=gw_token)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    gw_host, gw_port = gw.server_address[:2]
    base = f"http://{gw_host}:{gw_port}"

    try:
        # 1. /healthz accessible without Bearer token
        with urllib.request.urlopen(f"{base}/healthz", timeout=5) as resp:
            hz = json.loads(resp.read().decode("utf-8"))
        assert hz["ok"] is True
        assert hz["providers"] == ["litellm_proxy"]

        # 2. /v1/models and POST /v1/chat/completions reject missing Bearer token cleanly (no TCP RST)
        with pytest.raises(urllib.error.HTTPError) as exc_401:
            urllib.request.urlopen(f"{base}/v1/models", timeout=5)
        assert exc_401.value.code == 401
        for _ in range(5):
            req_unauth = urllib.request.Request(
                f"{base}/v1/chat/completions",
                data=json.dumps(
                    {"model": "router/auto", "messages": [{"role": "user", "content": "NoAuth"}]}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with pytest.raises(urllib.error.HTTPError) as post_401:
                urllib.request.urlopen(req_unauth, timeout=5)
            assert post_401.value.code == 401

        # 3. /v1/models succeeds with Bearer token
        req_m = urllib.request.Request(
            f"{base}/v1/models", headers={"Authorization": f"Bearer {gw_token}"}
        )
        with urllib.request.urlopen(req_m, timeout=5) as resp:
            models_payload = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in models_payload["data"]]
        assert "router/auto" in ids
        assert "chatgpt/gpt-5.3-instant" in ids

        # 4. /v1/chat/completions succeeds
        req_c = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(
                {"model": "router/coding", "messages": [{"role": "user", "content": "Ping"}]}
            ).encode("utf-8"),
            headers={"Authorization": f"Bearer {gw_token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_c, timeout=5) as resp:
            comp = json.loads(resp.read().decode("utf-8"))
        assert comp["choices"][0]["message"]["content"] == "Gateway OK"
        assert comp["x_router"]["provider"] == "litellm_proxy"
        assert comp["x_router"]["resolved_model"] == "chatgpt/gpt-5.3-codex"

        # 5. /v1/chat/completions stream=true emits SSE events cleanly
        req_s = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "router/auto",
                    "stream": True,
                    "messages": [{"role": "user", "content": "Stream"}],
                }
            ).encode("utf-8"),
            headers={"Authorization": f"Bearer {gw_token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_s, timeout=5) as resp:
            sse_body = resp.read().decode("utf-8")
        assert "chat.completion.chunk" in sse_body
        assert "Gateway OK" in sse_body
        assert "data: [DONE]" in sse_body
    finally:
        gw.shutdown()
        gw.server_close()
        store.close()
        upstream.shutdown()
        upstream.server_close()


def test_gateway_concurrent_requests_with_wal_store(tmp_path: Path) -> None:
    upstream, up_url = _start_upstream()
    store = RouterStateStore(tmp_path / "wal_state.db")
    cfg = RouterConfig(
        providers=[
            ProviderConfig(
                name="litellm_proxy",
                display_name="Upstream",
                base_url=up_url,
                api_key="-".join(["sk", "wal", "ConcurrentTestKey01"]),
                default_model="chatgpt/gpt-5.3-instant",
            )
        ]
    )
    router = LLMProviderRouter(config=cfg, state_store=store)
    gw = LocalOpenAIGateway(router, host="127.0.0.1", port=0)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    gw_host, gw_port = gw.server_address[:2]
    url = f"http://{gw_host}:{gw_port}/v1/chat/completions"

    def _one_call(idx: int) -> str:
        req = urllib.request.Request(
            url,
            data=json.dumps(
                {"model": "router/auto", "messages": [{"role": "user", "content": f"q-{idx}"}]}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_one_call, range(8)))
        assert results == ["Gateway OK"] * 8
        assert store.get_daily_spend()["requests"] == 8
    finally:
        gw.shutdown()
        gw.server_close()
        store.close()
        upstream.shutdown()
        upstream.server_close()
