"""Golden questions against a live /ask endpoint (or any callable): scores, protocol flags, history."""

from __future__ import annotations

import json
import re
import statistics
import time
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path

DECLINE_MARK = "I can't answer that from this site"


def _norm(s: str) -> str:
    return re.sub(r"[\s ]", "", s.lower())


def score(item: dict, answer: str, trace: dict) -> bool:
    declined = bool(trace.get("declined")) or DECLINE_MARK.lower() in answer.lower()
    if item["expect"] == "DECLINE":
        return declined
    return (not declined) and _norm(str(item["expect"])) in _norm(answer)


def http_asker(api: str, eval_key: str | None = None) -> Callable[[str], dict]:
    def ask(q: str) -> dict:
        req = urllib.request.Request(
            f"{api.rstrip('/')}/ask",
            data=json.dumps({"question": q}).encode(),
            headers={
                "content-type": "application/json",
                "User-Agent": "sitewitness-eval",
                **({"X-Eval-Key": eval_key} if eval_key else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)

    return ask


def run_eval(
    golden: list[dict], ask: Callable[[str], dict], api: str = "", pause: float = 0.0
) -> tuple[dict, list[dict]]:
    rows = []
    for g in golden:
        try:
            out = ask(g["q"])
        except Exception as e:  # noqa: BLE001
            rows.append({**g, "answer": "", "error": str(e)[:200], "ok": False})
            continue
        ans, tr = out.get("answer", ""), out.get("trace", {}) or {}
        violated = bool(tr.get("enforced")) or any((tr.get("protocol") or {}).values())
        rows.append(
            {
                **g,
                "answer": ans,
                "ok": score(g, ans, tr),
                "declined": bool(tr.get("declined")),
                "tools": [t["name"] for t in tr.get("tools", [])],
                "input_tokens": tr.get("input_tokens"),
                "output_tokens": tr.get("output_tokens"),
                "cost_usd": tr.get("cost_usd"),
                "ms": tr.get("ms"),
                "enforced": tr.get("enforced"),
                "protocol_violation": violated,
                "model": tr.get("model_used") or tr.get("model"),
            }
        )
        if pause:
            time.sleep(pause)
    n = len(rows)
    by_kind: dict[str, dict] = {}
    for r in rows:
        k = by_kind.setdefault(r.get("kind", "text"), {"n": 0, "ok": 0})
        k["n"] += 1
        k["ok"] += int(r["ok"])
    ms = [r.get("ms") or 0 for r in rows]
    summary = {
        "date": date.today().isoformat(),
        "api": api,
        "n": n,
        "correct": sum(r["ok"] for r in rows),
        "by_kind": by_kind,
        "protocol_violations": sum(1 for r in rows if r.get("protocol_violation")),
        "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4),
        "median_ms": int(statistics.median(ms)) if ms else 0,
        "model": next((r.get("model") for r in rows if r.get("model")), None),
    }
    return summary, rows


def write_eval(summary: dict, rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False) + "\n"
    )
    hp = out_dir / "eval-history.json"
    hist = json.loads(hp.read_text()) if hp.exists() else []
    hist = [h for h in hist if h.get("date") != summary["date"]] + [summary]
    hp.write_text(json.dumps(hist, indent=1, ensure_ascii=False) + "\n")


def exit_code(summary: dict, allowed_misses: int = 0) -> int:
    return 0 if summary["correct"] >= summary["n"] - allowed_misses else 1
