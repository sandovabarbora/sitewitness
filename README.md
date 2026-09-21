# sitewitness

An agent over your site that shows its work.

Point it at a folder of texts (HTML or Markdown) and JSON data files, and you get a
question-answering API with a **trust protocol enforced in code**, an evaluation runner, and a
static page that shows every answer's trace. First instance: [bsandova.com/ask](https://bsandova.com/ask/).

```bash
pip install sitewitness            # add [embed] for local embeddings (sentence-transformers)
sitewitness index                  # texts → passages + BM25 (+ embeddings), data files → schemas
sitewitness serve --port 8000      # POST /ask {question} · GET /health
sitewitness ask "How many …?"      # one question from the terminal, trace on stderr
sitewitness eval golden.json --api http://localhost:8000
sitewitness page ask/ --api https://api.example.com --example "How many …?"
```

## The protocol

Five rules, each a check in `protocol.py`, each a flag in the trace. The first violation replaces
the answer with a refusal and names itself in `trace.enforced`.

| rule | what it catches |
|---|---|
| `require_tool_use` | an answer produced without calling any tool |
| `numbers_need_tool` | a digit in the answer with no `read_data` or `search` result in the conversation |
| `forbid_code` | fenced code, `def`/`import`, or HTML in the answer |
| `quotes_need_verification` | a quotation of 40+ characters without a `quote` call that came back *found* |
| `sources_must_exist` | a `Sources:` line naming a file or page the site does not have |

Plus caps: tool calls, output tokens, wall time; a budget per UTC day; a rate per address per
hour. Rules are switched only in `sitewitness.toml`, never by a prompt.

## Tools the model gets

`list_sources` · `describe_source` (schema of a JSON file) · `read_data` (dotted path, `find`
filter, clipped) · `search` (BM25, plus embeddings with reciprocal rank fusion when present) ·
`quote` (verbatim check through [quotecheck](https://pypi.org/project/quotecheck/)'s fold).

## Config

```toml
[site]
name = "example.com"
base_url = "https://example.com"
texts = ["texts/**/*.html"]
[site.data]
"surf/data.json" = "Surf forecast verification: skill by lead, quality counts."

[model]
name = "claude-sonnet-5"
max_output_tokens = 700
price_in_per_m = 3.0      # configured list prices; the trace says so
price_out_per_m = 15.0

[limits]
max_tool_calls = 8
daily_budget_usd = 4.0
per_ip_per_hour = 12
store = "sqlite:.sitewitness/limits.db"

[server]
allowed_origins = ["https://example.com"]
eval_key_env = "SITEWITNESS_EVAL_KEY"   # X-Eval-Key bypasses the per-address limit, never the budget
```

`ANTHROPIC_API_KEY` in the environment. Every trace carries: model requested and used, turns,
tools with inputs and sizes, tokens, cost from the configured prices, the protocol flags, what was
enforced, and today's budget.

## Evaluation

`golden.json`: `{"questions": [{"q": "…", "kind": "number|text|quote|decline", "expect": "…"}]}`.
`sitewitness eval` scores each question (substring match, or a refusal when `expect` is
`DECLINE`), counts protocol violations from the traces, writes `eval.json` and appends to
`eval-history.json`, and exits 1 when misses exceed `--allowed-misses`, so it can gate a deploy.

No framework, no network in the 44 tests. Apache-2.0.
