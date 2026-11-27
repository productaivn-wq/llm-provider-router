"""Tests for SQLite WAL cooldowns, exponential backoff, daily spend, and attempt logs."""

from __future__ import annotations

from pathlib import Path

from llm_provider_router.state import RouterStateStore


def test_exponential_cooldown_and_recovery(tmp_path: Path) -> None:
    store = RouterStateStore(tmp_path / "state.db", cooldown_base_sec=10.0, cooldown_max_sec=60.0)
    try:
        t0 = 1_700_000_000.0
        assert not store.is_cooled_down("litellm_proxy", "model-a", now_epoch=t0)

        d1 = store.record_failure("litellm_proxy", "model-a", reason="HTTP 429", now_epoch=t0)
        assert d1 == 10.0
        assert store.is_cooled_down("litellm_proxy", "model-a", now_epoch=t0 + 5.0)
        assert not store.is_cooled_down("litellm_proxy", "model-a", now_epoch=t0 + 11.0)

        d2 = store.record_failure(
            "litellm_proxy", "model-a", reason="HTTP 429", now_epoch=t0 + 12.0
        )
        assert d2 == 20.0

        d_cap = store.record_failure(
            "litellm_proxy",
            "model-a",
            retry_after_sec=999.0,
            reason="Retry-After header",
            now_epoch=t0 + 40.0,
        )
        assert d_cap == 60.0

        active = store.active_cooldowns(now_epoch=t0 + 41.0)
        assert len(active) == 1
        assert active[0]["failure_count"] == 3

        store.record_success(
            "litellm_proxy",
            "model-a",
            prompt_tokens=12,
            completion_tokens=8,
            estimated_cost_usd=0.015,
            now_epoch=t0 + 42.0,
        )
        assert not store.is_cooled_down("litellm_proxy", "model-a", now_epoch=t0 + 43.0)
        spend = store.get_daily_spend(now_epoch=t0 + 42.0)
        assert spend["requests"] == 1
        assert spend["prompt_tokens"] == 12
        assert spend["completion_tokens"] == 8
    finally:
        store.close()


def test_budget_breaker_and_attempt_ring() -> None:
    store = RouterStateStore(":memory:", daily_budget_usd=0.05)
    try:
        t0 = 1_700_000_000.0
        assert not store.is_budget_exceeded(now_epoch=t0)
        store.record_success("p1", "m1", estimated_cost_usd=0.06, now_epoch=t0)
        assert store.is_budget_exceeded(now_epoch=t0)

        store.record_attempt(
            provider="p1", model="m1", ok=False, http_status=429, detail="rate limit"
        )
        store.record_attempt(provider="p2", model="m2", ok=True, http_status=200, latency_ms=42.5)
        recent = store.recent_attempts(limit=5)
        assert len(recent) == 2
        assert recent[0]["provider"] == "p2"
        assert recent[0]["ok"] is True

        assert store.clear_cooldowns() == 0
    finally:
        store.close()
