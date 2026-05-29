from __future__ import annotations

import re

# Frases de interés + pedido de ver en persona (tras ficha o listado).
_VIEW_IN_PERSON_RE = (
    r"se\s+puede\s+ver(?!\s+(?:el\s+)?precio|\s+en\s+(?:la\s+)?web)|"
    r"puedo\s+ver(?!\s+(?:el\s+)?precio|\s+en\s+(?:la\s+)?web)|"
    r"podemos\s+ver|podr[ií]a\s+ver|puede\s+verla|puede\s+verlo|"
    r"cu[aá]ndo\s+(?:la\s+)?veo|cu[aá]ndo\s+la\s+podemos\s+ver|"
    r"quiero\s+conocerla|conocerla\s+en\s+persona"
)
_VIEWING_REQUEST_RE = re.compile(
    rf"\b(?:{_VIEW_IN_PERSON_RE}|me\s+gusta.{{0,60}}(?:verla|verlo|visitar|{_VIEW_IN_PERSON_RE}))\b",
    re.I | re.DOTALL,
)

_VISIT_RE = re.compile(
    r"\b("
    r"visitar|visita|verla|verlo|ver\s+la|ver\s+el|coordinar\s+visita|agendar|"
    r"quiero\s+ver|me\s+interesa\s+(?:el|la|esa|ese)|reservar|reserva"
    r")\b",
    re.I,
)

_RENT_VISIT_RE = re.compile(
    r"\b("
    r"visitar|visita|verla|verlo|verlos|verlas|ver\s+la|ver\s+el|ver\s+los|"
    r"coordinar\s+visita|agendar|quiero\s+ver|reservar|reserva|"
    r"cu[aá]ndo\s+podr[ií]a\s+ver|cu[aá]ndo\s+puedo\s+ver|"
    r"poder[ií]a\s+ver|podr[ií]a\s+ver|"
    r"los\s+dos\s+me\s+interesan|las\s+dos\s+me\s+interesan|"
    r"ambas\s+me\s+interesan|ambos\s+me\s+interesan"
    r")\b",
    re.I,
)

_HUMAN_CONTACT_RE = re.compile(
    r"\b("
    r"asesor|humano|persona|hablar\s+con|comunicar|comunicarme|contacto|"
    r"agente|vendedor|llamar|que\s+me\s+contacten|me\s+contacten"
    r")\b",
    re.I,
)

_BARE_ME_INTERESA_RE = re.compile(
    r"^\s*me\s+interesa[\s!.?]*$",
    re.I,
)


def conversation_bare_me_interesa(text: str) -> bool:
    return bool(_BARE_ME_INTERESA_RE.match((text or "").strip()))


def conversation_requests_viewing(conversation_text: str) -> bool:
    """Pedido explícito de ver la propiedad en persona (p. ej. tras la ficha)."""
    return bool(_VIEWING_REQUEST_RE.search(conversation_text))


def conversation_wants_visit(conversation_text: str) -> bool:
    return bool(_VISIT_RE.search(conversation_text))


def conversation_wants_visit_rent(conversation_text: str) -> bool:
    return bool(_RENT_VISIT_RE.search(conversation_text))


def conversation_requests_human(conversation_text: str) -> bool:
    return bool(_HUMAN_CONTACT_RE.search(conversation_text))
