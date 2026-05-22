from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.catalog_search import parse_search_criteria
from app.capture_flow import user_messages_for_flow
from app.listing_context import user_requests_fresh_listing
from app.prompts.templates import build_intake_bundle_question

_INTAKE_ANSWERED_KEY = "intake_answered"
_INTAKE_PROMPT_SENT_KEY = "intake_prompt_sent"
_INTAKE_RAW_TEXT_KEY = "intake_raw_text"
_SEARCH_CRITERIA_LLM_KEY = "search_criteria_llm"

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
PropertyType = Literal["casa", "departamento", "lote"]


def get_intake_answered(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_INTAKE_ANSWERED_KEY))


def get_intake_prompt_sent(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_INTAKE_PROMPT_SENT_KEY))


def get_intake_raw_text(capture_data: dict[str, Any] | None) -> str:
    return str((capture_data or {}).get(_INTAKE_RAW_TEXT_KEY) or "").strip()


def reset_intake_state(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_INTAKE_ANSWERED_KEY] = False
    merged[_INTAKE_PROMPT_SENT_KEY] = False
    merged.pop(_INTAKE_RAW_TEXT_KEY, None)
    merged.pop(_SEARCH_CRITERIA_LLM_KEY, None)
    merged.pop("intake_step", None)
    return merged


def mark_intake_prompt_sent(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_INTAKE_PROMPT_SENT_KEY] = True
    return merged


def mark_intake_answered(
    capture_data: dict[str, Any],
    user_text: str,
    *,
    criteria_llm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_INTAKE_ANSWERED_KEY] = True
    merged[_INTAKE_RAW_TEXT_KEY] = (user_text or "").strip()
    if criteria_llm is not None:
        merged[_SEARCH_CRITERIA_LLM_KEY] = criteria_llm
    return merged


def user_declined_zone_preference(user_messages_text: str) -> bool:
    return bool(_NO_DEFINED_ZONE_RE.search(user_messages_text))


def is_intake_complete(
    capture_data: dict[str, Any] | None,
    *,
    current_user_text: str = "",
) -> bool:
    if user_requests_fresh_listing((current_user_text or "").strip()):
        return True
    return get_intake_answered(capture_data)


@dataclass
class SearchProfile:
    branch: CatalogBranch
    property_type: PropertyType | None = None
    property_types: tuple[str, ...] = ()
    min_bedrooms: int = 0
    max_price_usd: int | None = None
    any_zone: bool = False
    zone_tokens: tuple[str, ...] = ()
    intake_complete: bool = False
    notes: str = ""

    @property
    def is_complete(self) -> bool:
        return self.intake_complete

    @property
    def missing_fields(self) -> tuple[str, ...]:
        if self.intake_complete:
            return ()
        return ("intake_bundle",)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "property_type": self.property_type,
            "property_types": list(self.property_types),
            "min_bedrooms": self.min_bedrooms,
            "max_price_usd": self.max_price_usd,
            "any_zone": self.any_zone,
            "zone_tokens": list(self.zone_tokens),
            "intake_complete": self.intake_complete,
            "missing_fields": list(self.missing_fields),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchProfile:
        branch = str(data.get("branch") or "compra").strip().lower()
        if branch not in ("compra", "alquiler"):
            branch = "compra"
        pt = data.get("property_type")
        property_type: PropertyType | None = None
        if pt in ("casa", "departamento", "lote"):
            property_type = pt  # type: ignore[assignment]
        types_raw = data.get("property_types") or []
        if isinstance(types_raw, str):
            property_types = (types_raw,) if types_raw else ()
        else:
            property_types = tuple(
                str(t).strip().lower()
                for t in types_raw
                if str(t).strip().lower() in ("casa", "departamento", "lote")
            )
        if not property_types and property_type:
            property_types = (property_type,)
        zone_raw = data.get("zone_tokens") or []
        if isinstance(zone_raw, str):
            zone_tokens: tuple[str, ...] = (zone_raw,) if zone_raw else ()
        else:
            zone_tokens = tuple(str(z) for z in zone_raw if str(z).strip())
        intake_complete = bool(data.get("intake_complete"))
        if not intake_complete and not data.get("missing_fields"):
            intake_complete = True
        return cls(
            branch=branch,  # type: ignore[arg-type]
            property_type=property_type,
            property_types=property_types,
            min_bedrooms=int(data.get("min_bedrooms") or 0),
            max_price_usd=data.get("max_price_usd"),
            any_zone=bool(data.get("any_zone")),
            zone_tokens=zone_tokens,
            intake_complete=intake_complete,
            notes=str(data.get("notes") or "").strip(),
        )

    def criteria_blob(self) -> str:
        parts: list[str] = []
        if self.property_types:
            parts.extend(self.property_types)
        elif self.property_type:
            parts.append(self.property_type)
        if self.min_bedrooms:
            parts.append(f"{self.min_bedrooms} dormitorios")
        if self.any_zone:
            parts.append("sin preferencia de zona")
        elif self.zone_tokens:
            parts.append(f"en {self.zone_tokens[0]}")
        if self.branch == "compra" and self.max_price_usd:
            parts.append(f"usd {self.max_price_usd}")
        if self.notes:
            parts.append(self.notes)
        return " ".join(parts)

    def next_question(self) -> str | None:
        if self.intake_complete:
            return None
        return build_intake_bundle_question(self.branch)


