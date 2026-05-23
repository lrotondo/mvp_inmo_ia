from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.catalog import is_property_available
from app.catalog_profiles import format_catalog_compact_for_branch
from app.catalog_search import (
    filter_catalog_rows_relaxed,
    listing_filter_from_profile,
    pick_listing_ids,
)
from app.llm.deepseek import chat_completion
from app.search_profile import SearchProfile

_PICK_MAX_TOKENS = 400
_MAX_ITEMS = 3
_MAX_CATALOG_ROWS = 80

PickerMode = Literal["initial", "more_options", "rejected_options"]


@dataclass(frozen=True)
class ListingPickResult:
    ids: list[str]
    rows: list[dict[str, Any]]
    empty_reason: str = ""


def _parse_picker_json(raw: str) -> dict[str, Any] | None:
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


def _valid_ids_from_catalog(
    requested: list[str],
    rows: list[dict[str, Any]],
    *,
    exclude_ids: set[str],
) -> list[str]:
    available_ids = {
        str(r.get("ID", "")).strip()
        for r in rows
        if str(r.get("ID", "")).strip() and is_property_available(r)
    }
    out: list[str] = []
    for pid in requested:
        if pid in exclude_ids:
            continue
        if pid in available_ids and pid not in out:
            out.append(pid)
        if len(out) >= _MAX_ITEMS:
            break
    return out


