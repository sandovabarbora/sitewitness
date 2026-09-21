"""One interface between the agent and a model, so tests never touch the network."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Block:
    type: str  # "text" | "tool_use"
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class Response:
    content: list[Block]
    stop_reason: str = "end_turn"
    usage_in: int = 0
    usage_out: int = 0
    model: str = ""


class ModelClient(Protocol):
    def create(
        self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int
    ) -> Response: ...


class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None):
        import anthropic

        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def create(
        self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int
    ) -> Response:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        r = self._client.messages.create(**kwargs)
        blocks = []
        for b in r.content:
            if b.type == "text":
                blocks.append(Block("text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(Block("tool_use", id=b.id, name=b.name, input=dict(b.input or {})))
        return Response(
            blocks, r.stop_reason or "end_turn", r.usage.input_tokens, r.usage.output_tokens, r.model
        )


def to_api_content(blocks: list[Block]) -> list[dict]:
    out = []
    for b in blocks:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        else:
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out
