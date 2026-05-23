from __future__ import annotations

import re
from typing import Any

from app.catalog import get_properties_by_ids
from app.catalog_profiles import format_row_compact
from app.property_matching import _normalize_property_match_text

_LAST_LISTING_KEY = "last_listing"
_SHOWN_LISTING_IDS_KEY = "shown_listing_ids"
_FOCUSED_OPTION_INDEX_KEY = "focused_listing_option_index"
_LAST_VIEWED_PROPERTY_KEY = "last_viewed_property"
_MAX_LISTING_ITEMS = 3

# Tokens genéricos en follow-ups (p. ej. "precio de alquiler") que no deben desambiguar filas.
_GENERIC_SCORE_TOKENS = frozenset(
    {
        "alquiler",
        "compra",
        "precio",
        "expensas",
        "garantia",
        "mensual",
        "dormitorios",
        "ambientes",
        "caracteristicas",
        "consultar",
        "opcion",
        "cual",
        "cuál",
        "tiene",
        "tienen",
        "cuanto",
        "cuánto",
        "cuantos",
        "cuántos",
        "hay",
        "incluye",
        "acepta",
        "admite",
        "sale",
        "usd",
        "pesos",
        "mascotas",
        "mascota",
    }
)

_DETAIL_FOLLOWUP_RE = re.compile(
    r"\b("
    r"m[aá]s\s+info|contame\s+m[aá]s|cu[eé]ntame\s+m[aá]s|"
    r"detalles?|ampli[aá]|"
    r"(?:ver|mostr(?:ar|ame))\s+(?:las\s+)?fotos|"
    r"fotos?|videos?|galer[ií]a|recorrido|tour\s*360|ficha"
    r")\b",
    re.I,
)

_BOT_OPTION_CITE_RE = re.compile(
    r"\b(?:la\s+)?opci[oó]n\s*(\d+)\b",
    re.I,
)

_REJECT_ALL_LISTING_RE = re.compile(
    r"\b("
    r"no,?\s*ninguna\b|"
    r"ninguna\s+(?:me\s+)?(?:sirve|convence|cierra|me\s+gusta)|"
    r"ninguna\s+de\s+(?:esas|estas)|"
    r"no\s+me\s+(?:sirve|convence|cierra|gusta)\s+ninguna|"
    r"nada\s+de\s+esto|no\s+cumple|no\s+cumplen|"
    r"no\s+es\s+lo\s+que\s+busco|no\s+encuentro\s+lo\s+que\s+busco|"
    r"no\s+hay\s+nada\s+para\s+m[ií]|"
    r"\btampoco\b|\bninguna\b"
    r")\b",
    re.I,
)
_NEW_SEARCH_STRONG_RE = re.compile(
    r"\b(busquemos|encontremos|empecemos\s+a\s+buscar|quiero\s+buscar)\b",
    re.I,
)
_REQUIREMENTS_HINT_RE = re.compile(
    r"\b("
    r"dormitorio|ambiente|pileta|tenis|zona|barrio|presupuesto|"
    r"usd|metros|m2|mascota|expensa|garage|cochera"
    r")\b",
    re.I,
)

