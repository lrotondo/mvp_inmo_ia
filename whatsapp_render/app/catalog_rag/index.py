from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.catalog import load_properties_for_catalog_path
from app.catalog_rag.document import build_document

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-záéíóúñ0-9]+", re.I)
_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "rag"


def _db_path(catalog_path: str, branch: str) -> Path:
    key = hashlib.sha256(f"{catalog_path}|{branch}".encode()).hexdigest()[:16]
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    return _DB_DIR / f"catalog_{key}.sqlite"


def _tokenize(text: str) -> dict[str, float]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return {}
    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    total = float(len(tokens))
    return {t: c / total for t, c in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in a)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def index_catalog(catalog_path: str, branch: str) -> int:
    """Reindexa catálogo en SQLite (TF-IDF liviano por tokens)."""
    path = (catalog_path or "").strip()
    br = (branch or "compra").strip().lower()
    if not path:
        return 0

    rows = load_properties_for_catalog_path(path)
    db_file = _db_path(path, br)
    doc_hash = hashlib.sha256(path.encode()).hexdigest()

    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_docs (
                property_id TEXT PRIMARY KEY,
                branch TEXT NOT NULL,
                document TEXT NOT NULL,
                tokens_json TEXT NOT NULL,
                document_hash TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM catalog_docs WHERE branch = ?", (br,))
        count = 0
        import json

        for row in rows:
            pid = str(row.get("ID", "")).strip()
            if not pid:
                continue
            doc = build_document(row, br)
            vec = _tokenize(doc)
            conn.execute(
                """
                INSERT OR REPLACE INTO catalog_docs
                (property_id, branch, document, tokens_json, document_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pid, br, doc, json.dumps(vec), doc_hash),
            )
            count += 1
        conn.commit()
        logger.info("catalog_rag indexed path=%r branch=%s rows=%s", path, br, count)
        return count
    finally:
        conn.close()


def search_catalog_ids(
    catalog_path: str,
    branch: str,
    query_text: str,
    *,
    k: int = 10,
) -> list[str]:
    """Top-K IDs por similitud coseno de tokens (fallback vacío si sin índice)."""
    path = (catalog_path or "").strip()
    br = (branch or "compra").strip().lower()
    if not path or not (query_text or "").strip():
        return []

    db_file = _db_path(path, br)
    if not db_file.exists():
        index_catalog(path, br)

    import json

    qvec = _tokenize(query_text)
    if not qvec:
        return []

    conn = sqlite3.connect(db_file)
    try:
        rows = conn.execute(
            "SELECT property_id, tokens_json FROM catalog_docs WHERE branch = ?",
            (br,),
        ).fetchall()
        scored: list[tuple[float, str]] = []
        for pid, tokens_json in rows:
            try:
                dvec = json.loads(tokens_json)
            except json.JSONDecodeError:
                continue
            score = _cosine(qvec, dvec)
            if score > 0:
                scored.append((score, str(pid)))
        scored.sort(reverse=True)
        return [pid for _, pid in scored[:k]]
    finally:
        conn.close()
