from __future__ import annotations

import re

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


def user_accepts_waitlist(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    if user_declines_waitlist(body):
        return False
    return bool(_ACCEPT_WAITLIST_RE.search(body))


def user_declines_waitlist(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    return bool(_DECLINE_WAITLIST_RE.search(body))


def user_signals_no_fit(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    return bool(_NO_FIT_RE.search(body))


def qualifies_for_waitlist_registration(current_user_text: str) -> bool:
    """Solo registrar si el mensaje actual acepta explícitamente la lista de espera."""
    return user_accepts_waitlist(current_user_text)
