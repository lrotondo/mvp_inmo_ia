from __future__ import annotations

import re

from app.conversation import HistoryTurn

_ACCEPT_WAITLIST_RE = re.compile(
    r"\b("
    r"s[ií]\s*,?\s*dale|dale|ok|okey|okay|"
    r"avisame|av[ií]same|quiero\s+que\s+me\s+avisen|"
    r"que\s+me\s+avisen|me\s+avisen|"
    r"quiero\s+que\s+me\s+contacten\s+cuando|"
    r"contacten\s+cuando|registrame|registr[aá]me|"
    r"acepto|de\s+acuerdo|perfecto\s*,?\s*si|"
    r"si\s*,?\s*por\s+favor|por\s+favor\s*,?\s*si"
    r")\b",
    re.I,
)

_CONFIRM_SUMMARY_RE = re.compile(
    r"\b("
    r"est[aá]\s+perfecto|est[aá]\s+bien|est[aá]\s+correcto|"
    r"confirmo|lo\s+confirmo|confirmado|correcto|tal\s+cual|"
    r"as[ií]\s+est[aá]|as[ií]\s+queda|genial\s*,?\s*gracias|"
    r"muchas\s+gracias|perfecto\s*,?\s*gracias"
    r")\b",
    re.I,
)

_WAITLIST_BOT_CONTEXT_RE = re.compile(
    r"\b("
    r"lista\s+de\s+espera|confirm[aá]s\s+que|"
    r"te\s+parece\s+bien\s+este\s+resumen|quer[eé]s\s+sumar\s+algo|"
    r"registrad[oa]\s+en\s+nuestra|te\s+escribimos\s+sin\s+falta"
    r")\b",
    re.I,
)

_DECLINE_WAITLIST_RE = re.compile(
    r"\b("
    r"no\s+gracias|no\s*,?\s*gracias|despu[eé]s|ahora\s+no|"
    r"no\s+quiero|prefiero\s+no|dejalo|dej[aá]lo"
    r")\b",
    re.I,
)

_NO_FIT_RE = re.compile(
    r"\b("
    r"ninguna\s+me\s+(?:sirve|convence|cierra|gusta)|"
    r"no\s+me\s+(?:sirve|convence|cierra|gusta)\s+ninguna|"
    r"ninguna\s+opcion|ninguna\s+opci[oó]n|"
    r"no\s+hay\s+nada|nada\s+me\s+convence|"
    r"no\s+encontr[eé]|no\s+tienen\s+nada|"
    r"ninguna\s+de\s+esas|no\s+me\s+sirven"
    r")\b",
    re.I,
)


def user_declines_waitlist(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    return bool(_DECLINE_WAITLIST_RE.search(body))


def user_confirms_summary(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    return bool(_CONFIRM_SUMMARY_RE.search(body))


def user_accepts_waitlist(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    if user_declines_waitlist(body):
        return False
    if bool(_ACCEPT_WAITLIST_RE.search(body)):
        return True
    return user_confirms_summary(body)


def user_signals_no_fit(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    return bool(_NO_FIT_RE.search(body))


def bot_recently_prompted_waitlist_confirm(history: list[HistoryTurn]) -> bool:
    """Último mensaje del bot en historial previo al turno actual."""
    for turn in reversed(history):
        if turn.role != "assistant":
            continue
        return bool(_WAITLIST_BOT_CONTEXT_RE.search(turn.content))
    return False


def qualifies_for_waitlist_registration(current_user_text: str) -> bool:
    """Aceptación explícita o confirmación de resumen (ej. está perfecto)."""
    return user_accepts_waitlist(current_user_text)


def should_register_waitlist(
    has_waitlist_tag: bool,
    current_user_text: str,
    *,
    history: list[HistoryTurn] | None = None,
) -> bool:
    """
    Decide si persistir lista de espera en este turno.
    - Tag [LISTA_ESPERA] + sin rechazo → registrar (LLM cumplió criterio).
    - Sin tag: respaldo si el usuario confirmó y el bot pidió confirmación antes.
    """
    if user_declines_waitlist(current_user_text):
        return False

    if qualifies_for_waitlist_registration(current_user_text):
        if has_waitlist_tag:
            return True
        if history and bot_recently_prompted_waitlist_confirm(history):
            return True
        return False

    if has_waitlist_tag:
        if user_signals_no_fit(current_user_text) and not qualifies_for_waitlist_registration(
            current_user_text
        ):
            return False
        return True

    return False
