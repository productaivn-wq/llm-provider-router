"""OpenAI-compatible HTTP provider tiers and optional local CLI fallback tier."""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

from .config import ProviderConfig, RouterConfig, redact_secrets, validate_outbound_url

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TRANSIENT_HTTP_CODES = frozenset({502, 503, 504})
COOLDOWN_HTTP_CODES = frozenset({401, 402, 403, 408, 429, 500, 502, 503, 504})


@dataclass
class ProviderAttempt:
    """Telemetry record for one routing attempt."""

    provider: str
    model: str
    ok: bool
    http_status: int = 0
    latency_ms: float = 0.0
    error: str = ""
    skipped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "ok": self.ok,
            "http_status": self.http_status,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class CompletionResult:
    """Normalized chat completion result across all provider backends."""

    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    attempts: list[ProviderAttempt] = field(default_factory=list)
    response_id: str = field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")

    def to_openai_dict(self, *, requested_model: str | None = None) -> dict[str, Any]:
        """Serialize into an OpenAI `/v1/chat/completions` compatible response payload."""
        total = self.total_tokens or (self.prompt_tokens + self.completion_tokens)
        return {
            "id": self.response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": requested_model or self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": self.content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": total,
            },
            "x_router": {
                "provider": self.provider,
                "resolved_model": self.model,
                "latency_ms": round(self.latency_ms, 2),
                "attempts": len(self.attempts),
            },
        }


class ProviderError(RuntimeError):
    """Error raised when a single provider call fails."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str = "",
        http_status: int = 0,
        retry_after_sec: float | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(redact_secrets(message))
        self.provider = provider
        self.model = model
        self.http_status = http_status
        self.retry_after_sec = retry_after_sec
        self.retryable = retryable


class AllProvidersFailedError(RuntimeError):
    """Error raised when all configured providers fail or are on cooldown."""

    def __init__(self, message: str, *, attempts: list[ProviderAttempt] | None = None) -> None:
        super().__init__(redact_secrets(message))
        self.attempts = attempts or []


def parse_retry_after(header_value: str | None) -> float | None:
    """Parse HTTP `Retry-After` seconds or HTTP-date into a bounded delay in seconds."""
    raw = str(header_value or "").strip()
    if not raw:
        return None
    try:
        secs = float(raw)
        return max(0.0, secs)
    except ValueError:
        pass
    try:
        target = email.utils.parsedate_to_datetime(raw)
        if target.tzinfo is None:
            target = target.replace(tzinfo=dt.timezone.utc)
        delta = (target - dt.datetime.now(dt.timezone.utc)).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


def _extract_message_content(payload: dict[str, Any]) -> str:
    """Extract assistant text from standard or block-formatted OpenAI completion responses."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing or empty 'choices' in completion response")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("malformed choice entry in completion response")
    msg = first.get("message")
    if isinstance(msg, dict):
        raw_content = msg.get("content")
        if isinstance(raw_content, str):
            return raw_content
        if isinstance(raw_content, list):
            parts: list[str] = []
            for part in raw_content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts)
    if isinstance(first.get("text"), str):
        return str(first["text"])
    raise ValueError("missing message content in completion response")


def _strip_think_prefix(text: str) -> str:
    """Strip leading `<think>...</think>` blocks if visible answer text follows."""
    stripped = text.lstrip()
    if not stripped.startswith("<think>"):
        return text
    end_idx = stripped.find("</think>")
    if end_idx == -1:
        return text
    remainder = stripped[end_idx + len("</think>") :].lstrip()
    return remainder if remainder else text


class BaseProviderTier:
    """Abstract base interface for a routable LLM provider backend."""

    name: str = "base"
    display_name: str = "Base"

    def is_available(self) -> bool:
        return False

    def candidate_models(
        self, *, requested_model: str | None = None, for_coding: bool = False
    ) -> list[str]:
        return []

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> CompletionResult:
        raise NotImplementedError

    def list_models(self, *, timeout: float = 15.0) -> list[dict[str, Any]]:
        return []

    def probe(self, *, timeout: float = 10.0) -> dict[str, Any]:
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "configured": self.is_available(),
            "ok": False,
            "http_status": 0,
            "models_count": 0,
            "latency_ms": 0.0,
            "error": "not implemented",
        }


