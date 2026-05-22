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
from app.listing_context import user_requests_fresh_listing

_INTAKE_STEP_KEY = "intake_step"

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


def intake_field_order(branch: str) -> tuple[str, ...]:
    path = (branch or "").strip().lower()
    if path == "compra":
        return _INTAKE_ORDER_COMPRA
    if path == "alquiler":
        return _INTAKE_ORDER_ALQUILER
    return ()


def get_intake_step(capture_data: dict[str, Any] | None) -> int:
    try:
        return max(0, int((capture_data or {}).get(_INTAKE_STEP_KEY) or 0))
    except (TypeError, ValueError):
        return 0


def reset_intake_step(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_INTAKE_STEP_KEY] = 0
    return merged


def bump_intake_step(capture_data: dict[str, Any], branch: str) -> dict[str, Any]:
    """Avanza un paso tras cada respuesta del usuario en compra/alquiler."""
    merged = dict(capture_data)
    order = intake_field_order(branch)
    if not order:
        return merged
    step = get_intake_step(merged)
    if step < len(order):
        merged[_INTAKE_STEP_KEY] = step + 1
    return merged


def user_declined_zone_preference(user_messages_text: str) -> bool:
    return bool(_NO_DEFINED_ZONE_RE.search(user_messages_text))


def is_intake_script_done(
    capture_data: dict[str, Any] | None,
    branch: str,
    *,
    current_user_text: str = "",
) -> bool:
    if user_requests_fresh_listing((current_user_text or "").strip()):
        return True
    order = intake_field_order(branch)
    if not order:
        return True
    return get_intake_step(capture_data) >= len(order)


@dataclass
class SearchProfile:
    branch: CatalogBranch
    property_type: PropertyType | None = None
    min_bedrooms: int = 0
    max_price_usd: int | None = None
    any_zone: bool = False
    zone_tokens: tuple[str, ...] = ()
    intake_step: int = 0
    intake_complete: bool = False

    @property
    def is_complete(self) -> bool:
        return self.intake_complete

    @property
    def missing_fields(self) -> tuple[str, ...]:
        """Campos de guía que faltan (solo para compat en tests/logs)."""
        if self.intake_complete:
            return ()
        order = intake_field_order(self.branch)
        step = min(self.intake_step, len(order))
        return order[step:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "property_type": self.property_type,
            "min_bedrooms": self.min_bedrooms,
            "max_price_usd": self.max_price_usd,
            "any_zone": self.any_zone,
            "zone_tokens": list(self.zone_tokens),
            "intake_step": self.intake_step,
            "intake_complete": self.intake_complete,
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
        intake_complete = bool(data.get("intake_complete"))
        if not intake_complete and not data.get("missing_fields"):
            intake_complete = True
        elif data.get("missing_fields") is not None and not intake_complete:
            intake_complete = len(data.get("missing_fields") or []) == 0
        return cls(
            branch=branch,  # type: ignore[arg-type]
            property_type=property_type,
            min_bedrooms=int(data.get("min_bedrooms") or 0),
            max_price_usd=data.get("max_price_usd"),
            any_zone=bool(data.get("any_zone")),
            zone_tokens=zone_tokens,
            intake_step=int(data.get("intake_step") or 0),
            intake_complete=intake_complete,
        )

    def criteria_blob(self) -> str:
        """Texto sintético para filtros de catálogo (recompilado del perfil)."""
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
        if self.intake_complete:
            return None
        order = intake_field_order(self.branch)
        step = min(self.intake_step, len(order) - 1) if order else 0
        if step >= len(order):
            return None
        field_name = order[step]
        return _FIELD_QUESTIONS.get(field_name, {}).get(self.branch)


def build_search_profile(
    capture_data: dict[str, Any] | None,
    current_user_text: str,
    flow_path: str,
) -> SearchProfile:
    branch = (flow_path or "compra").strip().lower()
    if branch not in ("compra", "alquiler"):
        return SearchProfile(branch="compra", intake_complete=True)

    step = get_intake_step(capture_data)
    intake_done = is_intake_script_done(
        capture_data, branch, current_user_text=current_user_text
    )

    blob = user_messages_for_flow(current_user_text, flow_path, capture_data)
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
    if min_beds <= 0 and re.fullmatch(r"\d{1,2}", current_only):
        min_beds = int(current_only)
    if min_beds <= 0:
        for line in reversed(blob.split("\n")):
            stripped = line.strip()
            if re.fullmatch(r"\d{1,2}", stripped):
                min_beds = int(stripped)
                break

    any_zone = criteria.any_zone or user_declined_zone_preference(blob)
    zone_tokens = criteria.zone_tokens
    if intake_done and not any_zone and not zone_tokens:
        any_zone = True

    return SearchProfile(
        branch=branch,  # type: ignore[arg-type]
        property_type=property_type,
        min_bedrooms=min_beds,
        max_price_usd=criteria.max_price_usd,
        any_zone=any_zone,
        zone_tokens=zone_tokens,
        intake_step=step,
        intake_complete=intake_done,
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
