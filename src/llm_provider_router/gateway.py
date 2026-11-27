"""Loopback-only OpenAI-compatible HTTP gateway exposing `LLMProviderRouter`."""

from __future__ import annotations

import hmac
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import redact_secrets
from .providers import AllProvidersFailedError
from .router import LLMProviderRouter
from .webui import render_chat_ui_html

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_REQUEST_BYTES = 4 * 1024 * 1024
VIRTUAL_MODELS = ("router/auto", "router/coding", "router/fast")


def validate_loopback_host(host: str) -> str:
    """Enforce strictly loopback binding so local API gateway never binds to public interfaces."""
    cleaned = (host or "").strip().strip("[]").lower()
    if cleaned not in LOOPBACK_HOSTS:
        raise ValueError(
            f"Refusing to bind LocalOpenAIGateway to non-loopback host {host!r}; allowed: {sorted(LOOPBACK_HOSTS)}"
        )
    return "127.0.0.1" if cleaned == "localhost" else cleaned


class LocalOpenAIGateway(ThreadingHTTPServer):
    """Thread-safe loopback HTTP server serving `/healthz`, `/v1/models`, and `/v1/chat/completions`."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        router: LLMProviderRouter,
        *,
        host: str = "127.0.0.1",
        port: int = 18766,
        gateway_token: str = "",
    ) -> None:
        safe_host = validate_loopback_host(host)
        self.router = router
        self.gateway_token = (gateway_token or "").strip()
        super().__init__((safe_host, int(port)), _GatewayRequestHandler)


class _GatewayRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler implementing OpenAI-compatible routes on localhost."""

    protocol_version = "HTTP/1.1"
    server: LocalOpenAIGateway

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("gateway %s", redact_secrets(format % args))

    def _drain_request_body(self) -> None:
        """Consume small POST bodies before early errors to avoid Windows TCP RST."""
        try:
            content_len = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return
        if 0 < content_len <= 65536:
            self.rfile.read(content_len)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if status_code >= 400 or (self.headers.get("Connection") or "").lower() == "close":
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _send_html(self, status_code: int, html_text: str) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if (self.headers.get("Connection") or "").lower() == "close":
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _send_sse_completion(self, payload: dict[str, Any]) -> None:
        """Emit OpenAI-compatible SSE chunks when client requests `stream=true`."""
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        model_id = payload["model"]
        cid = payload["id"]
        created = payload["created"]
        chunks = [
            {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": content},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]
        sse_text = (
            "".join(f"data: {json.dumps(ch, ensure_ascii=False)}\n\n" for ch in chunks)
            + "data: [DONE]\n\n"
        )
        body = sse_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _is_authorized(self) -> bool:
        expected = self.server.gateway_token
        if not expected:
            return True
        auth_hdr = self.headers.get("Authorization") or ""
        if not auth_hdr.lower().startswith("bearer "):
            return False
        provided = auth_hdr[7:].strip()
        return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/ui", "/index.html"):
            h, p = self.server.server_address[:2]
            self._send_html(
                200,
                render_chat_ui_html(
                    gateway_url=f"http://{h}:{p}/v1",
                    auth_required=bool(self.server.gateway_token),
                ),
            )
            return

        if path in ("/healthz", "/health"):
            st = self.server.router.status()
            self._send_json(
                200,
                {
                    "ok": st["ok"],
                    "status": "ready" if st["ok"] else "unconfigured",
                    "providers": [p["name"] for p in st["providers"] if p["available"]],
                    "active_cooldowns": len(st["active_cooldowns"]),
                    "daily_spend": st["daily_spend"],
                },
            )
            return

        if not self._is_authorized():
            self._send_json(
                401, {"error": {"message": "Unauthorized", "type": "authentication_error"}}
            )
            return

        if path == "/v1/models":
            now = int(time.time())
            entries: list[dict[str, Any]] = [
                {"id": m, "object": "model", "created": now, "owned_by": "llm-provider-router"}
                for m in VIRTUAL_MODELS
            ]
            seen = set(VIRTUAL_MODELS)
            for row in self.server.router.list_models(timeout=8.0):
                mid = row["id"]
                if mid not in seen:
                    seen.add(mid)
                    entries.append(
                        {
                            "id": mid,
                            "object": "model",
                            "created": now,
                            "owned_by": row.get("owned_by", "upstream"),
                        }
                    )
            self._send_json(200, {"object": "list", "data": entries})
            return

        self._send_json(
            404, {"error": {"message": f"Unknown route: {path}", "type": "not_found_error"}}
        )

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self._is_authorized():
            self._drain_request_body()
            self._send_json(
                401, {"error": {"message": "Unauthorized", "type": "authentication_error"}}
            )
            return

        if path != "/v1/chat/completions":
            self._drain_request_body()
            self._send_json(
                404, {"error": {"message": f"Unknown route: {path}", "type": "not_found_error"}}
            )
            return

        try:
            content_len = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._send_json(
                400,
                {"error": {"message": "Invalid Content-Length", "type": "invalid_request_error"}},
            )
            return

        if content_len <= 0 or content_len > MAX_REQUEST_BYTES:
            self._send_json(
                400,
                {
                    "error": {
                        "message": "Request body empty or too large",
                        "type": "invalid_request_error",
                    }
                },
            )
            return

        raw_body = self.rfile.read(content_len)
        try:
            req_json = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(
                400,
                {"error": {"message": "Malformed JSON payload", "type": "invalid_request_error"}},
            )
            return

        if (
            not isinstance(req_json, dict)
            or not isinstance(req_json.get("messages"), list)
            or not req_json["messages"]
        ):
            self._send_json(
                400,
                {
                    "error": {
                        "message": "'messages' must be a non-empty list",
                        "type": "invalid_request_error",
                    }
                },
            )
            return

        req_model = req_json.get("model")
        stop_val = req_json.get("stop")
        stop_list = (
            [stop_val]
            if isinstance(stop_val, str)
            else (stop_val if isinstance(stop_val, list) else None)
        )
        json_mode = (
            isinstance(req_json.get("response_format"), dict)
            and req_json["response_format"].get("type") == "json_object"
        )

        try:
            result = self.server.router.chat(
                req_json["messages"],
                model=str(req_model) if req_model else None,
                for_coding=(str(req_model or "") == "router/coding"),
                temperature=req_json.get("temperature"),
                max_tokens=req_json.get("max_tokens"),
                stop=stop_list,
                json_mode=json_mode,
            )
            response_payload = result.to_openai_dict(
                requested_model=str(req_model) if req_model else None
            )
            if req_json.get("stream") is True:
                self._send_sse_completion(response_payload)
            else:
                self._send_json(200, response_payload)
        except AllProvidersFailedError as exc:
            self._send_json(
                502,
                {"error": {"message": redact_secrets(str(exc)), "type": "upstream_error"}},
            )
        except Exception as exc:
            self._send_json(
                500,
                {"error": {"message": redact_secrets(str(exc)), "type": "server_error"}},
            )


def start_gateway(
    *,
    env_file: str | None = None,
    host: str | None = None,
    port: int | None = None,
    gateway_token: str | None = None,
) -> LocalOpenAIGateway:
    """Create and return a bound `LocalOpenAIGateway` instance ready for `.serve_forever()`."""
    router = LLMProviderRouter(env_file=env_file)
    return LocalOpenAIGateway(
        router,
        host=host or router.config.gateway_host,
        port=router.config.gateway_port if port is None else port,
        gateway_token=router.config.gateway_token if gateway_token is None else gateway_token,
    )
