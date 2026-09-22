"""Five tools: their Anthropic schemas and one runner. Everything the model learns about the site
comes through here, which is what makes the trust protocol checkable."""

from __future__ import annotations

import json
from typing import Any

from quotecheck import fold

from sitewitness.config import Config
from sitewitness.index import Embedder, Index

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_sources",
        "description": "List the site's data files, one line each. Call this first for any question about numbers.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_source",
        "description": "Schema of one data file: keys, types, array lengths and ranges. Use it to find the right path before read_data.",
        "input_schema": {
            "type": "object",
            "properties": {"source": {"type": "string"}},
            "required": ["source"],
        },
    },
    {
        "name": "read_data",
        "description": "Read part of a data file. `path` is dotted/indexed (e.g. 'skill.x.m.1'); for an array, pass `find` (a substring such as a date, an alias or a name) to get only the matching items in one call instead of reading items one by one. Output is clipped, so narrow the path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "path": {"type": "string"},
                "find": {"type": "string"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "search",
        "description": "Search the site's texts. Returns up to k passages (paragraphs) with ids, page URLs and full text. To quote from one, call quote with its id.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
            "required": ["query"],
        },
    },
    {
        "name": "quote",
        "description": "Verify that a phrase occurs verbatim in a passage (by id) before quoting it. Never quote a phrase that did not come back 'found'.",
        "input_schema": {
            "type": "object",
            "properties": {"passage_id": {"type": "string"}, "phrase": {"type": "string"}},
            "required": ["passage_id", "phrase"],
        },
    },
]


def dig(obj: Any, path: str) -> Any:
    cur = obj
    for k in [k for k in path.split(".") if k]:
        if isinstance(cur, list):
            try:
                cur = cur[int(k)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
        if cur is None:
            return None
    return cur


def clip(v: Any, max_bytes: int) -> str:
    s = json.dumps(v, ensure_ascii=False)
    if len(s.encode()) <= max_bytes:
        return s
    if isinstance(v, dict):
        return json.dumps({"_truncated": True, "keys": list(v)[:50]})
    if isinstance(v, list):
        return json.dumps(
            {"_truncated": True, "array": len(v), "first": v[0] if v else None}, ensure_ascii=False
        )[:max_bytes]
    return s[:max_bytes] + "…"


def run_tool(
    name: str,
    input: dict,
    index: Index,
    config: Config,
    max_bytes: int = 3000,
    embedder: Embedder | None = None,
) -> str:
    inp = input or {}
    if name == "list_sources":
        return json.dumps({k: v["description"] for k, v in index.sources.items()}, ensure_ascii=False)
    if name == "describe_source":
        src = index.sources.get(str(inp.get("source", "")))
        return json.dumps(
            src["schema"] if src else {"error": "unknown source; call list_sources"}, ensure_ascii=False
        )
    if name == "read_data":
        rel = str(inp.get("source", ""))
        if rel not in index.sources:
            return json.dumps({"error": "unknown source; call list_sources"})
        p = config.site.root / rel
        if not p.exists():
            return json.dumps({"error": "file not found"})
        v = dig(json.loads(p.read_text(encoding="utf-8")), str(inp.get("path", "")))
        if v is None:
            return json.dumps({"error": "path not found"})
        if isinstance(v, list) and inp.get("find"):
            f = str(inp["find"]).lower()
            v = [x for x in v if f in json.dumps(x, ensure_ascii=False).lower()][:20]
        return clip(v, max_bytes)
    if name == "search":
        k = int(inp.get("k") or 6)
        hits = index.search(str(inp.get("query", "")), k=k, embedder=embedder)
        return json.dumps(
            [{"id": p.id, "page": p.page, "title": p.title, "text": p.text[:1500]} for p in hits],
            ensure_ascii=False,
        )
    if name == "quote":
        p = index.get(str(inp.get("passage_id", "")))
        if p is None:
            return json.dumps({"status": "absent", "reason": "no such passage"})
        needle, _ = fold(str(inp.get("phrase", "")))
        hay, _ = fold(p.text)
        if needle and needle in hay:
            return json.dumps({"status": "found", "passage": p.text, "page": p.page}, ensure_ascii=False)
        return json.dumps({"status": "absent", "passage": p.text[:300], "page": p.page}, ensure_ascii=False)
    return json.dumps({"error": f"unknown tool {name}"})
