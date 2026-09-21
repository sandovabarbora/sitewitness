"""Texts → passages, data files → schemas, both → an Index with hybrid search."""

from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from glob import glob
from pathlib import Path
from typing import Protocol

from rank_bm25 import BM25Okapi

from sitewitness.config import Config

MIN_WORDS = 8
HTML_BLOCK = re.compile(r"<(p|li|figcaption|dd)\b([^>]*)>(.*?)</\1>", re.S | re.I)
SKIP_CLASSES = ("kicker", "back", "tags")


@dataclass
class Passage:
    id: str
    page: str
    title: str
    text: str


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # extra [embed]

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.encode(texts, normalize_embeddings=True)]


def fold_tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]{2,}", s)


def _clean(fragment: str) -> str:
    fragment = re.sub(r"<sup class=\"cite\">.*?</sup>", "", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def page_of(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    rel = re.sub(r"\.(html?|md)$", "", rel)
    rel = re.sub(r"(^|/)index$", r"\1", rel)
    return "/" + rel


def extract_passages(path: Path, root: Path) -> list[Passage]:
    text = path.read_text(encoding="utf-8", errors="replace")
    page = page_of(path, root)
    out: list[Passage] = []
    if path.suffix.lower() in (".html", ".htm"):
        m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)
        title = _clean(m.group(1)) if m else path.stem
        body = text[text.index("<article") :] if "<article" in text else text
        if '<section class="refs"' in body:
            body = body[: body.index('<section class="refs"')]
        for _tag, attrs, inner in HTML_BLOCK.findall(body):
            if any(c in attrs for c in SKIP_CLASSES):
                continue
            t = _clean(inner)
            if len(t.split()) >= MIN_WORDS:
                out.append(Passage(f"{path.stem}#{len(out)}", page, title, t))
    else:
        m = re.search(r"^#\s+(.+)$", text, re.M)
        title = m.group(1).strip() if m else path.stem
        for block in re.split(r"\n\s*\n", text):
            for line in [block] if not block.lstrip().startswith(("-", "*")) else block.splitlines():
                t = re.sub(r"^\s*[-*]\s+", "", line).strip()
                if t.startswith("#") or len(t.split()) < MIN_WORDS:
                    continue
                t = re.sub(r"\s+", " ", t)
                out.append(Passage(f"{path.stem}#{len(out)}", page, title, t))
    return out


def describe_json(obj, depth: int = 5):
    """Types per key to `depth` levels; below that, only the size. Arrays: length, first item's keys,
    numeric range for leaf numeric arrays."""
    if isinstance(obj, dict):
        if depth == 0:
            return {"object": len(obj), "keys": list(obj)[:20]}
        return {k: describe_json(v, depth - 1) for k, v in obj.items()}
    if isinstance(obj, list):
        d = {"array": len(obj)}
        if obj and isinstance(obj[0], dict):
            d["item_keys"] = list(obj[0].keys())[:20]
        elif obj and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in obj):
            d["min"], d["max"] = min(obj), max(obj)
        return d
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, int):
        return "int"
    if isinstance(obj, float):
        return "float"
    if obj is None:
        return "null"
    return "str"


def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    score: dict[str, float] = {}
    for r in rankings:
        for i, pid in enumerate(r):
            score[pid] = score.get(pid, 0.0) + 1.0 / (k + i + 1)
    return sorted(score, key=lambda p: -score[p])


class Index:
    def __init__(
        self,
        passages: list[Passage],
        sources: dict[str, dict],
        embeddings: dict[str, list[float]] | None = None,
    ):
        self.passages = passages
        self.sources = sources
        self.embeddings = embeddings or {}
        self._by_id = {p.id: p for p in passages}
        self._bm25 = BM25Okapi([fold_tokens(p.title + " " + p.text) for p in passages]) if passages else None

    @property
    def pages(self) -> set[str]:
        return {p.page for p in self.passages}

    def get(self, passage_id: str) -> Passage | None:
        return self._by_id.get(passage_id)

    def search(self, query: str, k: int = 6, embedder: Embedder | None = None) -> list[Passage]:
        if not self.passages:
            return []
        scores = self._bm25.get_scores(fold_tokens(query))
        bm = [
            self.passages[i].id for i in sorted(range(len(scores)), key=lambda i: -scores[i]) if scores[i] > 0
        ][: k * 3]
        rankings = [bm]
        if self.embeddings and embedder is not None:
            q = embedder.embed([query])[0]

            def cos(a, b):
                na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
                return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0

            em = sorted(self.embeddings, key=lambda pid: -cos(q, self.embeddings[pid]))[: k * 3]
            rankings.append(em)
        order = rrf(rankings) if len(rankings) > 1 else bm
        return [self._by_id[pid] for pid in order[:k] if pid in self._by_id]

    def save(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        (index_dir / "index.json").write_text(
            json.dumps(
                {"passages": [asdict(p) for p in self.passages], "sources": self.sources}, ensure_ascii=False
            )
        )
        if self.embeddings:
            (index_dir / "embeddings.json").write_text(json.dumps(self.embeddings))

    @classmethod
    def load(cls, index_dir: Path) -> Index:
        d = json.loads((index_dir / "index.json").read_text())
        emb_p = index_dir / "embeddings.json"
        emb = json.loads(emb_p.read_text()) if emb_p.exists() else None
        return cls([Passage(**p) for p in d["passages"]], d["sources"], emb)


def build_index(config: Config, embedder: Embedder | None = None) -> Index:
    root = config.site.root
    files: list[Path] = []
    for pattern in config.site.texts:
        files += [Path(f) for f in sorted(glob(str(root / pattern), recursive=True))]
    passages: list[Passage] = []
    for f in files:
        passages += extract_passages(f, root)
    sources = {}
    for rel, desc in config.site.data.items():
        p = root / rel
        schema = describe_json(json.loads(p.read_text())) if p.exists() else {"error": "file not found"}
        sources[rel] = {"description": desc, "schema": schema}
    embeddings = None
    if embedder is not None and passages:
        vecs = embedder.embed([p.title + ". " + p.text for p in passages])
        embeddings = {p.id: v for p, v in zip(passages, vecs, strict=True)}
    idx = Index(passages, sources, embeddings)
    idx.save(config.index_dir)
    return idx
