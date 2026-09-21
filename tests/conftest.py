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
