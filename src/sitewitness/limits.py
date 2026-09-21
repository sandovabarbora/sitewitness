"""A budget per UTC day and a rate per address per UTC hour, on a pluggable store."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from sitewitness.config import LimitsConfig


class LimitStore(Protocol):
    def get(self, key: str) -> float: ...
    def add(self, key: str, delta: float, ttl: int) -> float: ...


class MemoryStore:
    def __init__(self, now: Callable[[], float] = time.time):
        self._d: dict[str, tuple[float, float]] = {}
        self._now = now

    def get(self, key: str) -> float:
        v = self._d.get(key)
        if not v or v[1] <= self._now():
            self._d.pop(key, None)
            return 0.0
        return v[0]

    def add(self, key: str, delta: float, ttl: int) -> float:
        cur = self.get(key)
        self._d[key] = (cur + delta, self._now() + ttl)
        return cur + delta


class SqliteStore:
    def __init__(self, path: str | Path, now: Callable[[], float] = time.time):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        with sqlite3.connect(self.path) as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, value REAL NOT NULL, expires REAL NOT NULL)"
            )

    def get(self, key: str) -> float:
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT value, expires FROM limits WHERE key = ?", (key,)).fetchone()
            if not row or row[1] <= self._now():
                c.execute("DELETE FROM limits WHERE key = ?", (key,))
                return 0.0
            return float(row[0])

    def add(self, key: str, delta: float, ttl: int) -> float:
        cur = self.get(key)
        with sqlite3.connect(self.path) as c:
            c.execute(
                "INSERT OR REPLACE INTO limits (key, value, expires) VALUES (?, ?, ?)",
                (key, cur + delta, self._now() + ttl),
            )
        return cur + delta


def store_from_config(spec: str, now: Callable[[], float] = time.time) -> LimitStore:
    if spec == "memory":
        return MemoryStore(now=now)
    if spec.startswith("sqlite:"):
        return SqliteStore(spec[7:], now=now)
    raise ValueError(f"unknown limit store {spec!r} (use 'memory' or 'sqlite:PATH')")


class Gate:
    def __init__(self, store: LimitStore, config: LimitsConfig, now: Callable[[], float] = time.time):
        self.store, self.config, self._now = store, config, now

    def _day(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).strftime("%Y-%m-%d")

    def _hour(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).strftime("%Y-%m-%dT%H")

    def spent_today(self) -> float:
        return self.store.get(f"budget:{self._day()}")

    def check(self, ip: str, eval_run: bool = False) -> str | None:
        """None when the question may proceed (and the address counter is incremented), else 'budget' or 'rate'."""
        if self.spent_today() >= self.config.daily_budget_usd:
            return "budget"
        key = f"ip:{ip}:{self._hour()}"
        if not eval_run and self.store.get(key) >= self.config.per_ip_per_hour:
            return "rate"
        if not eval_run:
            self.store.add(key, 1.0, ttl=3600)
        return None

    def spend(self, cost_usd: float) -> float:
        return self.store.add(f"budget:{self._day()}", cost_usd, ttl=172800)