class OpenAICompatTier(BaseProviderTier):
    """Stdlib HTTP client for OpenAI-compatible endpoints (LiteLLM Proxy, OpenRouter, NIM, Groq, etc.)."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.name = config.name
        self.display_name = config.display_name

    def _endpoints(self) -> tuple[str, str]:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions", f"{base}/models"
        return f"{base}/v1/chat/completions", f"{base}/v1/models"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.config.user_agent or "LLM-Provider-Router/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        for k, v in self.config.extra_headers.items():
            headers[k] = v
        return headers

    def is_available(self) -> bool:
        if not self.config.is_configured():
            return False
        ok, _ = validate_outbound_url(self.config.base_url, allow_loopback=True)
        return ok

    def candidate_models(
        self, *, requested_model: str | None = None, for_coding: bool = False
    ) -> list[str]:
        return self.config.candidate_models(requested_model=requested_model, for_coding=for_coding)

    def _read_bounded(self, response: Any) -> bytes:
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ProviderError(
                f"[{self.display_name}] response exceeded {MAX_RESPONSE_BYTES} byte limit",
                provider=self.name,
                retryable=False,
            )
        return data

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> CompletionResult:
        if not self.is_available():
            raise ProviderError(
                f"[{self.display_name}] provider is not configured or URL blocked",
                provider=self.name,
                model=model,
                retryable=False,
            )

        chat_url, _ = self._endpoints()
        ok_url, reason = validate_outbound_url(chat_url, allow_loopback=True)
        if not ok_url:
            raise ProviderError(
                f"[{self.display_name}] blocked outbound URL ({reason})",
                provider=self.name,
                model=model,
                retryable=False,
            )

        body_obj: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            body_obj["temperature"] = temperature
        if max_tokens is not None:
            body_obj["max_tokens"] = int(max_tokens)
        if stop:
            body_obj["stop"] = stop
        if json_mode:
            body_obj["response_format"] = {"type": "json_object"}

        req_timeout = max(0.5, float(timeout or self.config.timeout_sec))
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        headers = self._headers()

        last_err: ProviderError | None = None
        for attempt in range(2):
            req = urllib.request.Request(chat_url, data=raw_body, headers=headers, method="POST")
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=req_timeout) as resp:
                    payload_bytes = self._read_bounded(resp)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                decoded = payload_bytes.decode("utf-8", errors="replace")
                res_data = json.loads(decoded)
                content = _strip_think_prefix(_extract_message_content(res_data))
                usage = res_data.get("usage") if isinstance(res_data.get("usage"), dict) else {}
                p_tok = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                c_tok = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                t_tok = int(usage.get("total_tokens") or (p_tok + c_tok))
                resolved_model = str(res_data.get("model") or model)
                return CompletionResult(
                    content=content,
                    provider=self.name,
                    model=resolved_model,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                    latency_ms=latency_ms,
                )
            except urllib.error.HTTPError as exc:
                err_raw = exc.read(8192).decode("utf-8", errors="replace")
                clean_err = redact_secrets(err_raw, (self.config.api_key,))[:300]
                retry_after = parse_retry_after(
                    exc.headers.get("Retry-After") if exc.headers else None
                )
                last_err = ProviderError(
                    f"[{self.display_name}] HTTP {exc.code}: {clean_err}",
                    provider=self.name,
                    model=model,
                    http_status=int(exc.code),
                    retry_after_sec=retry_after,
                    retryable=int(exc.code) in COOLDOWN_HTTP_CODES,
                )
                if exc.code in TRANSIENT_HTTP_CODES and attempt == 0:
                    time.sleep(0.25)
                    continue
                raise last_err from exc
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                clean_err = redact_secrets(str(exc), (self.config.api_key,))[:240]
                raise ProviderError(
                    f"[{self.display_name}] invalid JSON response: {clean_err}",
                    provider=self.name,
                    model=model,
                    retryable=True,
                ) from exc
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                clean_err = redact_secrets(str(exc), (self.config.api_key,))[:240]
                last_err = ProviderError(
                    f"[{self.display_name}] network error: {clean_err}",
                    provider=self.name,
                    model=model,
                    retryable=True,
                )
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                raise last_err from exc

        assert last_err is not None
        raise last_err

    def list_models(self, *, timeout: float = 15.0) -> list[dict[str, Any]]:
        if not self.is_available():
            return []
        _, models_url = self._endpoints()
        ok_url, _ = validate_outbound_url(models_url, allow_loopback=True)
        if not ok_url:
            return []
        headers = {k: v for k, v in self._headers().items() if k.lower() != "content-type"}
        req = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=max(0.5, timeout)) as resp:
            data = json.loads(self._read_bounded(resp).decode("utf-8", errors="replace"))
        rows = data.get("data") if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                out.append(
                    {
                        "id": str(row["id"]),
                        "owned_by": str(row.get("owned_by") or self.name),
                        "provider": self.name,
                    }
                )
        return out

    def probe(self, *, timeout: float = 10.0) -> dict[str, Any]:
        if not self.is_available():
            return {
                "provider": self.name,
                "display_name": self.display_name,
                "configured": False,
                "ok": False,
                "http_status": 0,
                "models_count": 0,
                "latency_ms": 0.0,
                "error": "not configured",
            }
        t0 = time.perf_counter()
        try:
            models = self.list_models(timeout=timeout)
            return {
                "provider": self.name,
                "display_name": self.display_name,
                "configured": True,
                "ok": True,
                "http_status": 200,
                "models_count": len(models),
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "error": "",
            }
        except urllib.error.HTTPError as exc:
            err_txt = redact_secrets(
                exc.read(2048).decode("utf-8", errors="replace"), (self.config.api_key,)
            )[:200]
            return {
                "provider": self.name,
                "display_name": self.display_name,
                "configured": True,
                "ok": False,
                "http_status": int(exc.code),
                "models_count": 0,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "error": f"HTTP {exc.code}: {err_txt}",
            }
        except (OSError, ValueError, ProviderError) as exc:
            return {
                "provider": self.name,
                "display_name": self.display_name,
                "configured": True,
                "ok": False,
                "http_status": 0,
                "models_count": 0,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "error": redact_secrets(str(exc), (self.config.api_key,))[:200],
            }


class LiteLLMProxyTier(OpenAICompatTier):
    """Primary LiteLLM Proxy OpenAI-compatible provider tier."""


class OpenRouterTier(OpenAICompatTier):
    """OpenRouter OpenAI-compatible provider tier."""


class NvidiaNimTier(OpenAICompatTier):
    """NVIDIA NIM OpenAI-compatible provider tier."""


class GroqTier(OpenAICompatTier):
    """Groq OpenAI-compatible provider tier."""


class CerebrasTier(OpenAICompatTier):
    """Cerebras OpenAI-compatible provider tier."""


class OpenAIDirectTier(OpenAICompatTier):
    """Direct OpenAI API provider tier."""


class LocalCLITier(BaseProviderTier):
    """Optional local headless CLI fallback tier (`claude -p` or `codex exec`)."""

    def __init__(
        self, *, binary: str = "claude", enabled: bool = False, timeout_sec: float = 90.0
    ) -> None:
        self.binary = binary
        self.name = f"local_cli_{binary}"
        self.display_name = f"Local CLI ({binary})"
        self.enabled = bool(enabled)
        self.timeout_sec = max(5.0, float(timeout_sec))

    def is_available(self) -> bool:
        return self.enabled and shutil.which(self.binary) is not None

    def candidate_models(
        self, *, requested_model: str | None = None, for_coding: bool = False
    ) -> list[str]:
        return [f"cli/{self.binary}"]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> CompletionResult:
        exe = shutil.which(self.binary)
        if not self.enabled or not exe:
            raise ProviderError(
                f"[{self.display_name}] disabled or executable not installed",
                provider=self.name,
                model=model,
                retryable=False,
            )

        prompt_lines: list[str] = []
        for m in messages:
            role = str(m.get("role") or "user").upper()
            content = str(m.get("content") or "")
            prompt_lines.append(f"{role}: {content}")
        joined = "\n\n".join(prompt_lines)
        cmd = [exe, "-p", joined] if self.binary == "claude" else [exe, "exec", joined]

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(5.0, float(timeout or self.timeout_sec)),
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProviderError(
                f"[{self.display_name}] execution failed: {redact_secrets(str(exc))[:200]}",
                provider=self.name,
                model=model,
                retryable=True,
            ) from exc

        latency_ms = (time.perf_counter() - t0) * 1000.0
        if proc.returncode != 0 or not proc.stdout.strip():
            err_msg = redact_secrets(proc.stderr or proc.stdout or f"exit={proc.returncode}")[:240]
            raise ProviderError(
                f"[{self.display_name}] failed: {err_msg}",
                provider=self.name,
                model=model,
                retryable=True,
            )
        return CompletionResult(
            content=proc.stdout.strip(),
            provider=self.name,
            model=f"cli/{self.binary}",
            latency_ms=latency_ms,
        )

    def probe(self, *, timeout: float = 10.0) -> dict[str, Any]:
        exe = shutil.which(self.binary)
        ok = bool(self.enabled and exe)
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "configured": ok,
            "ok": ok,
            "http_status": 0,
            "models_count": 1 if ok else 0,
            "latency_ms": 0.0,
            "error": ""
            if self.enabled
            else "disabled (set ROUTER_ENABLE_CLI_PROVIDERS=1 to enable)",
        }


_TIER_CLASS_MAP: dict[str, type[OpenAICompatTier]] = {
    "litellm_proxy": LiteLLMProxyTier,
    "openrouter": OpenRouterTier,
    "nvidia_nim": NvidiaNimTier,
    "groq": GroqTier,
    "cerebras": CerebrasTier,
    "openai": OpenAIDirectTier,
}


def build_tiers_from_config(config: RouterConfig) -> list[BaseProviderTier]:
    """Instantiate ordered provider tiers from a `RouterConfig`."""
    tiers: list[BaseProviderTier] = []
    for pcfg in config.providers:
        cls = _TIER_CLASS_MAP.get(pcfg.name, OpenAICompatTier)
        tiers.append(cls(pcfg))
    if config.enable_cli_providers:
        tiers.append(LocalCLITier(binary="claude", enabled=True))
        tiers.append(LocalCLITier(binary="codex", enabled=True))
    return tiers
