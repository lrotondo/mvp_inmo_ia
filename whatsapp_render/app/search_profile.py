from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.catalog_search import (
    _parse_min_bedrooms,
    parse_property_type_from_blob,
    parse_search_criteria,
)
from app.bedroom_intake import bedroom_signal_in_text, parse_bedroom_count
from app.capture_flow import user_messages_for_flow

_NO_DEFINED_ZONE_RE = re.compile(
    r"\b("
    r"no\s+tengo\s+zona|no\s+tengo\s+zonas?|"
    r"no\s+tengo\s+preferencia\s+de\s+zona|no\s+tengo\s+zonas?\s+preferid[ao]s?|"
    r"sin\s+zona\s+definida|sin\s+zonas?\s+preferid[ao]s?|"
    r"no\s+tengo\s+barrio|"
    r"cualquier\s+zona|cualquier\s+barrio|"
    r"sin\s+preferencia\s+de\s+zona|no\s+importa\s+la\s+zona|"
    r"no\s+me\s+importa\s+(?:la\s+)?zona|"
    r"toda\s+la\s+ciudad|en\s+cualquier\s+parte|"
    r"no\s+tengo\s+ubicaci[oó]n\s+definida|sin\s+ubicaci[oó]n\s+definida"
    r")\b",
    re.I,
)

_BEDROOM_SIGNAL_RE = re.compile(
    r"\b("
    r"\d+\s*(?:ó|o|or|y|a|-)\s*\d+\b|"
    r"\d+\s*(?:ó|o|or|y)\s*m[aá]s\s*dormitorios?|"
    r"m[aá]s\s+de\s+\d+\s*dorm(?:itorios?)?|"
    r"\d+\s*\+\s*dorm(?:itorios?)?|"
    r"\d+\s*(?:dormitorios?|dorm\.?|ambientes?)|"
    r"mono\s*amb(?:iente)?|"
    r"(?:un|una|dos|tres|cuatro|cinco|seis)\s+dormitorios?|"
    r"(?:un|una|dos|tres|cuatro)\s+ambientes?"
    r")\b",
    re.I,
)

_BUDGET_USD_RE = re.compile(
    r"(?:"
    r"us\s*\$?\s*[\d.,]+|"
    r"usd\s*[\d.,]+|"
    r"\$\s*[\d.,]+\s*(?:usd|d[oó]lares?)?|"
    r"presupuesto\s*(?:de\s+)?[\d.,]+|"
    r"tengo\s+[\d.,]{4,}|"
    r"[\d]{2,3}[.,]?\d{3}\s*(?:usd|d[oó]lares?)?"
    r")",
    re.I,
)


def user_declined_zone_preference(user_messages_text: str) -> bool:
    return bool(_NO_DEFINED_ZONE_RE.search(user_messages_text))


def user_has_budget_usd(user_messages_text: str) -> bool:
    return bool(_BUDGET_USD_RE.search(user_messages_text))

CatalogBranch = Literal["compra", "alquiler"]
PropertyType = Literal["casa", "departamento"]

_INTAKE_ORDER_COMPRA: tuple[str, ...] = ("tipo", "zona", "dormitorios", "presupuesto")
_INTAKE_ORDER_ALQUILER: tuple[str, ...] = ("tipo", "zona", "dormitorios")

_FIELD_QUESTIONS: dict[str, dict[str, str]] = {
    "tipo": {
        "compra": "¿Buscás *casa* o *departamento*?",
        "alquiler": "¿Preferís *casa* o *departamento*?",
    },
    "zona": {
        "compra": "¿En qué *zona o barrio* te gustaría? (Si no tenés preferencia, decime «sin preferencia de zona».)",
        "alquiler": "¿En qué *zona o barrio* de Tandil te gustaría? (O «sin preferencia de zona».)",
    },
    "dormitorios": {
        "compra": "¿De cuántos *dormitorios o ambientes* como mínimo?",
        "alquiler": "¿Cuántos *dormitorios* necesitás?",
    },
    "presupuesto": {
        "compra": "¿Qué *presupuesto en USD* manejás aproximadamente?",
        "alquiler": "",
    },
}


