"""sitewitness.toml → Config. Missing sections take the documented defaults; nothing is read from
the environment here except what the config names (the eval key variable)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


@dataclass
class SiteConfig:
    name: str = "site"
    base_url: str = ""
    texts: list[str] = field(default_factory=lambda: ["**/*.html", "**/*.md"])
    data: dict[str, str] = field(default_factory=dict)
    root: Path = Path(".")


@dataclass
class ModelConfig:
    name: str = "claude-sonnet-5"
    max_output_tokens: int = 700
    price_in_per_m: float = 3.0
    price_out_per_m: float = 15.0


@dataclass
class LimitsConfig:
    max_tool_calls: int = 8
    max_wall_seconds: int = 60
    daily_budget_usd: float = 4.0
    per_ip_per_hour: int = 12
    store: str = "sqlite:.sitewitness/limits.db"


@dataclass
class ProtocolConfig:
    numbers_need_tool: bool = True
    quotes_need_verification: bool = True
    require_tool_use: bool = True
    forbid_code: bool = True
    sources_must_exist: bool = True


@dataclass
class ServerConfig:
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:8000"])
    eval_key_env: str = "SITEWITNESS_EVAL_KEY"


@dataclass
class Config:
    site: SiteConfig
    model: ModelConfig
    limits: LimitsConfig
    protocol: ProtocolConfig
    server: ServerConfig
    index_dir: Path


def _fill(cls, section: dict):
    known = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in section.items() if k in known})


def load_config(path: str | Path) -> Config:
    p = Path(path).resolve()
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    site = _fill(SiteConfig, raw.get("site", {}))
    site.root = p.parent
    cfg = Config(
        site=site,
        model=_fill(ModelConfig, raw.get("model", {})),
        limits=_fill(LimitsConfig, raw.get("limits", {})),
        protocol=_fill(ProtocolConfig, raw.get("protocol", {})),
        server=_fill(ServerConfig, raw.get("server", {})),
        index_dir=p.parent / ".sitewitness",
    )
    if cfg.limits.store.startswith("sqlite:") and not Path(cfg.limits.store[7:]).is_absolute():
        cfg.limits.store = "sqlite:" + str(p.parent / cfg.limits.store[7:])
    return cfg
