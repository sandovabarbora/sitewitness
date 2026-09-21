"""sitewitness index | serve | ask | eval | page"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sitewitness import __version__
from sitewitness.config import Config, load_config
from sitewitness.index import Index, build_index


def _agent(config: Config, embed: bool = False):
    from sitewitness.agent import Agent
    from sitewitness.limits import Gate, store_from_config

    idx = Index.load(config.index_dir) if (config.index_dir / "index.json").exists() else build_index(config)
    embedder = None
    if embed or (config.index_dir / "embeddings.json").exists():
        try:
            from sitewitness.index import SentenceTransformersEmbedder

            embedder = SentenceTransformersEmbedder()
        except ImportError:
            print(
                "embeddings present but sentence-transformers is not installed; searching with BM25 only",
                file=sys.stderr,
            )
    if os.environ.get("SITEWITNESS_FAKE"):
        from sitewitness.client import Block, Response

        class Fake:
            def create(self, system, messages, tools, max_tokens):
                return Response(
                    [Block("text", text="I can't answer that from this site. (fake client)")],
                    "end_turn",
                    10,
                    5,
                    "fake",
                )

        client = Fake()
    else:
        from sitewitness.client import AnthropicClient

        client = AnthropicClient(config.model.name)
    return Agent(
        config, idx, client, Gate(store_from_config(config.limits.store), config.limits), embedder=embedder
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="sitewitness", description="An agent over your site that shows its work."
    )
    p.add_argument("--config", default="sitewitness.toml")
    p.add_argument("--version", action="version", version=f"sitewitness {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("index", help="build the passage index and data schemas")
    s.add_argument(
        "--embed", action="store_true", help="also compute sentence-transformers embeddings (extra [embed])"
    )
    s = sub.add_parser("serve", help="run the API")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s = sub.add_parser("ask", help="ask one question from the terminal")
    s.add_argument("question")
    s = sub.add_parser("eval", help="run golden questions against a live API")
    s.add_argument("golden")
    s.add_argument("--api", required=True)
    s.add_argument("--allowed-misses", type=int, default=0)
    s.add_argument("--out", default=".")
    s.add_argument("--pause", type=float, default=0.5)
    s = sub.add_parser("page", help="write the static Ask page")
    s.add_argument("out_dir")
    s.add_argument("--api", required=True)
    s.add_argument("--example", action="append", default=[])
    s.add_argument("--css", help="href of an extra stylesheet to include")
    a = p.parse_args(argv)
    config = load_config(a.config)

    if a.cmd == "index":
        embedder = None
        if a.embed:
            from sitewitness.index import SentenceTransformersEmbedder

            embedder = SentenceTransformersEmbedder()
        idx = build_index(config, embedder=embedder)
        print(f"{len(idx.passages)} passages, {len(idx.sources)} data files → {config.index_dir}")
        return 0
    if a.cmd == "serve":
        import uvicorn

        from sitewitness.server import create_app

        uvicorn.run(create_app(_agent(config), config), host=a.host, port=a.port)
        return 0
    if a.cmd == "ask":
        ans = _agent(config).ask(a.question, ip="cli")
        print(ans.text)
        print(json.dumps(ans.trace.to_dict(), indent=1, ensure_ascii=False), file=sys.stderr)
        return 0
    if a.cmd == "eval":
        from sitewitness.evaluate import exit_code, http_asker, run_eval, write_eval

        golden = json.loads(Path(a.golden).read_text())
        golden = golden["questions"] if isinstance(golden, dict) else golden
        summary, rows = run_eval(
            golden, http_asker(a.api, os.environ.get(config.server.eval_key_env)), api=a.api, pause=a.pause
        )
        write_eval(summary, rows, Path(a.out))
        for r in rows:
            print(
                ("OK  " if r["ok"] else "MISS"),
                r.get("kind", "")[:6].ljust(6),
                r["q"][:60],
                "→",
                (r.get("answer") or r.get("error") or "")[:70].replace("\n", " "),
            )
        print(json.dumps(summary, indent=1))
        return exit_code(summary, a.allowed_misses)
    if a.cmd == "page":
        from sitewitness.page import render_page

        out = render_page(config, a.api, a.example, Path(a.out_dir), a.css)
        print(f"wrote {out}")
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
