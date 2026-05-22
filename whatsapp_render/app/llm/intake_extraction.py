from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.catalog_search import parse_property_types_from_blob, parse_search_criteria
from app.llm.deepseek import chat_completion
from app.search_profile import user_declined_zone_preference

_EXTRACT_MAX_TOKENS = 320


@dataclass(frozen=True)
class ExtractedSearchCriteria:
    property_types: tuple[str, ...]
    min_bedrooms: int
    max_price_usd: int | None
    zone_tokens: tuple[str, ...]
    any_zone: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_types": list(self.property_types),
            "min_bedrooms": self.min_bedrooms,
            "max_price_usd": self.max_price_usd,
            "zone_tokens": list(self.zone_tokens),
            "any_zone": self.any_zone,
            "notes": self.notes,
        }


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _normalize_types(raw: Any, branch: str) -> tuple[str, ...]:
    allowed = {"casa", "departamento", "lote"} if branch == "compra" else {"casa", "departamento"}
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        t = str(item).strip().lower()
        if t in allowed and t not in out:
            out.append(t)
    return tuple(out)


def _criteria_from_dict(data: dict[str, Any], branch: str, fallback_text: str) -> ExtractedSearchCriteria:
    types = _normalize_types(data.get("property_types"), branch)
    if not types:
        types = parse_property_types_from_blob(fallback_text)
        if branch == "alquiler":
            types = tuple(t for t in types if t != "lote")

    min_beds_raw = data.get("min_bedrooms")
    min_bedrooms = 0
    if isinstance(min_beds_raw, (int, float)) and min_beds_raw > 0:
        min_bedrooms = int(min_beds_raw)

    max_price: int | None = None
    mp = data.get("max_price_usd")
    if isinstance(mp, (int, float)) and mp >= 1000:
        max_price = int(mp)

    any_zone = bool(data.get("any_zone")) or user_declined_zone_preference(fallback_text)
    zone_tokens: tuple[str, ...] = ()
    zr = data.get("zone_tokens")
    if isinstance(zr, list):
        zone_tokens = tuple(str(z).strip().lower() for z in zr if str(z).strip())
    if not any_zone and not zone_tokens:
        parsed = parse_search_criteria(fallback_text, branch=branch)
        zone_tokens = parsed.zone_tokens
        any_zone = parsed.any_zone
    if not types:
        pt = parse_search_criteria(fallback_text, branch=branch).property_type
        if pt:
            types = (pt,)

    return ExtractedSearchCriteria(
        property_types=types,
        min_bedrooms=min_bedrooms,
        max_price_usd=max_price if branch == "compra" else None,
        zone_tokens=zone_tokens,
        any_zone=any_zone,
        notes=str(data.get("notes") or "").strip(),
    )


def criteria_from_fallback_text(user_text: str, branch: str) -> ExtractedSearchCriteria:
    parsed = parse_search_criteria(user_text, branch=branch)
    types = parse_property_types_from_blob(user_text)
    if not types and parsed.property_type:
        types = (parsed.property_type,)
    if branch == "alquiler":
        types = tuple(t for t in types if t != "lote")
    return ExtractedSearchCriteria(
        property_types=types,
        min_bedrooms=parsed.min_bedrooms,
        max_price_usd=parsed.max_price_usd if branch == "compra" else None,
        zone_tokens=parsed.zone_tokens,
        any_zone=parsed.any_zone,
    )


def _system_prompt(branch: str) -> str:
    types_hint = "casa, departamento o lote" if branch == "compra" else "casa o departamento"
    return (
        f"Sos un extractor de criterios de búsqueda inmobiliaria ({branch}). "
        "Respondé SOLO con un JSON válido (sin markdown) con estas claves:\n"
        '{"property_types": [], "min_bedrooms": 0, "max_price_usd": null, '
        '"zone_tokens": [], "any_zone": false, "notes": ""}\n\n'
        "Reglas:\n"
        f"- property_types: lista de {types_hint}; vacía si el usuario no especificó tipo.\n"
        "- min_bedrooms: entero mínimo; 0 si no mencionó dormitorios.\n"
        "- max_price_usd: entero USD solo en compra; null si no dijo presupuesto.\n"
        "- zone_tokens: barrios/zonas mencionados; vacío si dijo sin preferencia.\n"
        "- any_zone: true si no tiene zona preferida.\n"
        "- No inventes datos que el usuario no dijo."
    )


async def extract_search_criteria(
    user_text: str,
    *,
    branch: str,
    log_context: dict[str, Any] | None = None,
) -> ExtractedSearchCriteria:
    text = (user_text or "").strip()
    path = (branch or "compra").strip().lower()
    if path not in ("compra", "alquiler"):
        path = "compra"
    if not text:
        return criteria_from_fallback_text("", path)

    ctx = dict(log_context or {})
    ctx["prompt_source"] = "intake_extraction"
    ctx["branch"] = path

    try:
        raw = await chat_completion(
            [
                {"role": "system", "content": _system_prompt(path)},
                {"role": "user", "content": f"Mensaje del cliente:\n{text}"},
            ],
            max_tokens=_EXTRACT_MAX_TOKENS,
            log_context=ctx,
        )
        data = _parse_json_object(raw)
        if data:
            return _criteria_from_dict(data, path, text)
    except RuntimeError:
        pass

    return criteria_from_fallback_text(text, path)
