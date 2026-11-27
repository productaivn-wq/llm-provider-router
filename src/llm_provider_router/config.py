"""Configuration loading, strict secret redaction, and outbound URL validation."""

from __future__ import annotations

import ipaddress
import os
import re
import threading
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

REDACTED = "***REDACTED***"

_SECRET_LOCK = threading.Lock()
_REGISTERED_SECRETS: set[str] = set()

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PEM_PRIVATE_KEY",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
        ),
    ),
    ("SK_KEY", re.compile(r"\bsk-(?:ant-|proj-|svcacct-)?[A-Za-z0-9_-]{8,}\b")),
    ("NVIDIA_KEY", re.compile(r"\bnvapi-[A-Za-z0-9_-]{12,}\b")),
    ("GROQ_KEY", re.compile(r"\bgsk_[A-Za-z0-9_-]{12,}\b")),
    (
        "GITHUB_TOKEN",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,})\b"),
    ),
    ("GOOGLE_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{16,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT_TOKEN", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("BEARER_HEADER", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.~+/-]{8,}=*")),
    ("BASIC_HEADER", re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}")),
    (
        "URL_QUERY_SECRET",
        re.compile(r"(?i)([?&](?:key|api_key|token|access_token|secret|auth)=)([^&#\s]+)"),
    ),
    (
        "KV_SECRET",
        re.compile(
            r"(?i)\b(api_key|litellm_api_key|openrouter_api_key|nvidia_api_key|groq_api_key|cerebras_api_key|openai_api_key|router_gateway_token|password|secret_key|private_key)\s*([:=])\s*['\"]?([^\s'\",;}]{4,})['\"]?"
        ),
    ),
)

_BLOCKED_METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata.goog"})
_INVISIBLE_CONTROL_CHARS_RE = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060\xa0\r\n\x00]")
_SMART_QUOTE_TRANS = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})


def default_global_env_path() -> Path:
    """Return the fallback per-user `.env` path so `llm-router` works from any directory."""
    return Path.home() / ".llm_provider_router" / ".env"


