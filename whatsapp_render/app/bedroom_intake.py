from __future__ import annotations

import re

_WORD_BEDROOMS: dict[str, int] = {
    "un": 1,
    "una": 1,
    "mono": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
}

_BARE_RANGE_RE = re.compile(
    r"\b(\d+)\s*(?:ó|o|or|y|a|-)\s*(\d+)\b",
    re.I,
)
_DIGIT_BEDROOM_RE = re.compile(
    r"\b(\d+)\s*(?:dormitorios?|dorm\.?|ambientes?)\b",
    re.I,
)
_WORD_BEDROOM_RE = re.compile(
    r"\b(un|una|mono|dos|tres|cuatro|cinco|seis)\s+(?:dormitorios?|ambientes?)\b",
    re.I,
)
_PLUS_BED_RE = re.compile(
    r"\b(\d+)\s*\+\s*dorm(?:itorios?)?\b",
    re.I,
)
_MORE_THAN_BED_RE = re.compile(
    r"m[aá]s\s+de\s+(\d+)\s*dorm(?:itorios?)?",
    re.I,
)
_RANGE_WITH_BED_RE = re.compile(
    r"\b(\d+)\s*(?:ó|o|or|y)\s*(\d+)\s*dormitorios?",
    re.I,
)


def bedroom_signal_in_text(text: str) -> bool:
    """True si el mensaje menciona dormitorios/ambientes (con o sin la palabra dormitorios)."""
    blob = (text or "").strip()
    if not blob:
        return False
    if _DIGIT_BEDROOM_RE.search(blob):
        return True
    if _WORD_BEDROOM_RE.search(blob):
        return True
    if _PLUS_BED_RE.search(blob) or _MORE_THAN_BED_RE.search(blob):
        return True
    if _RANGE_WITH_BED_RE.search(blob):
        return True
    if _BARE_RANGE_RE.search(blob):
        return True
    if re.search(r"\bmono\s*amb(?:iente)?\b", blob, re.I):
        return True
    return False


def parse_bedroom_count(text: str) -> int:
    """
    Mínimo de dormitorios inferido del texto.
    Acepta «2 ó 3», «2», rangos con dormitorios y palabras (dos dormitorios).
    """
    blob = (text or "").strip()
    if not blob:
        return 0

    match = _RANGE_WITH_BED_RE.search(blob)
    if match:
        return min(int(match.group(1)), int(match.group(2)))

    match = _BARE_RANGE_RE.search(blob)
    if match:
        return min(int(match.group(1)), int(match.group(2)))

    values: list[int] = []
    for match in _DIGIT_BEDROOM_RE.finditer(blob):
        values.append(int(match.group(1)))
    for match in _PLUS_BED_RE.finditer(blob):
        values.append(int(match.group(1)))
    for match in _MORE_THAN_BED_RE.finditer(blob):
        values.append(int(match.group(1)) + 1)

    for match in _WORD_BEDROOM_RE.finditer(blob):
        word = match.group(1).lower()
        if word in _WORD_BEDROOMS:
            values.append(_WORD_BEDROOMS[word])

    if re.search(r"\bmono\s*amb(?:iente)?\b", blob, re.I):
        values.append(1)

    if not values:
        lone = re.search(r"\b(\d+)\b", blob)
        if lone and bedroom_signal_in_text(blob):
            values.append(int(lone.group(1)))

    return min(values) if values else 0
