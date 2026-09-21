"""Write the static Ask page for a site: the template with the API URL, site name and examples inlined."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from sitewitness.config import Config


def render_page(
    config: Config, api_url: str, examples: list[str], out_dir: Path, extra_css_href: str | None = None
) -> Path:
    tpl = resources.files("sitewitness").joinpath("page/index.html").read_text(encoding="utf-8")
    html = (
        tpl.replace("{{SITE_NAME}}", config.site.name)
        .replace("{{API_JSON}}", json.dumps(api_url.rstrip("/")))
        .replace("{{EXAMPLES_JSON}}", json.dumps(examples, ensure_ascii=False))
        .replace(
            "{{EXTRA_CSS}}", f'<link rel="stylesheet" href="{extra_css_href}">' if extra_css_href else ""
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
