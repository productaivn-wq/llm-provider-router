"""Clean, zero-dependency multi-provider LLM router with OpenAI-compatible local gateway."""

from __future__ import annotations

from .config import (
    ProviderConfig,
    RouterConfig,
    load_dotenv_file,
    redact_secrets,
    register_runtime_secret,
    validate_outbound_url,
)
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

__version__ = "1.0.0"

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
    "load_dotenv_file",
    "redact_secrets",
    "register_runtime_secret",
    "start_gateway",
    "validate_outbound_url",
]
