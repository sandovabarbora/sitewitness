"""FastAPI around the agent: POST /ask, GET /health, CORS from config, eval key for the per-IP limit."""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sitewitness import __version__
from sitewitness.agent import Agent
from sitewitness.config import Config

log = logging.getLogger("sitewitness")


def client_ip(request: Request, trusted_header: str = "") -> str:
    if trusted_header:
        v = request.headers.get(trusted_header)
        if v:
            return v.split(",")[0].strip()
    return request.client.host if request.client else "0"


def create_app(agent: Agent, config: Config) -> FastAPI:
    app = FastAPI(title=f"sitewitness · {config.site.name}", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.allowed_origins,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["content-type", "x-eval-key"],
    )

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "site": config.site.name,
            "model": config.model.name,
            "budget_usd": config.limits.daily_budget_usd,
            "spent_today_usd": round(agent.gate.spent_today(), 5),
            "index": {"passages": len(agent.index.passages), "sources": len(agent.index.sources)},
            "version": __version__,
        }

    @app.post("/ask")
    async def ask(request: Request):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "json body with `question`"}, status_code=400)
        q = str((body or {}).get("question", "")).strip()
        if len(q) < 3:
            return JSONResponse({"error": "ask something"}, status_code=400)
        key = os.environ.get(config.server.eval_key_env, "")
        given = request.headers.get("X-Eval-Key", "")
        eval_run = bool(key) and hmac.compare_digest(given.encode(), key.encode())
        try:
            return agent.ask(
                q, ip=client_ip(request, config.server.trusted_ip_header), eval_run=eval_run
            ).to_dict()
        except Exception:  # noqa: BLE001 - the model or a tool failed; details go to the log, not the client
            log.exception("ask failed")
            return JSONResponse({"error": "the assistant could not answer right now"}, status_code=502)

    return app
