from __future__ import annotations

from app.meta_graph import meta_app_id


def is_invalid_waba_id(waba_id: str | None) -> bool:
    """True si vacío o coincide con META_APP_ID (no es un WABA del cliente)."""
    wid = (waba_id or "").strip()
    if not wid:
        return True
    app_id = meta_app_id()
    return bool(app_id and wid == app_id)


def normalize_waba_id(waba_id: str | None) -> str:
    """Devuelve waba_id limpio o vacío si es inválido."""
    if is_invalid_waba_id(waba_id):
        return ""
    return (waba_id or "").strip()
