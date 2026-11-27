"""Multi-provider failover router orchestrator with cooldown and budget enforcement."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import RouterConfig, redact_secrets
from .providers import (
    COOLDOWN_HTTP_CODES,
    AllProvidersFailedError,
    BaseProviderTier,
    CompletionResult,
    ProviderAttempt,
    ProviderError,
    build_tiers_from_config,
)
from .state import RouterStateStore

logger = logging.getLogger(__name__)


class LLMProviderRouter:
    """Routes chat completions across configured providers with deterministic failover."""

    def __init__(
        self,
        config: RouterConfig | None = None,
        *,
        env_file: str | Path | None = None,
        tiers: list[BaseProviderTier] | None = None,
        state_store: RouterStateStore | None = None,
    ) -> None:
        self.config = config or RouterConfig.from_env(env_file=env_file)
        self.tiers: list[BaseProviderTier] = (
            tiers if tiers is not None else build_tiers_from_config(self.config)
        )
        self.state = state_store or RouterStateStore(
            self.config.state_db_path,
            cooldown_base_sec=self.config.cooldown_base_sec,
            cooldown_max_sec=self.config.cooldown_max_sec,
            daily_budget_usd=self.config.daily_budget_usd,
        )

    def __enter__(self) -> LLMProviderRouter:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the backing SQLite state store cleanly."""
        self.state.close()

    def available_tiers(self) -> list[BaseProviderTier]:
        """Return currently configured & available provider tiers in priority order."""
        return [t for t in self.tiers if t.is_available()]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        for_coding: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> CompletionResult:
        """Execute a chat completion across configured tiers with automatic failover."""
        if not messages:
            raise ValueError("messages must be a non-empty list")

        if self.state.is_budget_exceeded():
            raise AllProvidersFailedError(
                f"Daily spend budget ({self.config.daily_budget_usd:.4f} USD) reached.",
                attempts=[],
            )

        routing_coding = bool(for_coding or model == "router/coding")
        requested = model if (model and not model.startswith("router/")) else None
        active = self.available_tiers()
        if not active:
            raise AllProvidersFailedError(
                "No LLM provider configured. Set LITELLM_PROXY_URL and LITELLM_API_KEY in .env or run 'llm-router setup'.",
                attempts=[],
            )

        attempts: list[ProviderAttempt] = []
        for tier in active:
            models = tier.candidate_models(requested_model=requested, for_coding=routing_coding)
            if not models:
                continue
            for cand_model in models:
                if self.state.is_cooled_down(tier.name, cand_model):
                    rem = self.state.remaining_cooldown_sec(tier.name, cand_model)
                    attempts.append(
                        ProviderAttempt(
                            provider=tier.name,
                            model=cand_model,
                            ok=False,
                            skipped_reason=f"cooldown ({rem}s remaining)",
                        )
                    )
                    continue
                try:
                    result = tier.chat(
                        messages,
                        model=cand_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stop=stop,
                        json_mode=json_mode,
                        timeout=timeout,
                    )
                    self.state.record_success(
                        tier.name,
                        cand_model,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                    )
                    attempt_ok = ProviderAttempt(
                        provider=tier.name,
                        model=cand_model,
                        ok=True,
                        http_status=200,
                        latency_ms=result.latency_ms,
                    )
                    self.state.record_attempt(
                        provider=tier.name,
                        model=cand_model,
                        ok=True,
                        http_status=200,
                        latency_ms=result.latency_ms,
                    )
                    attempts.append(attempt_ok)
                    result.attempts = attempts
                    return result
                except ProviderError as exc:
                    err_text = redact_secrets(str(exc))
                    logger.warning("Provider %s (%s) failed: %s", tier.name, cand_model, err_text)
                    if exc.http_status in COOLDOWN_HTTP_CODES or exc.http_status == 0:
                        self.state.record_failure(
                            tier.name,
                            cand_model,
                            retry_after_sec=exc.retry_after_sec,
                            reason=err_text,
                        )
                    attempts.append(
                        ProviderAttempt(
                            provider=tier.name,
                            model=cand_model,
                            ok=False,
                            http_status=exc.http_status,
                            error=err_text,
                        )
                    )
                    self.state.record_attempt(
                        provider=tier.name,
                        model=cand_model,
                        ok=False,
                        http_status=exc.http_status,
                        detail=err_text,
                    )
                    # Stop trying extra models on the same provider if auth failed cleanly
                    if exc.http_status in (401, 403):
                        break

        summary = "; ".join(
            f"{a.provider}/{a.model}: {a.skipped_reason or a.error}" for a in attempts
        )
        raise AllProvidersFailedError(
            f"All configured providers failed ({len(attempts)} attempt(s)): {summary[:400]}",
            attempts=attempts,
        )

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        """Convenience wrapper for single-turn text completion."""
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)

    def list_models(
        self, *, provider: str | None = None, timeout: float = 15.0
    ) -> list[dict[str, Any]]:
        """Aggregate live models from configured OpenAI-compatible tiers."""
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for tier in self.available_tiers():
            if provider and tier.name != provider:
                continue
            try:
                rows = tier.list_models(timeout=timeout)
            except Exception as exc:
                logger.debug("list_models failed for %s: %s", tier.name, redact_secrets(str(exc)))
                rows = []
            for row in rows:
                key = (row["provider"], row["id"])
                if key not in seen:
                    seen.add(key)
                    out.append(row)
        return out

    def probe(self, *, timeout: float = 10.0) -> dict[str, Any]:
        """Run read-only connectivity/auth probes across all configured providers."""
        results = [tier.probe(timeout=timeout) for tier in self.tiers if tier.is_available()]
        return {
            "ok": any(r["ok"] for r in results) if results else False,
            "configured_count": len(results),
            "healthy_count": sum(1 for r in results if r["ok"]),
            "providers": results,
        }

    def status(self) -> dict[str, Any]:
        """Return safe router diagnostics with zero plaintext secrets."""
        providers_info = []
        for tier in self.tiers:
            providers_info.append(
                {
                    "name": tier.name,
                    "display_name": tier.display_name,
                    "available": tier.is_available(),
                    "models": tier.candidate_models(),
                }
            )
        return {
            "ok": any(p["available"] for p in providers_info),
            "providers": providers_info,
            "active_cooldowns": self.state.active_cooldowns(),
            "daily_spend": self.state.get_daily_spend(),
            "recent_attempts": self.state.recent_attempts(limit=10),
        }
