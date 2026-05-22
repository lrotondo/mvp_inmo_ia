from __future__ import annotations

import re

from app.conversation import HistoryTurn

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

_TIME_PREFERENCE_RE = re.compile(
    r"\b("
    r"ma[nñ]ana|tarde|noche|fin\s+de\s+semana|s[aá]bado|domingo|"
    r"preferentemente|prefiero|me\s+queda\s+mejor|"
    r"horario|franja|despu[eé]s\s+del\s+mediod[ií]a|antes\s+del\s+mediod[ií]a"
    r")\b",
    re.I,
)

_BOT_ASKED_TIME_PREFERENCE_RE = re.compile(
    r"\b("
    r"ma[nñ]ana|tarde|fin\s+de\s+semana|preferencia\s+general|"
    r"qu[eé]\s+franja|horario\s+prefer"
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


def conversation_wants_visit(conversation_text: str) -> bool:
    return bool(_VISIT_RE.search(conversation_text))


def conversation_wants_visit_rent(conversation_text: str) -> bool:
    return bool(_RENT_VISIT_RE.search(conversation_text))


def conversation_requests_human(conversation_text: str) -> bool:
    return bool(_HUMAN_CONTACT_RE.search(conversation_text))


def user_gave_visit_time_preference(text: str) -> bool:
    return bool(_TIME_PREFERENCE_RE.search(text.strip()))


def extract_visit_time_preference_label(text: str) -> str:
    body = text.strip().lower()
    if not body:
        return ""
    if re.search(r"\bfin\s+de\s+semana\b|\bs[aá]bado\b|\bdomingo\b", body):
        return "fin de semana"
    if re.search(r"\bma[nñ]ana\b|antes\s+del\s+mediod", body):
        return "mañana"
    if re.search(r"\btarde\b|despu[eé]s\s+del\s+mediod|\bnoche\b", body):
        return "tarde"
    if re.search(r"\bpreferentemente\b|\bprefiero\b", body):
        if re.search(r"\btarde\b", body):
            return "tarde"
        if re.search(r"\bma[nñ]ana\b", body):
            return "mañana"
    return ""


def bot_asked_visit_time_preference(history: list[HistoryTurn]) -> bool:
    for turn in reversed(history):
        if turn.role != "assistant":
            continue
        return bool(_BOT_ASKED_TIME_PREFERENCE_RE.search(turn.content))
    return False


def scoped_rent_visit_intent(
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
) -> bool:
    from app.lead_context import user_messages_for_flow

    scoped = user_messages_for_flow(history, current_user_text, flow_path)
    return bool(scoped.strip()) and conversation_wants_visit_rent(scoped)


def rent_visit_ready_for_alert(
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
) -> bool:
    current = current_user_text.strip()
    if not current:
        return False

    from app.lead_context import user_messages_for_flow

    scoped = user_messages_for_flow(history, current_user_text, flow_path)
    if conversation_requests_human(current) or conversation_requests_human(scoped):
        return True

    has_visit = scoped_rent_visit_intent(history, current_user_text, flow_path)
    pref_current = user_gave_visit_time_preference(current)
    pref_label = extract_visit_time_preference_label(current)

    if has_visit and conversation_wants_visit_rent(current) and pref_current:
        return True

    if pref_label and bot_asked_visit_time_preference(history) and has_visit:
        return True

    return False


def build_rent_visit_lead_notes(
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
) -> str:
    from app.lead_context import user_messages_for_flow

    parts: list[str] = []
    scoped = user_messages_for_flow(history, current_user_text, flow_path)

    pref = extract_visit_time_preference_label(current_user_text)
    if not pref:
        for line in reversed(scoped.split("\n")):
            pref = extract_visit_time_preference_label(line)
            if pref:
                break

    if scoped_rent_visit_intent(history, current_user_text, flow_path):
        if re.search(
            r"\b(dos|ambas|ambos|las\s+dos|los\s+dos)\b",
            scoped,
            re.I,
        ):
            parts.append("Interés en visitar dos opciones del catálogo.")
        else:
            parts.append("Pide coordinar visita a propiedad(es) del catálogo.")

    if pref:
        parts.append(f"Preferencia horaria: {pref}.")

    return " ".join(parts)
