import json

import pytest

from sitewitness.config import load_config
from sitewitness.index import build_index
from sitewitness.tools import TOOL_SCHEMAS, run_tool


@pytest.fixture
def env(site_dir):
    cfg = load_config(site_dir / "sitewitness.toml")
    return cfg, build_index(cfg)


def run(env, name, **inp):
    cfg, idx = env
    return json.loads(run_tool(name, inp, idx, cfg))


def test_schemas_name_the_five_tools():
    assert {t["name"] for t in TOOL_SCHEMAS} == {
        "list_sources",
        "describe_source",
        "read_data",
        "search",
        "quote",
    }


def test_list_and_describe(env):
    assert run(env, "list_sources") == {
        "data/surf.json": "Surf verification data",
        "data/watch.json": "Watch runs",
    }
    d = run(env, "describe_source", source="data/surf.json")
    assert d["skill"]["x"]["m"]["1"] == {"n": "int", "mae": "float"}
    assert "error" in run(env, "describe_source", source="nope.json")


def test_read_data_path_find_and_clip(env):
    assert run(env, "read_data", source="data/surf.json", path="skill.x.m.1.mae") == 0.42
    assert run(env, "read_data", source="data/surf.json", path="list.1.name") == "two"
    assert run(env, "read_data", source="data/surf.json", path="list", find="two") == [
        {"a": 2, "name": "two"}
    ]
    assert "error" in run(env, "read_data", source="data/surf.json", path="skill.nope")
    cfg, idx = env
    clipped = json.loads(run_tool("read_data", {"source": "data/surf.json"}, idx, cfg, max_bytes=40))
    assert clipped["_truncated"] is True and "keys" in clipped


def test_search_returns_known_passages(env):
    hits = run(env, "search", query="weather models stations")
    assert hits and hits[0]["id"].startswith("b#") and {"id", "page", "title", "text"} <= set(hits[0])


def test_quote_folds_like_quotecheck(env):
    found = run(env, "quote", passage_id="a#1", phrase="iam is a wall")
    assert found["status"] == "found" and "IAM is a wall" in found["passage"]
    hyph = run(env, "quote", passage_id="a#0", phrase="sixty eight millimetres")
    assert hyph["status"] == "found"
    assert run(env, "quote", passage_id="a#1", phrase="IAM is a suggestion")["status"] == "absent"
    assert run(env, "quote", passage_id="zz#9", phrase="x")["status"] == "absent"


def test_unknown_tool(env):
    assert "error" in run(env, "nope")
