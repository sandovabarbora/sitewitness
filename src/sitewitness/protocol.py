"""The trust protocol, enforced on the answer after the model is done. A prompt asks; this checks."""

from __future__ import annotations

import re
import string
from dataclasses import asdict, dataclass, field

from quotecheck import fold

from sitewitness.config import ProtocolConfig
from sitewitness.index import Index

_PUNCT = str.maketrans("", "", string.punctuation + "…·—–")


def squash(s: str) -> str:
    """fold() plus every punctuation mark removed: a quotation matches on its words alone."""
    return fold(s)[0].translate(_PUNCT)


DECLINE = "I can't answer that from this site."
DECLINE_TAIL = (
    " This assistant answers only from the site's data files and texts, "
    "with every number and quotation traced to a tool result."
)
QUOTE_RUN = re.compile(r"[\"“„][^\"”“]{40,}[\"”“]")
CODE = re.compile(r"```|^\s*(def|import|from)\s+\w|</?[a-zA-Z][^>]*>", re.M)
SOURCES_LINE = re.compile(r"^Sources?:\s*(.+)$", re.M | re.I)


@dataclass
class ToolCall:
    name: str
    input: dict
    ms: int
    bytes: int
    result_status: str | None = None


@dataclass
class Trace:
    model: str = ""
    model_used: str = ""
    turns: int = 0
    tools: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    prices: dict = field(default_factory=dict)
    ms: int = 0
    stop: str | None = None
    declined: bool = False
    numbers_from_tools: bool = False
    quotes_verified: int = 0
    quotes_absent: int = 0
    protocol: dict = field(default_factory=dict)
    enforced: str | None = None
    budget_spent_usd: float = 0.0
    limited: str | None = None
    original: str | None = None  # the model's answer before enforcement replaced it
    evidence: str = (
        ""  # folded text of every tool result in the conversation; quotations are checked against it
    )

    def to_dict(self) -> dict:
        return asdict(self)


def _sources(answer: str) -> tuple[str, list[str]]:
    m = SOURCES_LINE.search(answer)
    if not m:
        return answer, []
    items = [s.strip().strip(".,;") for s in re.split(r"[,;·]", m.group(1)) if s.strip()]
    return answer[: m.start()], items


def _source_known(item: str, index: Index) -> bool:
    item = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", item)  # "surf/data.json (climatology.ericeira)" → the path
    item = item.strip().strip("`'\"()[]<>")
    item = re.sub(r"^https?://[^/]+", "", item).split("#")[0].split("?")[0].strip()
    if not item:
        return True  # an empty token from a stray separator is not a claim
    rel = item.lstrip("/")
    if rel in index.sources or rel.rstrip("/") in index.sources:
        return True
    page = "/" + re.sub(r"\.(html?|md)$", "", rel).strip("/")
    if page in index.pages or (page + "/") in index.pages:
        return True
    # a passage id such as "surf#3" or a bare file stem also names a page the index knows
    stem = rel.split("#")[0].rsplit("/", 1)[-1]
    return any(p.rsplit("/", 1)[-1] == stem for p in index.pages)


def _unverified_quote(body: str, trace: Trace) -> bool:
    """A quotation of 40+ characters counts as verified when the quote tool returned found, or when the
    quoted words occur verbatim (folded) in a tool result of this conversation: the evidence is there."""
    runs = [m.group(0)[1:-1] for m in QUOTE_RUN.finditer(body)]
    if not runs:
        return False
    if trace.quotes_verified:
        return False
    for run in runs:
        needle = squash(run)
        if not needle or needle not in trace.evidence:
            return True
    return False


def enforce(answer: str, trace: Trace, config: ProtocolConfig, index: Index) -> tuple[str, Trace]:
    """First violated rule wins, replaces the answer with the decline, and is named in trace.enforced."""
    body, sources = _sources(answer)
    declined = answer.strip().startswith(DECLINE)
    checks = {
        "require_tool_use": config.require_tool_use and not trace.tools,
        "numbers_need_tool": config.numbers_need_tool
        and bool(re.search(r"\d", body))
        and not trace.numbers_from_tools,
        "forbid_code": config.forbid_code and bool(CODE.search(body)),
        "quotes_need_verification": config.quotes_need_verification and _unverified_quote(body, trace),
        "sources_must_exist": config.sources_must_exist and any(not _source_known(s, index) for s in sources),
    }
    trace.declined = declined
    if declined:
        trace.protocol = dict.fromkeys(checks, False)
        return answer, trace
    trace.protocol = {k: bool(v) for k, v in checks.items()}
    for rule, violated in checks.items():
        if violated:
            trace.enforced = rule
            trace.declined = True
            trace.original = answer
            return DECLINE + DECLINE_TAIL, trace
    return answer, trace
