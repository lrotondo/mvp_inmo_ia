from __future__ import annotations

import re

_STREET_AL_RE = re.compile(r"\s+al\s+", re.I)


def _normalize_property_match_text(text: str) -> str:
    t = (text or "").lower().strip()
    t = _STREET_AL_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _property_ref_from_blob_norm(
    blob_norm: str,
    *,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    skip_barrio: bool,
) -> str:
    from app.catalog import field_matches_reference, iter_rows_for_property_matching
    from app.catalog import catalog_paths_for_flow

    best = ""
    best_len = 0
    for csv_path in catalog_paths_for_flow(flow_path, catalog_sale_path, catalog_rent_path):
        for row in iter_rows_for_property_matching(csv_path):
            candidates: list[str] = []
            row_id = str(row.get("ID", "")).strip()
            titulo = str(row.get("Titulo", "")).strip()
            tipo = str(row.get("Tipo", "")).strip()
            direccion = str(row.get("Direccion", "")).strip()
            barrio = str(row.get("Barrio", "")).strip()
            if row_id:
                candidates.append(row_id)
                candidates.append(f"ID {row_id}")
            if titulo:
                candidates.append(titulo)
            if tipo and len(tipo) >= 5:
                candidates.append(tipo)
            if direccion:
                candidates.append(direccion)
            if barrio and len(barrio) >= 5 and not skip_barrio:
                candidates.append(barrio)

            for cand in candidates:
                key = _normalize_property_match_text(cand)
                if len(key) < 4:
                    continue
                if key not in blob_norm and not field_matches_reference(blob_norm, cand):
                    continue
                if len(key) > best_len:
                    best = cand
                    best_len = len(key)
    return best


def extract_property_ref(
    conversation_text: str,
    *,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    current_user_text: str = "",
) -> str:
    from app.catalog_search import user_declined_zone_preference

    current = (current_user_text or "").strip()
    if current:
        blob_norm = _normalize_property_match_text(current.lower())
        skip_barrio = user_declined_zone_preference(blob_norm)
        ref = _property_ref_from_blob_norm(
            blob_norm,
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            skip_barrio=skip_barrio,
        )
        if ref:
            return ref

    blob = (conversation_text or "").lower()
    if not blob.strip():
        return ""

    blob_norm = _normalize_property_match_text(blob)
    skip_barrio = user_declined_zone_preference(blob_norm)
    return _property_ref_from_blob_norm(
        blob_norm,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        skip_barrio=skip_barrio,
    )
