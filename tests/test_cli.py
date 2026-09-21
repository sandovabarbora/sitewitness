import json

from sitewitness.cli import main


def test_index_and_page(site_dir, capsys):
    cfg = str(site_dir / "sitewitness.toml")
    assert main(["--config", cfg, "index"]) == 0
    assert (site_dir / ".sitewitness" / "index.json").exists()
    assert (
        main(
            [
                "--config",
                cfg,
                "page",
                str(site_dir / "ask"),
                "--api",
                "https://api.example.test/",
                "--example",
                "How many?",
                "--css",
                "/style.css",
            ]
        )
        == 0
    )
    html = (site_dir / "ask" / "index.html").read_text()
    assert (
        '"https://api.example.test"' in html
        and '["How many?"]' in html
        and 'href="/style.css"' in html
        and "Ask fixture" in html
    )


def test_ask_with_fake_client(site_dir, capsys, monkeypatch):
    monkeypatch.setenv("SITEWITNESS_FAKE", "1")
    assert main(["--config", str(site_dir / "sitewitness.toml"), "ask", "what is here?"]) == 0
    out, err = capsys.readouterr()
    assert out.startswith("I can't answer") and json.loads(err)["model_used"] == "fake"


def test_eval_exit_code(site_dir, tmp_path, monkeypatch):
    golden = tmp_path / "g.json"
    golden.write_text(
        json.dumps(
            {
                "questions": [
                    {"q": "x?", "kind": "decline", "expect": "DECLINE"},
                    {"q": "y?", "kind": "number", "expect": "42"},
                ]
            }
        )
    )
    import sitewitness.cli as cli

    monkeypatch.setattr(cli, "load_config", lambda p: cli.load_config(site_dir / "sitewitness.toml"))
    from sitewitness import evaluate

    monkeypatch.setattr(
        evaluate,
        "http_asker",
        lambda api, key=None: (
            lambda q: {"answer": "I can't answer that from this site.", "trace": {"declined": True}}
        ),
    )
    assert main(["eval", str(golden), "--api", "http://x", "--out", str(tmp_path), "--pause", "0"]) == 1
    assert (
        main(
            [
                "eval",
                str(golden),
                "--api",
                "http://x",
                "--out",
                str(tmp_path),
                "--pause",
                "0",
                "--allowed-misses",
                "1",
            ]
        )
        == 0
    )
    assert (tmp_path / "eval-history.json").exists()
