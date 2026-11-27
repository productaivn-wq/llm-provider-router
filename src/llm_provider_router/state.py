"""Thread-safe SQLite WAL state store for cooldowns, spend tracking, and attempt audit logs."""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class RouterStateStore:
    """SQLite WAL state store managing provider cooldowns, daily spend, and recent attempt history."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        cooldown_base_sec: float = 30.0,
        cooldown_max_sec: float = 600.0,
        daily_budget_usd: float = 0.0,
    ) -> None:
        self.db_path = str(db_path) if db_path is not None else ":memory:"
        self.cooldown_base_sec = max(1.0, float(cooldown_base_sec))
        self.cooldown_max_sec = max(self.cooldown_base_sec, float(cooldown_max_sec))
        self.daily_budget_usd = max(0.0, float(daily_budget_usd))
        self._lock = threading.RLock()
        self._conn = self._open_connection(self.db_path)
        self._init_schema()

    @staticmethod
    def _open_connection(target: str) -> sqlite3.Connection:
        if target != ":memory:":
            Path(target).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cooldowns (
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    until_epoch REAL NOT NULL,
                    failure_count INTEGER NOT NULL DEFAULT 1,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (provider, model)
                );

                CREATE TABLE IF NOT EXISTS daily_spend (
                    day_utc TEXT PRIMARY KEY,
                    spend_usd REAL NOT NULL DEFAULT 0.0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    requests INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS attempt_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_epoch REAL NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    http_status INTEGER NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT 0.0,
                    detail TEXT NOT NULL DEFAULT ''
                );
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    @staticmethod
    def _utc_day(now_epoch: float | None = None) -> str:
        t = time.time() if now_epoch is None else now_epoch
        return dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).strftime("%Y-%m-%d")

    def is_cooled_down(
        self, provider: str, model: str = "*", *, now_epoch: float | None = None
    ) -> bool:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            rows = self._conn.execute(
                "SELECT until_epoch FROM cooldowns WHERE provider = ? AND model IN (?, '*')",
                (provider, model),
            ).fetchall()
            return any(float(r["until_epoch"]) > now for r in rows)

    def remaining_cooldown_sec(
        self, provider: str, model: str = "*", *, now_epoch: float | None = None
    ) -> float:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            rows = self._conn.execute(
                "SELECT until_epoch FROM cooldowns WHERE provider = ? AND model IN (?, '*')",
                (provider, model),
            ).fetchall()
            rem = [float(r["until_epoch"]) - now for r in rows if float(r["until_epoch"]) > now]
            return round(max(rem), 2) if rem else 0.0

    def record_failure(
        self,
        provider: str,
        model: str = "*",
        *,
        retry_after_sec: float | None = None,
        reason: str = "",
        now_epoch: float | None = None,
    ) -> float:
        """Put `(provider, model)` on exponential cooldown (or explicit `Retry-After`). Returns duration sec."""
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            row = self._conn.execute(
                "SELECT failure_count FROM cooldowns WHERE provider = ? AND model = ?",
                (provider, model),
            ).fetchone()
            failures = int(row["failure_count"]) + 1 if row else 1
            if retry_after_sec is not None and retry_after_sec > 0:
                duration = min(self.cooldown_max_sec, float(retry_after_sec))
            else:
                duration = min(
                    self.cooldown_max_sec, self.cooldown_base_sec * (2 ** min(failures - 1, 8))
                )
            until = now + duration
            self._conn.execute(
                """
                INSERT INTO cooldowns (provider, model, until_epoch, failure_count, reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, model) DO UPDATE SET
                    until_epoch = excluded.until_epoch,
                    failure_count = excluded.failure_count,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (provider, model, until, failures, reason[:240], now),
            )
            self._conn.commit()
            return round(duration, 2)

    def record_success(
        self,
        provider: str,
        model: str = "*",
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        now_epoch: float | None = None,
    ) -> None:
        """Clear cooldown for `(provider, model)` and accumulate daily spend telemetry."""
        now = time.time() if now_epoch is None else now_epoch
        day = self._utc_day(now)
        with self._lock:
            self._conn.execute(
                "DELETE FROM cooldowns WHERE provider = ? AND model IN (?, '*')",
                (provider, model),
            )
            self._conn.execute(
                """
                INSERT INTO daily_spend (day_utc, spend_usd, prompt_tokens, completion_tokens, requests, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(day_utc) DO UPDATE SET
                    spend_usd = daily_spend.spend_usd + excluded.spend_usd,
                    prompt_tokens = daily_spend.prompt_tokens + excluded.prompt_tokens,
                    completion_tokens = daily_spend.completion_tokens + excluded.completion_tokens,
                    requests = daily_spend.requests + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    day,
                    max(0.0, float(estimated_cost_usd)),
                    max(0, int(prompt_tokens)),
                    max(0, int(completion_tokens)),
                    now,
                ),
            )
            self._conn.commit()

    def clear_cooldowns(self, provider: str | None = None) -> int:
        with self._lock:
            if provider:
                cur = self._conn.execute("DELETE FROM cooldowns WHERE provider = ?", (provider,))
            else:
                cur = self._conn.execute("DELETE FROM cooldowns")
            self._conn.commit()
            return cur.rowcount

    def active_cooldowns(self, *, now_epoch: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            rows = self._conn.execute(
                "SELECT provider, model, until_epoch, failure_count, reason FROM cooldowns WHERE until_epoch > ? ORDER BY provider, model",
                (now,),
            ).fetchall()
            return [
                {
                    "provider": r["provider"],
                    "model": r["model"],
                    "remaining_sec": round(float(r["until_epoch"]) - now, 2),
                    "failure_count": int(r["failure_count"]),
                    "reason": r["reason"],
                }
                for r in rows
            ]

    def get_daily_spend(self, *, now_epoch: float | None = None) -> dict[str, Any]:
        day = self._utc_day(now_epoch)
        with self._lock:
            row = self._conn.execute(
                "SELECT day_utc, spend_usd, prompt_tokens, completion_tokens, requests FROM daily_spend WHERE day_utc = ?",
                (day,),
            ).fetchone()
            if not row:
                return {
                    "day_utc": day,
                    "spend_usd": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "requests": 0,
                    "daily_budget_usd": self.daily_budget_usd,
                    "budget_exceeded": False,
                }
            spend = round(float(row["spend_usd"]), 6)
            return {
                "day_utc": row["day_utc"],
                "spend_usd": spend,
                "prompt_tokens": int(row["prompt_tokens"]),
                "completion_tokens": int(row["completion_tokens"]),
                "requests": int(row["requests"]),
                "daily_budget_usd": self.daily_budget_usd,
                "budget_exceeded": bool(
                    self.daily_budget_usd > 0 and spend >= self.daily_budget_usd
                ),
            }

    def is_budget_exceeded(self, *, now_epoch: float | None = None) -> bool:
        if self.daily_budget_usd <= 0:
            return False
        return bool(self.get_daily_spend(now_epoch=now_epoch)["budget_exceeded"])

    def record_attempt(
        self,
        *,
        provider: str,
        model: str,
        ok: bool,
        http_status: int = 0,
        latency_ms: float = 0.0,
        detail: str = "",
        now_epoch: float | None = None,
    ) -> None:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            self._conn.execute(
                "INSERT INTO attempt_log (ts_epoch, provider, model, ok, http_status, latency_ms, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    now,
                    provider,
                    model,
                    1 if ok else 0,
                    int(http_status),
                    round(float(latency_ms), 2),
                    detail[:240],
                ),
            )
            # Keep bounded ring of last 500 attempts
            self._conn.execute(
                "DELETE FROM attempt_log WHERE id NOT IN (SELECT id FROM attempt_log ORDER BY id DESC LIMIT 500)"
            )
            self._conn.commit()

    def recent_attempts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts_epoch, provider, model, ok, http_status, latency_ms, detail FROM attempt_log ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [
                {
                    "ts_epoch": float(r["ts_epoch"]),
                    "provider": r["provider"],
                    "model": r["model"],
                    "ok": bool(r["ok"]),
                    "http_status": int(r["http_status"]),
                    "latency_ms": float(r["latency_ms"]),
                    "detail": r["detail"],
                }
                for r in rows
            ]