def _read_text_auto_encoding(path: Path) -> str:
    """Decode config text safely across UTF-8, UTF-8 BOM, and Windows UTF-16 LE/BE BOM."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8", errors="replace")


def sanitize_header_value(
    value: str | None,
    *,
    field_name: str = "header",
    require_ascii: bool = True,
) -> str:
    """Strip BOM, zero-width spaces, smart quotes, and line breaks from header/key strings."""
    cleaned = _INVISIBLE_CONTROL_CHARS_RE.sub("", str(value or "")).translate(_SMART_QUOTE_TRANS)
    cleaned = cleaned.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ('"', "'"):
        cleaned = cleaned[1:-1].strip()
    if require_ascii and cleaned:
        try:
            cleaned.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"Invalid non-ASCII characters in {field_name}; remove extra copied Vietnamese text or symbols."
            ) from exc
    return cleaned


def register_runtime_secret(value: str | None) -> None:
    """Register an in-memory secret string so it is scrubbed from logs and errors."""
    cleaned = str(value or "").strip()
    if len(cleaned) >= 6:
        with _SECRET_LOCK:
            _REGISTERED_SECRETS.add(cleaned)


def redact_secrets(text: str | None, extra_secrets: Iterable[str] = ()) -> str:
    """Scrub API keys, tokens, PEM blocks, and registered secrets with zero characters leaked."""
    if text is None:
        return ""
    out = str(text)
    if not out:
        return ""

    with _SECRET_LOCK:
        known = set(_REGISTERED_SECRETS)
    for item in extra_secrets:
        cleaned = str(item or "").strip()
        if len(cleaned) >= 6:
            known.add(cleaned)

    for secret_val in sorted(known, key=len, reverse=True):
        if secret_val in out:
            out = out.replace(secret_val, REDACTED)

    for label, pattern in _SECRET_PATTERNS:
        if label == "URL_QUERY_SECRET":
            out = pattern.sub(rf"\1{REDACTED}", out)
        elif label == "KV_SECRET":
            out = pattern.sub(rf"\1\2 {REDACTED}", out)
        elif label == "BEARER_HEADER":
            out = pattern.sub(f"Bearer {REDACTED}", out)
        elif label == "BASIC_HEADER":
            out = pattern.sub(f"Basic {REDACTED}", out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def _strip_inline_comment(raw: str) -> str:
    """Strip unquoted `#` comments from an env value while keeping `#` inside quotes."""
    if not raw:
        return ""
    quote: str | None = None
    escaped = False
    for idx, ch in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and quote == '"':
            escaped = True
            continue
        if ch in ('"', "'"):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
            continue
        if ch == "#" and quote is None and (idx == 0 or raw[idx - 1].isspace()):
            return raw[:idx].strip()
    return raw.strip()


def _unquote_env_value(raw: str) -> str:
    """Unquote a single-quoted or double-quoted `.env` value cleanly."""
    cleaned = _strip_inline_comment(raw)
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ('"', "'"):
        inner = cleaned[1:-1]
        if cleaned[0] == '"':
            inner = (
                inner.replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
        return inner
    return cleaned


def load_dotenv_file(
    path: str | Path | None = None,
    *,
    override: bool = False,
) -> dict[str, str]:
    """Load key=value pairs from a `.env` file using stdlib only."""
    target = Path(path) if path is not None else Path.cwd() / ".env"
    if not target.is_file():
        return {}

    parsed: dict[str, str] = {}
    for raw_line in _read_text_auto_encoding(target).splitlines():
        line = _INVISIBLE_CONTROL_CHARS_RE.sub("", raw_line).strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = _INVISIBLE_CONTROL_CHARS_RE.sub("", key).strip()
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        val = _INVISIBLE_CONTROL_CHARS_RE.sub("", _unquote_env_value(raw_val))
        parsed[key] = val
        if override or not os.environ.get(key):
            os.environ[key] = val
        if any(hint in key.upper() for hint in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            register_runtime_secret(val)
    return parsed


def normalize_openai_base_url(url: str) -> str:
    """Normalize an OpenAI-compatible base URL (trim trailing slash cleanly)."""
    cleaned = str(url or "").strip().rstrip("/")
    return cleaned


def validate_outbound_url(url: str, *, allow_loopback: bool = True) -> tuple[bool, str]:
    """Validate that an outbound provider URL is safe http/https and not a metadata endpoint."""
    raw = str(url or "").strip()
    if not raw:
        return False, "empty URL"
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"unsupported URL scheme: {parsed.scheme!r}"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "missing hostname"
    if host in _BLOCKED_METADATA_HOSTS:
        return False, f"blocked metadata host: {host}"
    if host == "localhost" or host.endswith(".localhost"):
        return (True, "loopback") if allow_loopback else (False, "loopback disabled")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True, "hostname"

    if ip.is_unspecified:
        return False, f"blocked unspecified IP: {host}"
    if ip.is_link_local or str(ip) == "fd00:ec2::254":
        return False, f"blocked link-local/metadata IP: {host}"
    if ip.is_loopback:
        return (True, "loopback") if allow_loopback else (False, "loopback disabled")
    return True, "ip"


def _parse_float(value: str | None, default: float) -> float:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_int(value: str | None, default: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_bool(value: str | None, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def default_state_db_path() -> Path:
    """Return the default SQLite WAL state database path inside user home."""
    return Path.home() / ".llm_provider_router" / "state.db"


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single OpenAI-compatible provider backend."""

    name: str
    display_name: str
    base_url: str
    api_key: str = ""
    default_model: str = ""
    coding_model: str = ""
    fallback_models: tuple[str, ...] = ()
    user_agent: str = "LLM-Provider-Router/1.0"
    timeout_sec: float = 45.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def is_loopback(self) -> bool:
        host = (urllib.parse.urlparse(self.base_url).hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and (self.api_key or self.is_loopback()))

    def candidate_models(
        self, *, requested_model: str | None = None, for_coding: bool = False
    ) -> list[str]:
        if requested_model and not requested_model.startswith("router/"):
            return [requested_model]
        raw: list[str] = []
        if for_coding and self.coding_model:
            raw.append(self.coding_model)
        if self.default_model:
            raw.append(self.default_model)
        raw.extend(self.fallback_models)
        return list(dict.fromkeys(m for m in raw if m))