@dataclass
class SearchProfile:
    branch: CatalogBranch
    property_type: PropertyType | None = None
    min_bedrooms: int = 0
    max_price_usd: int | None = None
    any_zone: bool = False
    zone_tokens: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return len(self.missing_fields) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "property_type": self.property_type,
            "min_bedrooms": self.min_bedrooms,
            "max_price_usd": self.max_price_usd,
            "any_zone": self.any_zone,
            "zone_tokens": list(self.zone_tokens),
            "missing_fields": list(self.missing_fields),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchProfile:
        branch = str(data.get("branch") or "compra").strip().lower()
        if branch not in ("compra", "alquiler"):
            branch = "compra"
        pt = data.get("property_type")
        property_type: PropertyType | None = None
        if pt in ("casa", "departamento"):
            property_type = pt  # type: ignore[assignment]
        zone_raw = data.get("zone_tokens") or []
        if isinstance(zone_raw, str):
            zone_tokens: tuple[str, ...] = (zone_raw,) if zone_raw else ()
        else:
            zone_tokens = tuple(str(z) for z in zone_raw if str(z).strip())
        missing = tuple(str(m) for m in (data.get("missing_fields") or []))
        return cls(
            branch=branch,  # type: ignore[arg-type]
            property_type=property_type,
            min_bedrooms=int(data.get("min_bedrooms") or 0),
            max_price_usd=data.get("max_price_usd"),
            any_zone=bool(data.get("any_zone")),
            zone_tokens=zone_tokens,
            missing_fields=missing,
        )

    def criteria_blob(self) -> str:
        """Texto sintético para reutilizar filtros de catálogo."""
        parts: list[str] = []
        if self.property_type:
            parts.append(self.property_type)
        if self.min_bedrooms:
            parts.append(f"{self.min_bedrooms} dormitorios")
        if self.any_zone:
            parts.append("sin preferencia de zona")
        elif self.zone_tokens:
            parts.append(f"en {self.zone_tokens[0]}")
        if self.branch == "compra" and self.max_price_usd:
            parts.append(f"usd {self.max_price_usd}")
        return " ".join(parts)

    def next_question(self) -> str | None:
        if not self.missing_fields:
            return None
        field_name = self.missing_fields[0]
        return _FIELD_QUESTIONS.get(field_name, {}).get(self.branch)


def build_search_profile(
    capture_data: dict[str, Any] | None,
    current_user_text: str,
    flow_path: str,
) -> SearchProfile:
    branch = (flow_path or "compra").strip().lower()
    if branch not in ("compra", "alquiler"):
        return SearchProfile(branch="compra", missing_fields=_INTAKE_ORDER_COMPRA)

    existing = load_search_profile_from_capture(capture_data or {}, branch=branch)
    blob = user_messages_for_flow(current_user_text, flow_path, capture_data)
    if existing and existing.criteria_blob():
        blob = f"{existing.criteria_blob()} {blob}".strip()
    criteria = parse_search_criteria(blob, branch=branch)

    property_type: PropertyType | None = None
    if criteria.property_type in ("casa", "departamento"):
        property_type = criteria.property_type  # type: ignore[assignment]

    current_only = (current_user_text or "").strip()
    min_beds = (
        criteria.min_bedrooms
        or _parse_min_bedrooms(blob)
        or parse_bedroom_count(current_only)
    )
    any_zone = criteria.any_zone or user_declined_zone_preference(blob)
    has_zone = any_zone or bool(criteria.zone_tokens)
    has_beds = (
        min_beds > 0
        or bool(_BEDROOM_SIGNAL_RE.search(blob))
        or bedroom_signal_in_text(current_only)
    )

    missing: list[str] = []
    order = _INTAKE_ORDER_COMPRA if branch == "compra" else _INTAKE_ORDER_ALQUILER
    for field_name in order:
        if field_name == "tipo" and not property_type:
            missing.append("tipo")
        elif field_name == "zona" and not has_zone:
            missing.append("zona")
        elif field_name == "dormitorios" and not has_beds:
            missing.append("dormitorios")
        elif field_name == "presupuesto" and branch == "compra":
            if not user_has_budget_usd(blob) and criteria.max_price_usd is None:
                missing.append("presupuesto")

    return SearchProfile(
        branch=branch,  # type: ignore[arg-type]
        property_type=property_type,
        min_bedrooms=min_beds if has_beds else 0,
        max_price_usd=criteria.max_price_usd,
        any_zone=any_zone,
        zone_tokens=criteria.zone_tokens,
        missing_fields=tuple(missing),
    )


def merge_search_profile_into_capture(
    capture_data: dict[str, Any],
    profile: SearchProfile,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    merged["search_profile"] = profile.to_dict()
    return merged


def user_search_profile_ready(
    current_user_text: str,
    flow_path: str,
    capture_data: dict[str, Any] | None = None,
) -> bool:
    path = (flow_path or "").strip().lower()
    if path not in ("compra", "alquiler"):
        return True
    return build_search_profile(
        capture_data, current_user_text, flow_path
    ).is_complete


def load_search_profile_from_capture(
    capture_data: dict[str, Any],
    *,
    branch: str,
) -> SearchProfile | None:
    raw = (capture_data or {}).get("search_profile")
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    profile = SearchProfile.from_dict(raw)
    path = (branch or "").strip().lower()
    if profile.branch != path:
        return None
    return profile

