"""The trust protocol, enforced on the answer after the model is done. A prompt asks; this checks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sitewitness.config import ProtocolConfig
from sitewitness.index import Index

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

    def to_dict(self) -> dict:
        return asdict(self)


def _sources(answer: str) -> tuple[str, list[str]]:
    m = SOURCES_LINE.search(answer)
    if not m:
        return answer, []
    items = [s.strip().strip(".,;") for s in re.split(r"[,;·]", m.group(1)) if s.strip()]
    return answer[: m.start()], items


def _source_known(item: str, index: Index) -> bool:
    item = re.sub(r"^https?://[^/]+", "", item).split("#")[0].split("?")[0]
    if item in index.sources or item.lstrip("/") in index.sources:
        return True
    page = "/" + item.strip("/")
    return page in index.pages or page.rstrip("/") in index.pages or (page + "/") in index.pages


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
        "quotes_need_verification": config.quotes_need_verification
        and bool(QUOTE_RUN.search(body))
        and trace.quotes_verified == 0,
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
            return DECLINE + DECLINE_TAIL, trace
    return answer, trace
