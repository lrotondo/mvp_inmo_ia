from __future__ import annotations

import re
from typing import Literal

from app.catalog import load_properties_for_catalog_path, resolve_rent_catalog_path

LeadType = Literal["venta", "alquiler", "captacion"]

_VISIT_RE = re.compile(
    r"\b(visitar|visita|verla|verlo|ver\s+la|ver\s+el|coordinar\s+visita|agendar)\b",
    re.I,
)


def lead_type_from_flow_path(flow_path: str) -> LeadType:
    path = (flow_path or "").strip().lower()
    if path == "alquiler":
        return "alquiler"
    if path == "captacion":
        return "captacion"
    return "venta"


def catalog_paths_for_flow(
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> list[str]:
    path = (flow_path or "").strip().lower()
    if path == "alquiler":
        rent = resolve_rent_catalog_path(catalog_sale_path, catalog_rent_path)
        return [rent] if rent else []
    if path == "compra":
        sale = (catalog_sale_path or "").strip()
        return [sale] if sale else []
    return []


def extract_property_ref(
    conversation_text: str,
    *,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> str:
    blob = conversation_text.lower()
    best = ""
    best_len = 0

    for csv_path in catalog_paths_for_flow(flow_path, catalog_sale_path, catalog_rent_path):
        for row in load_properties_for_catalog_path(csv_path):
            candidates: list[str] = []
            row_id = str(row.get("ID", "")).strip()
            direccion = str(row.get("Direccion", "")).strip()
            barrio = str(row.get("Barrio", "")).strip()
            if row_id:
                candidates.append(row_id)
                candidates.append(f"ID {row_id}")
            if direccion:
                candidates.append(direccion)
            if barrio and len(barrio) >= 5:
                candidates.append(barrio)

            for cand in candidates:
                key = cand.lower()
                if len(key) < 4 or key not in blob:
                    continue
                if len(key) > best_len:
                    best = cand
                    best_len = len(key)

    return best


def conversation_wants_visit(conversation_text: str) -> bool:
    return bool(_VISIT_RE.search(conversation_text))
