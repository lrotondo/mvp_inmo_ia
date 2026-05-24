from __future__ import annotations

import re

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


def conversation_wants_visit(conversation_text: str) -> bool:
    return bool(_VISIT_RE.search(conversation_text))


def conversation_wants_visit_rent(conversation_text: str) -> bool:
    return bool(_RENT_VISIT_RE.search(conversation_text))


def conversation_requests_human(conversation_text: str) -> bool:
    return bool(_HUMAN_CONTACT_RE.search(conversation_text))
