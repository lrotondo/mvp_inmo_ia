from __future__ import annotations

import re

_SOCIAL_HOST_RE = re.compile(
    r"(?:^|//)(?:www\.)?(?:"
    r"instagram\.com|"
    r"facebook\.com|"
    r"fb\.com|"
    r"fb\.watch|"
    r"tiktok\.com|"
    r"youtube\.com|"
    r"youtu\.be"
    r")(?:/|$)",
    re.I,
)

_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", re.I)

_KNOWN_IMAGE_HOST_RE = re.compile(
    r"(?:^|//)(?:[\w.-]+\.)?(?:"
    r"images\.unsplash\.com|"
    r"images\.wasi\.co|"
    r"cdn\.|"
    r"img\.|"
    r"static\.|"
    r"media\.|"
    r"photos\."
    r")",
    re.I,
)


def is_social_or_page_url(url: str) -> bool:
    """Perfil o página (Instagram, etc.), no archivo de imagen directo."""
    u = (url or "").strip()
    if not u.lower().startswith("https://"):
        return False
    return bool(_SOCIAL_HOST_RE.search(u))


def is_likely_direct_image_url(url: str) -> bool:
    """URL HTTPS que Meta/WhatsApp puede usar como imagen embebida."""
    u = (url or "").strip()
    if not u.lower().startswith("https://"):
        return False
    if is_social_or_page_url(u):
        return False
    if _IMAGE_EXT_RE.search(u):
        return True
    if _KNOWN_IMAGE_HOST_RE.search(u):
        return True
    return False


def detail_image_url(primary: str, gallery: str) -> str:
    """URL para mensaje imagen en detalle: siempre foto principal si es imagen directa."""
    p = (primary or "").strip()
    if is_likely_direct_image_url(p):
        return p
    g = (gallery or "").strip()
    if is_likely_direct_image_url(g):
        return g
    return ""


def preview_link_for_text(primary: str, gallery: str) -> str:
    """Primer enlace para preview en texto: prioriza imagen directa, no redes sociales."""
    p = (primary or "").strip()
    g = (gallery or "").strip()
    if is_likely_direct_image_url(p):
        return p
    if is_likely_direct_image_url(g):
        return g
    if p and not is_social_or_page_url(p):
        return p
    return ""