_OPTION_NUMBER_RE = re.compile(
    r"\b(?:opci[oó]n|la\s+opci[oó]n|el\s+de|la\s+de)\s*(?:n[°º]?\s*)?(\d+)\b",
    re.I,
)
_LA_N_RE = re.compile(r"\bla\s+(\d+)\b", re.I)
_ORDINAL_WORD_RE = re.compile(
    r"\b(?:la|el)?\s*(primera|segunda|tercera|cuarta|primer|segundo|tercer|cuarto)\b",
    re.I,
)
_ORDINAL_TO_INDEX: dict[str, int] = {
    "primera": 1,
    "primer": 1,
    "segunda": 2,
    "segundo": 2,
    "tercera": 3,
    "tercer": 3,
    "cuarta": 4,
    "cuarto": 4,
}
_TYPE_HINT_RE = re.compile(
    r"\b(duplex|d[uú]plex|departamento|depto|casa|ph)\b",
    re.I,
)
_LISTADO_TAG_RE = re.compile(r"\[LISTADO:", re.I)
_FRESH_LISTING_RE = re.compile(
    r"\b("
    r"otras?\s+opci[oó]nes|m[aá]s\s+opci[oó]nes|"
    r"mostr[aá](?:me)?\s+(?:de\s+nuevo|otra\s+vez|otras?)|"
    r"ver\s+(?:las\s+)?opci[oó]nes|mostr[aá]me\s+(?:las\s+)?opci[oó]nes|"
    r"dec[ií]me\s+qu[eé]\s+ten[eé]s|qu[eé]\s+ten[eé]s|qu[eé]\s+hay|"
    r"qu[eé]\s+disponible|alguna\s+opci[oó]n"
    r")\b",
    re.I,
)
_NEW_SEARCH_RE = re.compile(
    r"\b("
    r"busquemos|buscar|busco|encontremos|encontrar|"
    r"quiero\s+ver|quiero\s+buscar|mostr(?:ar|ame)|pasame|pas[aá]me"
    r")\b",
    re.I,
)
_NEW_SEARCH_TYPE_RE = re.compile(
    r"\b("
    r"casas?|departamentos?|deptos?|lotes?|terrenos?|duplex|d[uú]plex|ph"
    r")\b",
    re.I,
)
_TYPE_TO_CANONICAL: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:casas?)\b", re.I), "casa"),
    (re.compile(r"\b(?:departamentos?|deptos?|ph)\b", re.I), "departamento"),
    (re.compile(r"\b(?:lotes?|terrenos?)\b", re.I), "lote"),
    (re.compile(r"\b(?:duplex|d[uú]plex)\b", re.I), "departamento"),
)
_LISTING_FOLLOWUP_RE = re.compile(
    r"\b("
    r"tiene|tienen|hay\s+|cu[aá]nto|cu[aá]ntos|cu[aá]l|"
    r"metros?|m2|pileta|cochera|garage|mascotas?|expensas?|"
    r"garant[ií]a|caracter[ií]sticas?|diferencia|comparar|"
    r"acepta|admite|incluye|planta|balc[oó]n|toilette|"
    r"precio|sale|alquiler|usd|pesos|ambientes?|dormitorios?"
    r")\b",
    re.I,
)


def get_shown_listing_ids(capture_data: dict[str, Any] | None) -> list[str]:
    raw = (capture_data or {}).get(_SHOWN_LISTING_IDS_KEY)
    if not isinstance(raw, list):
        return []
    return [str(i).strip() for i in raw if str(i).strip()]


