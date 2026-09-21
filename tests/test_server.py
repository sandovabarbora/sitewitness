import pytest
from conftest import FakeClient, text, tool
from fastapi.testclient import TestClient

from sitewitness.agent import Agent
from sitewitness.config import load_config
from sitewitness.index import build_index
from sitewitness.limits import Gate, MemoryStore
from sitewitness.protocol import DECLINE
from sitewitness.server import create_app


@pytest.fixture
def app_factory(site_dir, monkeypatch):
    def make(script, per_ip=2):
        cfg = load_config(site_dir / "sitewitness.toml")
        cfg.limits.per_ip_per_hour = per_ip
        agent = Agent(cfg, build_index(cfg), FakeClient(script), Gate(MemoryStore(), cfg.limits))
        monkeypatch.setenv("SITEWITNESS_EVAL_KEY", "sekret")
        return TestClient(create_app(agent, cfg)), cfg

    return make


def test_bad_body_400(app_factory):
    c, _ = app_factory([])
    assert c.post("/ask", content=b"nope", headers={"content-type": "application/json"}).status_code == 400
    assert c.post("/ask", json={"question": "hi"}).status_code == 400


def test_ask_200_with_trace(app_factory):
    c, _ = app_factory([tool("list_sources", {}), text(DECLINE + " Only surf data.")])
    r = c.post("/ask", json={"question": "what is here?"}, headers={"Origin": "https://example.test"})
    assert (
        r.status_code == 200
        and r.json()["answer"].startswith(DECLINE)
        and r.json()["trace"]["tools"][0]["name"] == "list_sources"
    )
    assert r.headers.get("access-control-allow-origin") == "https://example.test"


def test_upstream_error_502(app_factory):
    c, _ = app_factory([RuntimeError("boom")])
    r = c.post("/ask", json={"question": "what is here?"})
    assert r.status_code == 502 and "boom" not in r.json()["error"]


def test_health(app_factory):
    c, _ = app_factory([])
    h = c.get("/health").json()
    assert h["ok"] and h["site"] == "fixture" and h["index"]["passages"] == 6 and h["budget_usd"] == 1.0


def test_eval_key_bypasses_rate_only(app_factory):
    script = [text(DECLINE + " x")] * 5
    c, _ = app_factory(script, per_ip=1)
    assert c.post("/ask", json={"question": "one?"}).json()["trace"]["limited"] is None
    assert c.post("/ask", json={"question": "two?"}).json()["trace"]["limited"] == "rate"
    assert (
        c.post("/ask", json={"question": "three?"}, headers={"X-Eval-Key": "sekret"}).json()["trace"][
            "limited"
        ]
        is None
    )
    assert (
        c.post("/ask", json={"question": "four?"}, headers={"X-Eval-Key": "wrong"}).json()["trace"]["limited"]
        == "rate"
    )


def test_forwarded_header_is_ignored_unless_trusted(site_dir, monkeypatch):
    from sitewitness.server import client_ip

    class R:
        headers = {"X-Forwarded-For": "9.9.9.9, 1.1.1.1", "CF-Connecting-IP": "8.8.8.8"}

        class client:
            host = "127.0.0.1"

    assert client_ip(R()) == "127.0.0.1"
    assert client_ip(R(), "CF-Connecting-IP") == "8.8.8.8"
    assert client_ip(R(), "X-Forwarded-For") == "9.9.9.9"
