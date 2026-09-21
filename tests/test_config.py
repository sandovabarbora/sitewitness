from sitewitness.config import load_config


def test_loads_every_section(site_dir):
    c = load_config(site_dir / "sitewitness.toml")
    assert c.site.name == "fixture" and c.site.root == site_dir.resolve()
    assert c.site.data["data/surf.json"] == "Surf verification data"
    assert c.model.name == "test-model" and c.model.price_out_per_m == 10.0
    assert c.limits.max_tool_calls == 3 and c.limits.store == "memory"
    assert c.server.allowed_origins == ["https://example.test"]
    assert c.index_dir == site_dir.resolve() / ".sitewitness"


def test_defaults_when_sections_missing(tmp_path):
    p = tmp_path / "sitewitness.toml"
    p.write_text('[site]\nname = "x"\n')
    c = load_config(p)
    assert c.model.name == "claude-sonnet-5" and c.limits.max_tool_calls == 8
    assert all(vars(c.protocol).values())
    assert c.limits.store == f"sqlite:{tmp_path.resolve() / '.sitewitness/limits.db'}"
    assert c.server.eval_key_env == "SITEWITNESS_EVAL_KEY"