def _rows_for_ids(rows: list[dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    by_id = {str(r.get("ID", "")).strip(): r for r in rows}
    return [by_id[pid] for pid in ids if pid in by_id]


def _fallback_pick(
    rows: list[dict[str, Any]],
    profile: SearchProfile,
    *,
    branch: str,
    exclude_ids: set[str],
    relaxed: bool = False,
) -> ListingPickResult:
    pool = [
        r
        for r in rows
        if str(r.get("ID", "")).strip() not in exclude_ids and is_property_available(r)
    ]
    if relaxed:
        picked = pool[:_MAX_ITEMS]
        ids = pick_listing_ids(picked, max_items=_MAX_ITEMS)
        reason = "" if ids else "No hay más propiedades en catálogo."
        return ListingPickResult(ids=ids, rows=_rows_for_ids(rows, ids), empty_reason=reason)

    criteria = listing_filter_from_profile(profile)
    filtered = filter_catalog_rows_relaxed(pool, criteria, branch)
    picked = filtered[:_MAX_ITEMS]
    ids = pick_listing_ids(picked, max_items=_MAX_ITEMS)
    if not ids and pool:
        picked = pool[:_MAX_ITEMS]
        ids = pick_listing_ids(picked, max_items=_MAX_ITEMS)
    reason = "" if ids else "Sin coincidencias en catálogo (fallback)."
    return ListingPickResult(ids=ids, rows=_rows_for_ids(rows, ids), empty_reason=reason)


def _system_prompt(branch: str, mode: PickerMode) -> str:
    if mode == "rejected_options":
        mode_line = (
            "El cliente rechazó las opciones mostradas. Elegí otras propiedades "
            "DISTINTAS (IDs no excluidos), aunque encajen menos estricto en criterios."
        )
    elif mode == "more_options":
        mode_line = "El cliente pide MÁS opciones distintas a las ya mostradas."
    else:
        mode_line = "Primera selección según criterios del cliente."
    return (
        f"Sos selector de propiedades ({branch}) para WhatsApp. {mode_line}\n"
        "Respondé SOLO JSON: {\"ids\": [\"id1\", \"id2\"], \"empty_reason\": \"\"}\n"
        "Reglas:\n"
        f"- Máximo {_MAX_ITEMS} IDs del catálogo provisto.\n"
        "- Usá SOLO IDs que aparecen en el catálogo.\n"
        "- Si el cliente no indicó un criterio, incluí propiedades que no lo contradigan.\n"
        "- Si Precio dice «consultar», NO excluyas por presupuesto; incluí la propiedad si encaja en lo demás.\n"
        "- En modo más opciones: NO repitas IDs excluidos.\n"
        "- Si no hay opciones válidas, ids vacío y empty_reason breve en español."
    )


def _user_prompt(
    profile: SearchProfile,
    catalog_block: str,
    *,
    exclude_ids: set[str],
    user_text: str,
) -> str:
    exclude_part = ""
    if exclude_ids:
        exclude_part = f"\nIDs ya mostrados (no repetir): {', '.join(sorted(exclude_ids))}"
    return (
        f"Criterios del cliente:\n{profile.criteria_blob() or '(abiertos)'}\n"
        f"Tipos: {', '.join(profile.property_types) or 'cualquiera'}\n"
        f"Dormitorios mín: {profile.min_bedrooms or 'sin mínimo'}\n"
        f"Presupuesto USD máx: {profile.max_price_usd or 'sin tope'}\n"
        f"Zona: {', '.join(profile.zone_tokens) if profile.zone_tokens else ('cualquiera' if profile.any_zone else 'sin especificar')}"
        f"{exclude_part}\n\n"
        f"Último mensaje del cliente:\n{(user_text or '').strip()}\n\n"
        f"### CATÁLOGO\n{catalog_block}"
    )


def _pre_filter_pool(
    rows: list[dict[str, Any]],
    profile: SearchProfile,
    branch: str,
    exclude_ids: set[str],
    *,
    mode: PickerMode = "initial",
) -> list[dict[str, Any]]:
    pool = [r for r in rows if str(r.get("ID", "")).strip() not in exclude_ids]
    if mode == "rejected_options":
        if len(pool) <= _MAX_CATALOG_ROWS:
            return pool
        return pool[:_MAX_CATALOG_ROWS]
    if len(pool) <= _MAX_CATALOG_ROWS:
        return pool
    criteria = listing_filter_from_profile(profile)
    relaxed = filter_catalog_rows_relaxed(pool, criteria, branch)
    if relaxed:
        return relaxed[:_MAX_CATALOG_ROWS]
    return pool[:_MAX_CATALOG_ROWS]


async def pick_listing_properties(
    rows: list[dict[str, Any]],
    profile: SearchProfile,
    user_text: str,
    *,
    branch: str,
    exclude_ids: list[str] | None = None,
    mode: PickerMode = "initial",
    log_context: dict[str, Any] | None = None,
) -> ListingPickResult:
    path = (branch or "compra").strip().lower()
    exclude = {str(i).strip() for i in (exclude_ids or []) if str(i).strip()}
    pool = _pre_filter_pool(rows, profile, path, exclude, mode=mode)
    if not pool:
        return ListingPickResult(ids=[], rows=[], empty_reason="No hay más propiedades en catálogo.")

    catalog_block = format_catalog_compact_for_branch(pool, path)
    if not catalog_block.strip():
        return _fallback_pick(
            rows,
            profile,
            branch=path,
            exclude_ids=exclude,
            relaxed=mode == "rejected_options",
        )

    ctx = dict(log_context or {})
    ctx["prompt_source"] = "listing_picker"
    ctx["picker_mode"] = mode
    ctx["exclude_ids"] = sorted(exclude)

    try:
        raw = await chat_completion(
            [
                {"role": "system", "content": _system_prompt(path, mode)},
                {
                    "role": "user",
                    "content": _user_prompt(
                        profile, catalog_block, exclude_ids=exclude, user_text=user_text
                    ),
                },
            ],
            max_tokens=_PICK_MAX_TOKENS,
            log_context=ctx,
        )
        data = _parse_picker_json(raw)
        if data:
            raw_ids = data.get("ids") or []
            if isinstance(raw_ids, list):
                requested = [str(i).strip() for i in raw_ids if str(i).strip()]
                ids = _valid_ids_from_catalog(requested, rows, exclude_ids=exclude)
                if ids:
                    return ListingPickResult(
                        ids=ids,
                        rows=_rows_for_ids(rows, ids),
                        empty_reason=str(data.get("empty_reason") or "").strip(),
                    )
            reason = str(data.get("empty_reason") or "").strip()
            if reason:
                fallback = _fallback_pick(
                    rows,
                    profile,
                    branch=path,
                    exclude_ids=exclude,
                    relaxed=mode == "rejected_options",
                )
                if fallback.ids:
                    return fallback
                return ListingPickResult(ids=[], rows=[], empty_reason=reason)
    except RuntimeError:
        pass

    return _fallback_pick(
        rows,
        profile,
        branch=path,
        exclude_ids=exclude,
        relaxed=mode == "rejected_options",
    )
