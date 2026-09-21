import pytest

from sitewitness.config import ProtocolConfig, load_config
from sitewitness.index import build_index
from sitewitness.protocol import DECLINE, ToolCall, Trace, enforce


@pytest.fixture
def idx(site_dir):
    return build_index(load_config(site_dir / "sitewitness.toml"))


def tr(tools=(), data=False, quotes_ok=0, quotes_absent=0):
    t = Trace()
    t.tools = [ToolCall(name=n, input={}, ms=1, bytes=10) for n in tools]
    t.numbers_from_tools = data
    t.quotes_verified, t.quotes_absent = quotes_ok, quotes_absent
    return t


def test_no_tool_use_is_enforced(idx):
    a, t = enforce("The site has three surf spots.\nSources: data/surf.json", tr(), ProtocolConfig(), idx)
    assert a.startswith(DECLINE) and t.enforced == "require_tool_use" and t.declined


def test_number_without_tool(idx):
    a, t = enforce("It grew by 68 mm.\nSources: /texts/a", tr(tools=["quote"]), ProtocolConfig(), idx)
    assert t.enforced == "numbers_need_tool"
    a, t = enforce(
        "It grew by 68 mm.\nSources: /texts/a", tr(tools=["search"], data=True), ProtocolConfig(), idx
    )
    assert t.enforced is None and a.startswith("It grew")


def test_code_in_answer(idx):
    for bad in ("```py\nx=1\n```", "def f():\n  pass", "use <b>bold</b>"):
        _, t = enforce(bad + "\nSources: /texts/a", tr(tools=["search"], data=True), ProtocolConfig(), idx)
        assert t.enforced == "forbid_code", bad


def test_unverified_quote(idx):
    q = '"' + "a" * 45 + '"'
    _, t = enforce(f"It says {q}.\nSources: /texts/a", tr(tools=["search"], data=True), ProtocolConfig(), idx)
    assert t.enforced == "quotes_need_verification"
    _, t = enforce(
        f"It says {q}.\nSources: /texts/a",
        tr(tools=["search", "quote"], data=True, quotes_ok=1),
        ProtocolConfig(),
        idx,
    )
    assert t.enforced is None


def test_sources_must_exist(idx):
    _, t = enforce("Fine.\nSources: nope.json", tr(tools=["search"], data=True), ProtocolConfig(), idx)
    assert t.enforced == "sources_must_exist"
    _, t = enforce(
        "Fine.\nSources: data/surf.json, /texts/a", tr(tools=["search"], data=True), ProtocolConfig(), idx
    )
    assert t.enforced is None
    _, t = enforce(
        "Fine.\nSources: https://example.test/texts/b", tr(tools=["search"], data=True), ProtocolConfig(), idx
    )
    assert t.enforced is None


def test_decline_is_never_enforced(idx):
    a, t = enforce(f"{DECLINE} The site has 3 things.", tr(), ProtocolConfig(), idx)
    assert t.enforced is None and t.declined and a.startswith(DECLINE)


def test_rules_off_in_config(idx):
    cfg = ProtocolConfig(require_tool_use=False, numbers_need_tool=False)
    a, t = enforce("It grew by 68 mm.\nSources: /texts/a", tr(), cfg, idx)
    assert t.enforced is None and a.startswith("It grew")


def test_trace_to_dict_is_json_safe(idx):
    d = tr(tools=["search"]).to_dict()
    assert d["tools"][0]["name"] == "search" and "protocol" in d and "enforced" in d
