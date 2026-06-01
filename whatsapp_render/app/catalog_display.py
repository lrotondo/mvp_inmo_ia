from __future__ import annotations

import re
from typing import Literal

from app.catalog_profiles import normalize_catalog_branch
from app.catalog_search import is_consultar_price, parse_price_usd

CountKind = Literal["dormitorio", "ambiente", "habitacion"]

_COUNT_NUM_RE = re.compile(r"\b(\d+)\b")
_COUNT_WORD_RE = re.compile(
    r"\b(un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b",
    re.I,
)
_WORD_TO_INT: dict[str, int] = {
    "un": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}

_LABELS: dict[CountKind, tuple[str, str]] = {
    "dormitorio": ("dormitorio", "dormitorios"),
    "ambiente": ("ambiente", "ambientes"),
    "habitacion": ("habitación", "habitaciones"),
}


def _format_thousands(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


def _extract_count(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = _COUNT_NUM_RE.search(text)
    if match:
        return int(match.group(1))
    word_match = _COUNT_WORD_RE.search(text)
    if word_match:
        return _WORD_TO_INT.get(word_match.group(1).lower())
    return None


def _infer_count_kind(raw: str, default: CountKind) -> CountKind:
    lower = (raw or "").lower()
    if "habitaci" in lower:
        return "habitacion"
    if "dormitorio" in lower or "dorm" in lower:
        return "dormitorio"
    if "ambiente" in lower:
        return "ambiente"
    return default


def format_ficha_count(raw: str, *, kind: CountKind) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    kind = _infer_count_kind(text, kind)
    singular, plural = _LABELS[kind]
    count = _extract_count(text)
    if count is None:
        return text

    noun = singular if count == 1 else plural
    return f"{count} {noun}"


def format_ficha_dormitorios(raw: str) -> str | None:
    return format_ficha_count(raw, kind="dormitorio")


def format_ficha_ambientes(raw: str) -> str | None:
    return format_ficha_count(raw, kind="ambiente")


def _price_mentions_usd(text: str) -> bool:
    upper = text.upper()
    return "USD" in upper or upper.startswith("US$") or upper.startswith("US $")


def _price_mentions_ars(text: str) -> bool:
    lower = text.lower()
    return any(
        token in lower
        for token in ("ars", "peso", "pesos", "$ar", "en pesos")
    )


def format_ficha_precio(raw: str, *, branch: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    is_rent = normalize_catalog_branch(branch) == "alquiler"

    if is_consultar_price({"Precio": text}):
        return "Consultar precio"

    amount = parse_price_usd(text)

    if is_rent:
        if amount is not None and not _price_mentions_usd(text):
            formatted = _format_thousands(amount)
            if text.startswith("$"):
                return f"Precio mensual: {text}"
            return f"Precio mensual: ${formatted}"
        if text.startswith("$"):
            return f"Precio mensual: {text}"
        if amount is not None:
            return f"Precio mensual: ${_format_thousands(amount)}"
        return f"Precio mensual: {text}"

    if amount is not None and (_price_mentions_usd(text) or not _price_mentions_ars(text)):
        return f"Precio: {_format_thousands(amount)} dólares"

    if text.startswith("$") or _price_mentions_usd(text):
        return f"Precio: {text}"
    if amount is not None:
        return f"Precio: {_format_thousands(amount)}"
    return f"Precio: {text}"


def format_row_field_display(key: str, val: str, *, branch: str) -> str | None:
    """Valor formateado para ficha / bloque compacto del LLM."""
    if key == "Precio":
        return format_ficha_precio(val, branch=branch)
    if key == "Dormitorios":
        return format_ficha_dormitorios(val)
    if key == "Ambientes":
        return format_ficha_ambientes(val)
    return val.strip() or None
