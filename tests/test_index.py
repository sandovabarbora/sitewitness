import json

from sitewitness.config import load_config
from sitewitness.index import Index, build_index, describe_json, extract_passages, rrf


class StubEmbedder:
    """Each text → a 3-vector: [has 'wheelbase', has 'surf', has 'weather'] with a small bias so
    paraphrases (e.g. 'axle distance' ≈ wheelbase) land next to the intended passage."""

    SYN = {
        "wheelbase": 0,
        "axle": 0,
        "millimetres": 0,
        "surf": 1,
        "surfable": 1,
        "waves": 1,
        "weather": 2,
        "models": 2,
        "stations": 2,
    }

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.01, 0.01, 0.01]
            for w, i in self.SYN.items():
                if w in t.lower():
                    v[i] += 1.0
            out.append(v)
        return out


def test_html_passages(site_dir):
    ps = extract_passages(site_dir / "texts" / "a.html", site_dir)
    assert [p.id for p in ps] == ["a#0", "a#1", "a#2"]
    assert ps[0].page == "/texts/a" and ps[0].title == "Alpha text"
    assert (
        "1" not in ps[0].text.split()[-1] and "sixty-eight millimetres between 2012 and 2022." in ps[0].text
    )
    assert ps[2].text.startswith("A list item")


def test_markdown_passages(site_dir):
    ps = extract_passages(site_dir / "texts" / "b.md", site_dir)
    assert ps[0].title == "Beta" and ps[0].page == "/texts/b" and len(ps) == 3
    assert ps[1].text.startswith("Beta list item")


def test_describe_json(site_dir):
    d = describe_json(json.loads((site_dir / "data" / "surf.json").read_text()))
    assert d["generated"] == "str" and d["skill"]["x"]["m"]["1"] == {"n": "int", "mae": "float"}
    assert d["list"] == {"array": 2, "item_keys": ["a", "name"]}
    assert d["vals"] == {"array": 3, "min": 0.5, "max": 2.5}


def test_build_search_and_roundtrip(site_dir):
    cfg = load_config(site_dir / "sitewitness.toml")
    idx = build_index(cfg)
    assert (cfg.index_dir / "index.json").exists()
    assert (
        set(idx.sources) == {"data/surf.json", "data/watch.json"}
        and "schema" in idx.sources["data/surf.json"]
    )
    assert idx.pages == {"/texts/a", "/texts/b"}
    assert idx.search("beta surfable rule")[0].id.startswith("b#")
    assert idx.get("a#1").text.startswith("A second")
    again = Index.load(cfg.index_dir)
    assert [p.id for p in again.passages] == [p.id for p in idx.passages]
    assert again.search("wall")[0].id == "a#1"


def test_embeddings_find_a_paraphrase(site_dir):
    cfg = load_config(site_dir / "sitewitness.toml")
    build_index(cfg, embedder=StubEmbedder())
    assert (cfg.index_dir / "embeddings.json").exists()
    hits = Index.load(cfg.index_dir).search("axle distance growth", k=3, embedder=StubEmbedder())
    assert hits[0].id == "a#0"


def test_rrf_merges_rankings():
    assert rrf([["a", "b", "c"], ["c", "a"]])[:2] == ["a", "c"]
