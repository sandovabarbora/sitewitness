from sitewitness.config import LimitsConfig
from sitewitness.limits import Gate, MemoryStore, SqliteStore, store_from_config


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _store_roundtrip(store, clock):
    assert store.get("k") == 0.0
    assert store.add("k", 1.5, ttl=10) == 1.5
    assert store.add("k", 1.0, ttl=10) == 2.5
    clock.t += 11
    assert store.get("k") == 0.0  # expired


def test_memory_store():
    c = Clock()
    _store_roundtrip(MemoryStore(now=c), c)


def test_sqlite_store(tmp_path):
    c = Clock()
    _store_roundtrip(SqliteStore(tmp_path / "l.db", now=c), c)
    assert isinstance(store_from_config(f"sqlite:{tmp_path / 'x.db'}"), SqliteStore)
    assert isinstance(store_from_config("memory"), MemoryStore)


def test_gate_budget_and_rate():
    c = Clock()
    g = Gate(MemoryStore(now=c), LimitsConfig(daily_budget_usd=1.0, per_ip_per_hour=2), now=c)
    assert g.check("1.1.1.1") is None
    assert g.check("1.1.1.1") is None
    assert g.check("1.1.1.1") == "rate"
    assert g.check("2.2.2.2") is None  # another address
    g.spend(0.6)
    assert g.spent_today() == 0.6
    g.spend(0.5)
    assert g.check("3.3.3.3") == "budget"
    assert g.check("3.3.3.3", eval_run=True) == "budget"  # eval key never bypasses the budget


def test_eval_key_bypasses_rate_only():
    c = Clock()
    g = Gate(MemoryStore(now=c), LimitsConfig(daily_budget_usd=9.0, per_ip_per_hour=1), now=c)
    assert g.check("1.1.1.1") is None and g.check("1.1.1.1") == "rate"
    assert g.check("1.1.1.1", eval_run=True) is None


def test_keys_are_utc_day_and_hour():
    c = Clock(0.0)  # 1970-01-01T00:00Z
    s = MemoryStore(now=c)
    g = Gate(s, LimitsConfig(), now=c)
    g.check("9.9.9.9")
    g.spend(0.1)
    assert s.get("ip:9.9.9.9:1970-01-01T00") == 1.0 and s.get("budget:1970-01-01") == 0.1