def merge_shown_listing_ids(
    capture_data: dict[str, Any],
    property_ids: list[str],
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    seen = set(get_shown_listing_ids(merged))
    for pid in property_ids:
        p = str(pid).strip()
        if p:
            seen.add(p)
    merged[_SHOWN_LISTING_IDS_KEY] = sorted(seen)
    return merged


def merge_last_listing_into_capture(
    capture_data: dict[str, Any],
    *,
    property_ids: list[str],
    branch: str,
    catalog_path: str | None,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    ids = [str(pid).strip() for pid in property_ids if str(pid).strip()][: _MAX_LISTING_ITEMS]
    if not ids:
        return merged
    merged[_LAST_LISTING_KEY] = {
        "ids": ids,
        "branch": (branch or "").strip().lower(),
        "catalog_path": catalog_path,
    }
    merged = merge_shown_listing_ids(merged, ids)
    return clear_listing_focus_state(merged)


def get_last_viewed_property_id(capture_data: dict[str, Any] | None) -> str:
    raw = (capture_data or {}).get(_LAST_VIEWED_PROPERTY_KEY)
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("id") or "").strip()


def set_last_viewed_property(
    capture_data: dict[str, Any],
    *,
    property_id: str,
    catalog_path: str | None,
    branch: str,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    pid = str(property_id or "").strip()
    if not pid:
        return merged
    merged[_LAST_VIEWED_PROPERTY_KEY] = {
        "id": pid,
        "catalog_path": (catalog_path or "").strip() or None,
        "branch": (branch or "").strip().lower(),
    }
    rows = load_last_listing_rows(catalog_path, merged)
    for idx, row in enumerate(rows, start=1):
        if str(row.get("ID", "")).strip() == pid:
            merged = set_focused_listing_option_index(merged, idx)
            break
    return merged


def clear_last_viewed_property(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data or {})
    merged.pop(_LAST_VIEWED_PROPERTY_KEY, None)
    return merged


def clear_listing_focus_state(capture_data: dict[str, Any]) -> dict[str, Any]:
    """Limpia opción en foco y última ficha vista (listado nuevo / más opciones)."""
    return clear_last_viewed_property(clear_focused_listing_option(capture_data))


def load_last_viewed_property_row(
    capture_data: dict[str, Any] | None,
    *,
    catalog_csv_path: str | None = None,
) -> dict[str, Any] | None:
    raw = (capture_data or {}).get(_LAST_VIEWED_PROPERTY_KEY)
    if not isinstance(raw, dict):
        return None
    pid = str(raw.get("id") or "").strip()
    path = str(raw.get("catalog_path") or "").strip() or catalog_csv_path
    if not pid or not path:
        return None
    rows = get_properties_by_ids(path, [pid], max_items=1)
    if rows:
        return rows[0]
    listing_rows = load_last_listing_rows(catalog_csv_path, capture_data)
    for row in listing_rows:
        if str(row.get("ID", "")).strip() == pid:
            return row
    return None


def get_focused_listing_option_index(
    capture_data: dict[str, Any] | None,
) -> int | None:
    raw = (capture_data or {}).get(_FOCUSED_OPTION_INDEX_KEY)
    if raw is None:
        return None
    try:
        index = int(raw)
    except (TypeError, ValueError):
        return None
    if index < 1:
        return None
    return index


def set_focused_listing_option_index(
    capture_data: dict[str, Any],
    option_index: int,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    if option_index < 1:
        return merged
    merged[_FOCUSED_OPTION_INDEX_KEY] = int(option_index)
    return merged


def clear_focused_listing_option(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data or {})
    merged.pop(_FOCUSED_OPTION_INDEX_KEY, None)
    return merged


def infer_focused_option_index_from_text(
    text: str,
    *,
    max_options: int,
) -> int | None:
    """Índice 1-based si el texto cita 'Opción N' (p. ej. respuesta del bot)."""
    if max_options < 1:
        return None
    indices: list[int] = []
    for match in _BOT_OPTION_CITE_RE.finditer(text or ""):
        try:
            indices.append(int(match.group(1)))
        except ValueError:
            continue
    for index in reversed(indices):
        if 1 <= index <= max_options:
            return index
    return None


def sync_focused_listing_option(
    capture_data: dict[str, Any],
    *,
    user_text: str,
    bot_text: str,
    listing_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Actualiza la opción en foco: elección explícita del usuario o cita en la respuesta del bot.
    Se mantiene entre turnos hasta un listado nuevo o pedido de más opciones.
    """
    merged = dict(capture_data or {})
    n = len(listing_rows)
    if n < 1:
        return clear_focused_listing_option(merged)

    user_index = _listing_index_from_text(user_text)
    if user_index is not None and 1 <= user_index <= n:
        return set_focused_listing_option_index(merged, user_index)

    if user_showed_property_selection(user_text):
        row = _resolve_listing_choice_by_semantic_score(user_text, listing_rows)
        if row is not None:
            for idx, candidate in enumerate(listing_rows, start=1):
                if candidate is row or str(candidate.get("ID")) == str(row.get("ID")):
                    return set_focused_listing_option_index(merged, idx)

    bot_index = infer_focused_option_index_from_text(bot_text, max_options=n)
    if bot_index is not None:
        return set_focused_listing_option_index(merged, bot_index)

    return merged


def load_last_listing_rows(
    catalog_csv_path: str | None,
    capture_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    raw = (capture_data or {}).get(_LAST_LISTING_KEY)
    if not isinstance(raw, dict):
        return []
    ids = raw.get("ids") or []
    if not isinstance(ids, list):
        return []
    path = str(raw.get("catalog_path") or "").strip() or catalog_csv_path
    property_ids = [str(pid).strip() for pid in ids if str(pid).strip()]
    if not property_ids or not path:
        return []
    return get_properties_by_ids(path, property_ids, max_items=_MAX_LISTING_ITEMS)


def _row_search_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("Titulo", "")),
        str(row.get("Tipo", "")),
        str(row.get("Direccion", "")),
        str(row.get("Barrio", "")),
        str(row.get("Caracteristicas", "")),
    ]
    return _normalize_property_match_text(" ".join(parts))


def _score_row_for_choice(user_norm: str, row: dict[str, Any]) -> int:
    blob = _row_search_blob(row)
    if not blob:
        return 0
    score = 0
    for hint in _TYPE_HINT_RE.findall(user_norm):
        key = _normalize_property_match_text(hint)
        if key in ("depto",):
            key = "departamento"
        if key in blob:
            score += 12
    tokens = [
        t
        for t in re.split(r"[^\wáéíóúñ]+", user_norm)
        if len(t) >= 4 and t not in _GENERIC_SCORE_TOKENS
    ]
    for token in tokens:
        if token in blob:
            score += len(token)
    titulo = _normalize_property_match_text(str(row.get("Titulo", "")))
    if titulo and titulo in user_norm:
        score += len(titulo) + 5
    return score


def _listing_index_from_text(text: str) -> int | None:
    """Índice 1-based dentro del último listado (opción 2, la segunda, la 2)."""
    match = _OPTION_NUMBER_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    match = _LA_N_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    match = _ORDINAL_WORD_RE.search(text)
    if match:
        return _ORDINAL_TO_INDEX.get(match.group(1).lower())
    return None


def _resolve_listing_choice_by_semantic_score(
    user_text: str,
    listing_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    text = (user_text or "").strip()
    if not text:
        return None
    user_norm = _normalize_property_match_text(text)
    best: dict[str, Any] | None = None
    best_score = 0
    for row in listing_rows:
        score = _score_row_for_choice(user_norm, row)
        if score > best_score:
            best = row
            best_score = score
    if best_score >= 8:
        return best
    return None


def resolve_listing_choice_row(
    user_text: str,
    listing_rows: list[dict[str, Any]],
    *,
    capture_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Elige una fila solo entre las del último listado enviado."""
    if not listing_rows:
        return None

    text = (user_text or "").strip()
    if not text:
        return None

    index = _listing_index_from_text(text)
    if index is not None and 1 <= index <= len(listing_rows):
        return listing_rows[index - 1]

    row = _resolve_listing_choice_by_semantic_score(text, listing_rows)
    if row is not None:
        return row

    if user_asks_about_shown_listing(text):
        viewed = load_last_viewed_property_row(capture_data)
        if viewed is not None:
            return viewed
        focused = get_focused_listing_option_index(capture_data)
        if focused is not None and 1 <= focused <= len(listing_rows):
            return listing_rows[focused - 1]

    return None


def property_ref_from_listing_choice(
    user_text: str,
    listing_rows: list[dict[str, Any]],
    *,
    capture_data: dict[str, Any] | None = None,
) -> str:
    row = resolve_listing_choice_row(
        user_text,
        listing_rows,
        capture_data=capture_data,
    )
    if row is None:
        return ""
    return str(row.get("ID", "")).strip()


def property_ref_from_listing_option_number(
    user_text: str,
    listing_rows: list[dict[str, Any]],
) -> str:
    index = _listing_index_from_text((user_text or "").strip())
    if index is None or index < 1 or index > len(listing_rows):
        return ""
    return str(listing_rows[index - 1].get("ID", "")).strip()


def listing_already_shown(
    *,
    catalog_csv_path: str | None,
    capture_data: dict[str, Any] | None,
) -> bool:
    raw = (capture_data or {}).get(_LAST_LISTING_KEY)
    if isinstance(raw, dict) and raw.get("ids"):
        return True
    return bool(load_last_listing_rows(catalog_csv_path, capture_data))


_MORE_PHOTOS_RE = re.compile(
    r"\b("
    r"m[aá]s\s+fotos|fotos\s+m[aá]s|m[aá]s\s+im[aá]genes|"
    r"ver\s+(?:las\s+)?fotos|ten[eé]s\s+fotos|tienen\s+fotos"
    r")\b",
    re.I,
)


def user_requests_more_photos(user_text: str) -> bool:
    return bool(_MORE_PHOTOS_RE.search((user_text or "").strip()))


_SELECTION_RE = re.compile(
    r"\b("
    r"me\s+(?:interesa|gusta|cierra|convence|quedo)|"
    r"quiero\s+(?:esa|este|esta|la|el|av\.?|calle)|"
    r"excelente\s+elecci[oó]n|buena\s+elecci[oó]n|"
    r"esa\s+(?:me\s+)?(?:gusta|interesa)"
    r")\b",
    re.I,
)


def user_showed_property_selection(user_text: str) -> bool:
    """Eligió o se decidió por una opción (no solo pregunta sobre ella)."""
    return bool(_SELECTION_RE.search((user_text or "").strip()))


_BROWSE_ONLY_RE = re.compile(
    r"\b("
    r"dec[ií]me\s+qu[eé]\s+ten[eé]s|qu[eé]\s+ten[eé]s|qu[eé]\s+hay|"
    r"ten[eé]s\s+algo|alguna\s+opci[oó]n|ver\s+opci[oó]nes|"
    r"mostr[aá](?:me)?\s+opci[oó]nes|qu[eé]\s+disponible|mostr[aá]me|"
    r"qu[eé]\s+opciones|opciones\s+para\s+comprar|opciones\s+de\s+compra|"
    r"opciones\s+para\s+alquilar|opciones\s+de\s+alquiler|qu[eé]\s+casas|"
    r"qu[eé]\s+departamentos|qu[eé]\s+propiedades"
    r")\b",
    re.I,
)


def current_message_is_browse_only(current_user_text: str) -> bool:
    body = (current_user_text or "").strip()
    if not body:
        return False
    return bool(_BROWSE_ONLY_RE.search(body))


def user_rejects_all_listings(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return bool(_REJECT_ALL_LISTING_RE.search(text))


def property_types_mentioned_in_text(user_text: str) -> set[str]:
    """Tipos de inmueble mencionados en el mensaje (casa, departamento, lote)."""
    text = (user_text or "").strip()
    if not text:
        return set()
    found: set[str] = set()
    for pattern, canonical in _TYPE_TO_CANONICAL:
        if pattern.search(text):
            found.add(canonical)
    return found


def user_requests_new_search(
    user_text: str,
    capture_data: dict[str, Any] | None = None,
) -> bool:
    """
    Nueva búsqueda (ej. busquemos casas en venta): reinicia intake y no reutiliza listado.
    """
    from app.waitlist_flow import get_waitlist_pending

    text = (user_text or "").strip()
    if not text or user_rejects_all_listings(text):
        return False
    if get_waitlist_pending(capture_data):
        return False
    if not _NEW_SEARCH_RE.search(text):
        return False
    if not _NEW_SEARCH_TYPE_RE.search(text):
        return False
    if _NEW_SEARCH_STRONG_RE.search(text):
        return True
    if _REQUIREMENTS_HINT_RE.search(text):
        return False
    return True


def user_wants_alternate_listing(user_text: str) -> bool:
    """Rechazo o pedido de más opciones: re-listado sin reiniciar intake."""
    return user_rejects_all_listings(user_text) or user_requests_more_listing_only(
        user_text
    )


def user_requests_fresh_listing(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    if user_rejects_all_listings(text):
        return False
    if user_requests_new_search(text):
        return True
    if current_message_is_browse_only(text):
        return True
    return bool(_FRESH_LISTING_RE.search(text))


def user_requests_more_listing_only(user_text: str) -> bool:
    """Más opciones sin reiniciar intake (qué tenés, más opciones, etc.)."""
    text = (user_text or "").strip()
    if not text or user_requests_new_search(text):
        return False
    return user_requests_fresh_listing(text)


def user_asks_about_shown_listing(user_text: str) -> bool:
    """Pregunta sobre opciones ya mostradas (características, comparación)."""
    text = (user_text or "").strip()
    if not text or user_requests_fresh_listing(text):
        return False
    has_followup = bool(_LISTING_FOLLOWUP_RE.search(text))
    if not has_followup:
        return False
    if _listing_index_from_text(text) is not None:
        return True
    return has_followup


def user_asks_listing_attribute_followup(user_text: str) -> bool:
    """Follow-up sobre precio/atributos sin pedir ficha, fotos ni otra opción."""
    text = (user_text or "").strip()
    if not user_asks_about_shown_listing(text):
        return False
    if user_requests_more_photos(text) or user_showed_property_selection(text):
        return False
    if _DETAIL_FOLLOWUP_RE.search(text):
        return False
    return True


def build_active_property_context_block(
    row: dict[str, Any],
    *,
    branch: str,
) -> str:
    compact = format_row_compact(row, branch)
    if not compact:
        return ""
    return (
        "### PROPIEDAD EN DETALLE (contexto activo)\n"
        "El cliente ya recibió la ficha de esta propiedad. "
        "Respondé sobre ella si la consulta es ambigua (precio, mascotas, patio, etc.):\n"
        f"{compact}"
    )


def build_listing_catalog_block(
    listing_rows: list[dict[str, Any]],
    *,
    branch: str,
) -> str:
    if not listing_rows:
        return ""
    lines: list[str] = []
    for index, row in enumerate(listing_rows, start=1):
        compact = format_row_compact(row, branch)
        if compact:
            lines.append(f"Opción {index}: {compact}")
    return "\n\n".join(lines)