def _criteria_from_llm_dict(
    raw: dict[str, Any] | None,
    branch: str,
    fallback_text: str,
) -> SearchProfile:
    branch_norm = branch if branch in ("compra", "alquiler") else "compra"
    if not raw:
        criteria = parse_search_criteria(fallback_text, branch=branch_norm)
        types: tuple[str, ...] = ()
        if criteria.property_type:
            types = (criteria.property_type,)
        if "lote" in fallback_text.lower() or "terreno" in fallback_text.lower():
            types = (*types, "lote") if "lote" not in types else types
        return SearchProfile(
            branch=branch_norm,  # type: ignore[arg-type]
            property_type=types[0] if types else None,  # type: ignore[arg-type]
            property_types=types,
            min_bedrooms=criteria.min_bedrooms,
            max_price_usd=criteria.max_price_usd,
            any_zone=criteria.any_zone,
            zone_tokens=criteria.zone_tokens,
            intake_complete=True,
        )

    types_list = raw.get("property_types") or []
    if not isinstance(types_list, list):
        types_list = []
    property_types = tuple(
        str(t).strip().lower()
        for t in types_list
        if str(t).strip().lower() in ("casa", "departamento", "lote")
    )
    min_beds = raw.get("min_bedrooms")
    min_bedrooms = int(min_beds) if isinstance(min_beds, (int, float)) and min_beds > 0 else 0
    max_price = raw.get("max_price_usd")
    max_price_usd: int | None = None
    if isinstance(max_price, (int, float)) and max_price > 0:
        max_price_usd = int(max_price)
    any_zone = bool(raw.get("any_zone"))
    zone_raw = raw.get("zone_tokens") or []
    zone_tokens: tuple[str, ...] = ()
    if isinstance(zone_raw, list):
        zone_tokens = tuple(str(z).strip().lower() for z in zone_raw if str(z).strip())
    if not any_zone and not zone_tokens:
        any_zone = user_declined_zone_preference(fallback_text)
    if not any_zone and not zone_tokens:
        criteria = parse_search_criteria(fallback_text, branch=branch_norm)
        zone_tokens = criteria.zone_tokens
        any_zone = criteria.any_zone
    property_type: PropertyType | None = None
    if property_types:
        property_type = property_types[0]  # type: ignore[assignment]
    return SearchProfile(
        branch=branch_norm,  # type: ignore[arg-type]
        property_type=property_type,
        property_types=property_types,
        min_bedrooms=min_bedrooms,
        max_price_usd=max_price_usd,
        any_zone=any_zone,
        zone_tokens=zone_tokens,
        intake_complete=True,
        notes=str(raw.get("notes") or "").strip(),
    )


def build_search_profile(
    capture_data: dict[str, Any] | None,
    current_user_text: str,
    flow_path: str,
) -> SearchProfile:
    branch = (flow_path or "compra").strip().lower()
    if branch not in ("compra", "alquiler"):
        return SearchProfile(branch="compra", intake_complete=True)

    intake_done = is_intake_complete(capture_data, current_user_text=current_user_text)
    if not intake_done:
        return SearchProfile(branch=branch, intake_complete=False)  # type: ignore[arg-type]

    raw_llm = (capture_data or {}).get(_SEARCH_CRITERIA_LLM_KEY)
    llm_dict: dict[str, Any] | None = None
    if isinstance(raw_llm, dict):
        llm_dict = raw_llm
    elif isinstance(raw_llm, str):
        try:
            parsed = json.loads(raw_llm)
            if isinstance(parsed, dict):
                llm_dict = parsed
        except json.JSONDecodeError:
            llm_dict = None

    blob = get_intake_raw_text(capture_data) or user_messages_for_flow(
        current_user_text, flow_path, capture_data
    )
    profile = _criteria_from_llm_dict(llm_dict, branch, blob)
    if profile.intake_complete and not profile.any_zone and not profile.zone_tokens:
        profile = SearchProfile(
            branch=profile.branch,
            property_type=profile.property_type,
            property_types=profile.property_types,
            min_bedrooms=profile.min_bedrooms,
            max_price_usd=profile.max_price_usd,
            any_zone=True,
            zone_tokens=profile.zone_tokens,
            intake_complete=True,
            notes=profile.notes,
        )
    return profile


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


# Compat aliases
reset_intake_step = reset_intake_state
bump_intake_step = lambda capture, branch: capture
get_intake_step = lambda capture: 1 if get_intake_answered(capture) else 0
is_intake_script_done = is_intake_complete
intake_field_order = lambda branch: ("intake_bundle",) if branch in ("compra", "alquiler") else ()