@dataclass
class RouterConfig:
    """Top-level runtime configuration for `LLMProviderRouter` and `LocalOpenAIGateway`."""

    providers: list[ProviderConfig] = field(default_factory=list)
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 18766
    gateway_token: str = ""
    daily_budget_usd: float = 0.0
    cooldown_base_sec: float = 30.0
    cooldown_max_sec: float = 600.0
    enable_cli_providers: bool = False
    state_db_path: Path = field(default_factory=default_state_db_path)

    @classmethod
    def from_env(
        cls, env_file: str | Path | None = None, *, override_env: bool | None = None
    ) -> RouterConfig:
        """Build `RouterConfig` from environment variables and an optional `.env` file."""
        if env_file is not None:
            load_dotenv_file(env_file, override=True if override_env is None else override_env)
        else:
            eff_override = False if override_env is None else override_env
            default_env = Path.cwd() / ".env"
            if default_env.is_file():
                load_dotenv_file(default_env, override=eff_override)
            global_env = default_global_env_path()
            if global_env.is_file() and global_env.resolve() != default_env.resolve():
                load_dotenv_file(global_env, override=eff_override)

        litellm_key = sanitize_header_value(
            os.environ.get("LITELLM_API_KEY", ""),
            field_name="LITELLM_API_KEY",
            require_ascii=False,
        )
        litellm_url = normalize_openai_base_url(
            sanitize_header_value(
                os.environ.get("LITELLM_PROXY_URL", ""),
                field_name="LITELLM_PROXY_URL",
                require_ascii=False,
            )
        )
        openrouter_key = sanitize_header_value(
            os.environ.get("OPENROUTER_API_KEY", ""), require_ascii=False
        )
        nvidia_key = sanitize_header_value(os.environ.get("NVIDIA_API_KEY", ""), require_ascii=False)
        groq_key = sanitize_header_value(os.environ.get("GROQ_API_KEY", ""), require_ascii=False)
        cerebras_key = sanitize_header_value(
            os.environ.get("CEREBRAS_API_KEY", ""), require_ascii=False
        )
        openai_key = sanitize_header_value(os.environ.get("OPENAI_API_KEY", ""), require_ascii=False)
        gw_token = sanitize_header_value(
            os.environ.get("ROUTER_GATEWAY_TOKEN", ""), require_ascii=False
        )

        for sec in (
            litellm_key,
            openrouter_key,
            nvidia_key,
            groq_key,
            cerebras_key,
            openai_key,
            gw_token,
        ):
            register_runtime_secret(sec)

        ua = (
            sanitize_header_value(
                os.environ.get("LITELLM_USER_AGENT", "LLM-Provider-Router/1.0"),
                field_name="LITELLM_USER_AGENT",
                require_ascii=False,
            )
            or "LLM-Provider-Router/1.0"
        )
        litellm_timeout = max(1.0, _parse_float(os.environ.get("LITELLM_TIMEOUT"), 45.0))
        litellm_model = (
            os.environ.get("LITELLM_MODEL", "chatgpt/gpt-5.3-instant").strip()
            or "chatgpt/gpt-5.3-instant"
        )
        litellm_coding = (
            os.environ.get("LITELLM_CODING_MODEL", "chatgpt/gpt-5.3-codex").strip() or litellm_model
        )

        providers = [
            ProviderConfig(
                name="litellm_proxy",
                display_name="LiteLLM Proxy",
                base_url=litellm_url,
                api_key=litellm_key,
                default_model=litellm_model,
                coding_model=litellm_coding,
                fallback_models=("chatgpt/gpt-5.2-codex",),
                user_agent=ua,
                timeout_sec=litellm_timeout,
            ),
            ProviderConfig(
                name="openrouter",
                display_name="OpenRouter",
                base_url=normalize_openai_base_url(
                    os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
                ),
                api_key=openrouter_key,
                default_model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
                or "openai/gpt-4o-mini",
                coding_model=os.environ.get("OPENROUTER_CODING_MODEL", "openai/gpt-4o-mini").strip()
                or "openai/gpt-4o-mini",
                user_agent=ua,
                timeout_sec=45.0,
            ),
            ProviderConfig(
                name="nvidia_nim",
                display_name="NVIDIA NIM",
                base_url=normalize_openai_base_url(
                    os.environ.get("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
                ),
                api_key=nvidia_key,
                default_model=os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct").strip()
                or "meta/llama-3.1-70b-instruct",
                coding_model=os.environ.get(
                    "NVIDIA_CODING_MODEL", "meta/llama-3.1-70b-instruct"
                ).strip()
                or "meta/llama-3.1-70b-instruct",
                user_agent=ua,
                timeout_sec=45.0,
            ),
            ProviderConfig(
                name="groq",
                display_name="Groq",
                base_url=normalize_openai_base_url(
                    os.environ.get("GROQ_BASE_URL") or "https://api.groq.com/openai/v1"
                ),
                api_key=groq_key,
                default_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
                or "llama-3.3-70b-versatile",
                coding_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
                or "llama-3.3-70b-versatile",
                user_agent=ua,
                timeout_sec=30.0,
            ),
            ProviderConfig(
                name="cerebras",
                display_name="Cerebras",
                base_url=normalize_openai_base_url(
                    os.environ.get("CEREBRAS_BASE_URL") or "https://api.cerebras.ai/v1"
                ),
                api_key=cerebras_key,
                default_model=os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b").strip()
                or "llama-3.3-70b",
                coding_model=os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b").strip()
                or "llama-3.3-70b",
                user_agent=ua,
                timeout_sec=30.0,
            ),
            ProviderConfig(
                name="openai",
                display_name="OpenAI Direct",
                base_url=normalize_openai_base_url(
                    os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
                ),
                api_key=openai_key,
                default_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
                or "gpt-4o-mini",
                coding_model=os.environ.get("OPENAI_CODING_MODEL", "gpt-4o-mini").strip()
                or "gpt-4o-mini",
                user_agent=ua,
                timeout_sec=45.0,
            ),
        ]

        raw_db = os.environ.get("ROUTER_STATE_DB", "").strip()
        db_path = Path(raw_db).expanduser() if raw_db else default_state_db_path()

        return cls(
            providers=providers,
            gateway_host=os.environ.get("ROUTER_GATEWAY_HOST", "127.0.0.1").strip() or "127.0.0.1",
            gateway_port=max(
                1, min(65535, _parse_int(os.environ.get("ROUTER_GATEWAY_PORT"), 18766))
            ),
            gateway_token=gw_token,
            daily_budget_usd=max(0.0, _parse_float(os.environ.get("ROUTER_DAILY_BUDGET_USD"), 0.0)),
            cooldown_base_sec=max(
                1.0, _parse_float(os.environ.get("ROUTER_COOLDOWN_BASE_SEC"), 30.0)
            ),
            cooldown_max_sec=max(
                5.0, _parse_float(os.environ.get("ROUTER_COOLDOWN_MAX_SEC"), 600.0)
            ),
            enable_cli_providers=_parse_bool(os.environ.get("ROUTER_ENABLE_CLI_PROVIDERS"), False),
            state_db_path=db_path,
        )
