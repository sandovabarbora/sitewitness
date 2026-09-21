import json
from pathlib import Path

import pytest

HTML_A = """<!doctype html><html><head><title>t</title></head><body>
<h1>Alpha <em>text</em></h1>
<p class="kicker">Short kicker here.</p>
<p>The alpha passage says that the wheelbase of new cars grew by sixty-eight millimetres
between 2012 and 2022<sup class="cite"><a href="#r1">1</a></sup>.</p>
<p>A second alpha passage states plainly: a prompt is a suggestion, IAM is a wall,
and that is the whole point.</p>
<p>Too short.</p>
<ul><li>A list item long enough to count as a passage of its own, with eight words at least.</li></ul>
</body></html>"""

MD_B = """# Beta

The beta document explains that surfable days are counted with a fixed rule about height and period.

- Beta list item about the surf rule that also has more than eight words in it.

Another beta paragraph mentioning that the weather page verifies four models against two stations.
"""

TOML = """
[site]
name = "fixture"
base_url = "https://example.test"
texts = ["texts/**/*.html", "texts/**/*.md"]

[site.data]
"data/surf.json" = "Surf verification data"
"data/watch.json" = "Watch runs"

[model]
name = "test-model"
max_output_tokens = 200
price_in_per_m = 1.0
price_out_per_m = 10.0

[limits]
max_tool_calls = 3
daily_budget_usd = 1.0
per_ip_per_hour = 2
store = "memory"

[server]
allowed_origins = ["https://example.test"]
"""


@pytest.fixture
def site_dir(tmp_path: Path) -> Path:
    (tmp_path / "texts").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "texts" / "a.html").write_text(HTML_A)
    (tmp_path / "texts" / "b.md").write_text(MD_B)
    (tmp_path / "data" / "surf.json").write_text(
        json.dumps(
            {
                "generated": "2026-09-15",
                "skill": {"x": {"m": {"1": {"n": 14, "mae": 0.42}}}},
                "list": [{"a": 1, "name": "one"}, {"a": 2, "name": "two"}],
                "vals": [0.5, 2.5, 1.0],
            }
        )
    )
    (tmp_path / "data" / "watch.json").write_text(
        json.dumps([{"date": "2026-08-20", "alias": "opus"}, {"date": "2026-09-14", "alias": "haiku"}])
    )
    (tmp_path / "sitewitness.toml").write_text(TOML)
    return tmp_path


class FakeClient:
    """Returns scripted responses in order and records what it was asked."""

    def __init__(self, script, model="test-model-2026"):
        from collections import deque

        self.script = deque(script)
        self.calls = []
        self.model = model

    def create(self, system, messages, tools, max_tokens):
        from sitewitness.client import Response

        self.calls.append(
            {
                "system": system,
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        if not self.script:
            raise RuntimeError("script exhausted")
        r = self.script.popleft()
        if isinstance(r, Exception):
            raise r
        if not r.model:
            r = Response(r.content, r.stop_reason, r.usage_in, r.usage_out, self.model)
        return r


def text(t, usage=(100, 20)):
    from sitewitness.client import Block, Response

    return Response([Block("text", text=t)], "end_turn", *usage)


def tool(name, inp, tid="t1", usage=(100, 10), pre_text=""):
    from sitewitness.client import Block, Response

    blocks = ([Block("text", text=pre_text)] if pre_text else []) + [
        Block("tool_use", id=tid, name=name, input=inp)
    ]
    return Response(blocks, "tool_use", *usage)


@pytest.fixture
def agent_factory(site_dir):
    from sitewitness.agent import Agent
    from sitewitness.config import load_config
    from sitewitness.index import build_index
    from sitewitness.limits import Gate, MemoryStore

    def make(script, limits=None):
        cfg = load_config(site_dir / "sitewitness.toml")
        if limits:
            for k, v in limits.items():
                setattr(cfg.limits, k, v)
        idx = build_index(cfg)
        client = FakeClient(script)
        return Agent(cfg, idx, client, Gate(MemoryStore(), cfg.limits)), client

    return make
