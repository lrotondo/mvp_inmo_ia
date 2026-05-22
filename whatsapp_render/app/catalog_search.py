from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.catalog_profiles import format_row_compact
from app.lead_context import user_declined_zone_preference

_MAX_LISTING_ITEMS = 3

_PRICE_USD_RE = re.compile(
    r"[\d.,]+",
)

_BEDROOM_ROW_RE = re.compile(
    r"(\d+)\s*(?:dormitorios?|dorm\.?)",
    re.I,
)

_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "casa": ("casa",),
    "departamento": ("departamento", "depto"),
    "duplex": ("duplex", "dúplex"),
    "ph": ("ph",),
    "lote": ("lote", "terreno"),
    "local": ("local",),
}

_USER_TYPE_RE = re.compile(
    r"\b(casa|departamento|depto|duplex|d[uú]plex|ph|lote|terreno|local)\b",
    re.I,
)

_USER_MIN_BEDS_RE = re.compile(
    r"(\d+)\s*(?:ó|o|or|y)\s*m[aá]s\s*dormitorios?|"
    r"m[aá]s\s+de\s+(\d+)\s*dorm|"
    r"(\d+)\s*\+\s*dorm|"
    r"(\d+)\s*dormitorios?",
    re.I,
)

_USER_BUDGET_RE = re.compile(
    r"(?:us\s*\$?\s*|usd\s*|\$\s*)?([\d][\d.,]*)",
    re.I,
)

_ZONE_TOKEN_RE = re.compile(
    r"\b(?:en|zona|barrio)\s+([a-záéíóúñ][a-záéíóúñ\s]{2,})",
    re.I,
)


@dataclass(frozen=True)
class SearchCriteria:
    property_type: str | None
    min_bedrooms: int
    max_price_usd: int | None
    zone_tokens: tuple[str, ...]
    any_zone: bool


def parse_price_usd(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _PRICE_USD_RE.search(text.replace(" ", ""))
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(0))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_bedrooms_from_row(row: dict[str, Any]) -> int | None:
    dorm = str(row.get("Dormitorios", "")).strip()
    if dorm.isdigit():
        return int(dorm)
    blob = f"{row.get('Titulo', '')} {row.get('Direccion', '')}"
    match = _BEDROOM_ROW_RE.search(blob)
    if match:
        return int(match.group(1))
    amb = str(row.get("Ambientes", "")).strip()
    match_amb = re.search(r"(\d+)", amb)
    if match_amb:
        return int(match_amb.group(1))
    return None


def _parse_min_bedrooms(blob: str) -> int:
    match = _USER_MIN_BEDS_RE.search(blob)
    if not match:
        return 0
    for group in match.groups():
        if group and group.isdigit():
            return int(group)
    return 0


def _parse_max_budget_usd(blob: str) -> int | None:
    best: int | None = None
    for match in _USER_BUDGET_RE.finditer(blob):
        raw = match.group(1)
        value = parse_price_usd(raw)
        if value is None or value < 1000:
            continue
        if best is None or value > best:
            best = value
    return best


def _parse_property_type(blob: str) -> str | None:
    match = _USER_TYPE_RE.search(blob)
    if not match:
        return None
    word = match.group(1).lower()
    if word in ("depto", "departamento"):
        return "departamento"
    if word in ("duplex", "dúplex"):
        return "duplex"
    if word in ("lote", "terreno"):
        return "lote"
    return word


