import json

from sitewitness.evaluate import exit_code, run_eval, score, write_eval

G = [
    {"q": "how many?", "kind": "number", "expect": "2 263"},
    {"q": "phone?", "kind": "decline", "expect": "DECLINE"},
    {"q": "who?", "kind": "text", "expect": "klementinum"},
]


def test_score_normalises_spaces_and_case():
    assert score(G[0], "About 2263 stalls.", {})
    assert score(G[0], "About 2 263 stalls.", {})
    assert not score(G[0], "I can't answer that from this site.", {"declined": True})
    assert score(G[1], "I can't answer that from this site.", {"declined": True})
    assert not score(G[1], "555-1234", {})
    assert score(G[2], "Ruzyně and Klementinum.", {})


def test_run_eval_and_history(tmp_path):
    answers = {
        "how many?": {
            "answer": "2 263 stalls.\nSources: x",
            "trace": {
                "tools": [{"name": "read_data"}],
                "cost_usd": 0.01,
                "ms": 100,
                "model_used": "m",
                "protocol": {},
            },
        },
        "phone?": {
            "answer": "I can't answer that from this site.",
            "trace": {"declined": True, "cost_usd": 0.002, "ms": 50, "protocol": {}},
        },
        "who?": {
            "answer": "Nobody",
            "trace": {
                "enforced": "require_tool_use",
                "cost_usd": 0.003,
                "ms": 70,
                "protocol": {"require_tool_use": True},
            },
        },
    }
    s, rows = run_eval(G, lambda q: answers[q], api="http://x")
    assert s["n"] == 3 and s["correct"] == 2 and s["protocol_violations"] == 1 and s["model"] == "m"
    assert s["by_kind"]["decline"] == {"n": 1, "ok": 1} and round(s["cost_usd"], 3) == 0.015
    write_eval(s, rows, tmp_path)
    write_eval({**s, "date": "2000-01-01"}, rows, tmp_path)
    hist = json.loads((tmp_path / "eval-history.json").read_text())
    assert [h["date"] for h in hist] == [s["date"], "2000-01-01"]
    assert exit_code(s) == 1 and exit_code(s, allowed_misses=1) == 0


def test_error_rows_are_kept():
    def boom(q):
        raise RuntimeError("down")

    s, rows = run_eval(G[:1], boom)
    assert s["correct"] == 0 and rows[0]["error"] == "down"
