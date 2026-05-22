from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from app.catalog_search import (
    parse_property_type_from_blob,
    parse_search_criteria,
)
from app.conversation import HistoryTurn
from app.bedroom_intake import bedroom_signal_in_text, parse_bedroom_count
from app.catalog_search import _parse_min_bedrooms
from app.lead_context import (
    _BEDROOM_SIGNAL_RE,
    user_declined_zone_preference,
    user_has_budget_usd,
    user_messages_for_flow,
)

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
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
) -> SearchProfile:
    branch = (flow_path or "compra").strip().lower()
    if branch not in ("compra", "alquiler"):
        return SearchProfile(branch="compra", missing_fields=_INTAKE_ORDER_COMPRA)

    blob = user_messages_for_flow(history, current_user_text, flow_path)
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