def _parse_zone_tokens(blob: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for match in _ZONE_TOKEN_RE.finditer(blob):
        token = match.group(1).strip().lower()
        if len(token) >= 3 and token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def parse_search_criteria(blob: str, *, branch: str) -> SearchCriteria:
    text = (blob or "").strip()
    any_zone = user_declined_zone_preference(text)
    path = (branch or "").strip().lower()
    max_price = _parse_max_budget_usd(text) if path == "compra" else None
    return SearchCriteria(
        property_type=_parse_property_type(text),
        min_bedrooms=_parse_min_bedrooms(text),
        max_price_usd=max_price,
        zone_tokens=() if any_zone else _parse_zone_tokens(text),
        any_zone=any_zone,
    )


def _row_matches_type(row: dict[str, Any], property_type: str | None) -> bool:
    if not property_type:
        return True
    keywords = _TYPE_KEYWORDS.get(property_type, (property_type,))
    tipo = str(row.get("Tipo", "")).lower()
    caract = str(row.get("Caracteristicas", "")).lower()
    titulo = str(row.get("Titulo", "")).lower()
    blob = f"{tipo} {caract} {titulo}"
    return any(kw in blob for kw in keywords)


def _row_matches_zone(row: dict[str, Any], criteria: SearchCriteria) -> bool:
    if criteria.any_zone or not criteria.zone_tokens:
        return True
    ubic = " ".join(
        str(row.get(k, ""))
        for k in ("Zona", "Lugar", "Barrio", "Direccion", "Titulo")
    ).lower()
    return any(token in ubic for token in criteria.zone_tokens)


def _score_row(row: dict[str, Any], criteria: SearchCriteria) -> float:
    score = 0.0
    beds = parse_bedrooms_from_row(row)
    if beds is not None:
        if criteria.min_bedrooms and beds >= criteria.min_bedrooms:
            score += 10.0 + min(beds - criteria.min_bedrooms, 3)
        elif criteria.min_bedrooms:
            score -= 5.0
    price = parse_price_usd(str(row.get("Precio", "")))
    if criteria.max_price_usd and price is not None:
        if price <= criteria.max_price_usd:
            score += 8.0
            score += max(0.0, (criteria.max_price_usd - price) / 50_000.0)
        else:
            score -= 20.0
    if _row_matches_zone(row, criteria):
        score += 3.0
    if _row_matches_type(row, criteria.property_type):
        score += 5.0
    return score


def filter_catalog_rows(
    rows: list[dict[str, Any]],
    criteria: SearchCriteria,
    branch: str,
) -> list[dict[str, Any]]:
    path = (branch or "").strip().lower()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        if not _row_matches_type(row, criteria.property_type):
            continue
        beds = parse_bedrooms_from_row(row)
        if criteria.min_bedrooms and beds is not None and beds < criteria.min_bedrooms:
            continue
        price = parse_price_usd(str(row.get("Precio", "")))
        if path == "compra" and criteria.max_price_usd and price is not None:
            if price > criteria.max_price_usd:
                continue
        if not _row_matches_zone(row, criteria):
            continue
        scored.append((_score_row(row, criteria), row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]


def pick_listing_ids(
    rows: list[dict[str, Any]],
    *,
    max_items: int = _MAX_LISTING_ITEMS,
) -> list[str]:
    ids: list[str] = []
    for row in rows:
        pid = str(row.get("ID", "")).strip()
        if pid and pid not in ids:
            ids.append(pid)
        if len(ids) >= max_items:
            break
    return ids


def build_mandatory_candidates_block(
    rows: list[dict[str, Any]],
    branch: str,
) -> str:
    if not rows:
        return (
            "(No hay propiedades en catálogo que coincidan con el perfil del cliente. "
            "Ofrecé ampliar presupuesto o criterios. Prohibido inventar direcciones, "
            "zonas o precios.)"
        )
    lines = [
        "Usá EXCLUSIVAMENTE estos IDs en [LISTADO:id1,id2,id3]. "
        "Prohibido citar otras propiedades, zonas o precios que no figuren abajo.",
        "",
    ]
    for row in rows:
        lines.append(format_row_compact(row, branch))
    return "\n".join(lines)


def select_listing_candidates(
    rows: list[dict[str, Any]],
    blob: str,
    *,
    branch: str,
    max_items: int = _MAX_LISTING_ITEMS,
) -> tuple[list[str], list[dict[str, Any]]]:
    criteria = parse_search_criteria(blob, branch=branch)
    filtered = filter_catalog_rows(rows, criteria, branch)
    picked_rows = filtered[:max_items]
    return pick_listing_ids(picked_rows, max_items=max_items), picked_rows
