"""Clean, zero-dependency multi-provider LLM router with OpenAI-compatible local gateway."""

from __future__ import annotations

from .config import (
    ProviderConfig,
    RouterConfig,
    default_global_env_path,
    load_dotenv_file,
    redact_secrets,
    register_runtime_secret,
    sanitize_header_value,
    validate_outbound_url,
)
from .connect import connect_clients
from .delegate import run_batch, run_delegate
from .gateway import LocalOpenAIGateway, start_gateway
from .providers import (
    AllProvidersFailedError,
    BaseProviderTier,
    CerebrasTier,
    CompletionResult,
    GroqTier,
    LiteLLMProxyTier,
    LocalCLITier,
    NvidiaNimTier,
    OpenAICompatTier,
    OpenAIDirectTier,
    OpenRouterTier,
    ProviderAttempt,
    ProviderError,
)
from .router import LLMProviderRouter
from .state import RouterStateStore

__version__ = "1.2.0"

__all__ = [
    "__version__",
    "AllProvidersFailedError",
    "BaseProviderTier",
    "CerebrasTier",
    "CompletionResult",
    "GroqTier",
    "LLMProviderRouter",
    "LiteLLMProxyTier",
    "LocalCLITier",
    "LocalOpenAIGateway",
    "NvidiaNimTier",
    "OpenAICompatTier",
    "OpenAIDirectTier",
    "OpenRouterTier",
    "ProviderAttempt",
    "ProviderConfig",
    "ProviderError",
    "RouterConfig",
    "RouterStateStore",
    "connect_clients",
    "default_global_env_path",
    "load_dotenv_file",
    "redact_secrets",
    "register_runtime_secret",
    "run_batch",
    "run_delegate",
    "sanitize_header_value",
    "start_gateway",
    "validate_outbound_url",
]
