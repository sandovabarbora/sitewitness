"""FastAPI around the agent: POST /ask, GET /health, CORS from config, eval key for the per-IP limit."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sitewitness import __version__
from sitewitness.agent import Agent
from sitewitness.config import Config


def client_ip(request: Request) -> str:
    for h in ("CF-Connecting-IP", "X-Forwarded-For"):
        v = request.headers.get(h)
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
        eval_run = bool(key) and request.headers.get("X-Eval-Key") == key
        try:
            return agent.ask(q, ip=client_ip(request), eval_run=eval_run).to_dict()
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:300]}, status_code=502)

    return app
