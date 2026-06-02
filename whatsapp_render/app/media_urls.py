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

_DRIVE_FILE_PATH_RE = re.compile(
    r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
    re.I,
)
_DRIVE_OPEN_OR_UC_RE = re.compile(
    r"drive\.google\.com/(?:open|uc)\?[^#]*\bid=([a-zA-Z0-9_-]+)",
    re.I,
)
_GOOGLE_USERCONTENT_DRIVE_RE = re.compile(
    r"googleusercontent\.com/d/([a-zA-Z0-9_-]+)",
    re.I,
)

GOOGLE_DRIVE_DEFAULT_WIDTH = 1920


def extract_google_drive_file_id(url: str) -> str | None:
    """Extrae el file ID de URLs de Google Drive o googleusercontent."""
    u = (url or "").strip()
    if not u:
        return None
    for pattern in (_DRIVE_FILE_PATH_RE, _DRIVE_OPEN_OR_UC_RE, _GOOGLE_USERCONTENT_DRIVE_RE):
        match = pattern.search(u)
        if match:
            return match.group(1)
    return None


def is_google_drive_url(url: str) -> bool:
    """True si la URL apunta a un archivo en Drive (incluye googleusercontent convertido)."""
    u = (url or "").strip().lower()
    if not u.startswith("https://"):
        return False
    if "drive.google.com" in u:
        return extract_google_drive_file_id(u) is not None
    return bool(_GOOGLE_USERCONTENT_DRIVE_RE.search(u))


def google_drive_direct_image_url(file_id: str, width: int = GOOGLE_DRIVE_DEFAULT_WIDTH) -> str:
    """
    URL directa para imagen pública en Drive (sin authuser; Meta descarga sin login).

    Requiere que el archivo esté compartido como «Cualquier persona con el enlace».
    """
    fid = (file_id or "").strip()
    return f"https://lh3.googleusercontent.com/d/{fid}=w{width}"


def normalize_photo_url(url: str, *, width: int = GOOGLE_DRIVE_DEFAULT_WIDTH) -> str:
    """Convierte URLs de Drive a lh3.googleusercontent.com; otras URLs se devuelven trimmeadas."""
    u = (url or "").strip()
    if not u:
        return ""
    file_id = extract_google_drive_file_id(u)
    if file_id:
        return google_drive_direct_image_url(file_id, width=width)
    return u


def is_social_or_page_url(url: str) -> bool:
    """Perfil o página (Instagram, etc.), no archivo de imagen directo."""
    u = (url or "").strip()
    if not u.lower().startswith("https://"):
        return False
    return bool(_SOCIAL_HOST_RE.search(u))


def is_likely_direct_image_url(url: str) -> bool:
    """URL HTTPS que Meta/WhatsApp puede usar como imagen embebida."""
    u = normalize_photo_url(url)
    if not u.lower().startswith("https://"):
        return False
    if is_social_or_page_url(u):
        return False
    if _IMAGE_EXT_RE.search(u):
        return True
    if _KNOWN_IMAGE_HOST_RE.search(u):
        return True
    if _GOOGLE_USERCONTENT_DRIVE_RE.search(u):
        return True
    return False


def detail_image_url(primary: str, gallery: str) -> str:
    """URL para mensaje imagen en detalle: siempre foto principal si es imagen directa."""
    p = normalize_photo_url(primary or "")
    if is_likely_direct_image_url(p):
        return p
    g = normalize_photo_url(gallery or "")
    if is_likely_direct_image_url(g):
        return g
    return ""


def preview_link_for_text(primary: str, gallery: str) -> str:
    """Primer enlace para preview en texto: prioriza imagen directa, no redes sociales."""
    p = normalize_photo_url(primary or "")
    g = normalize_photo_url(gallery or "")
    if is_likely_direct_image_url(p):
        return p
    if is_likely_direct_image_url(g):
        return g
    if p and not is_social_or_page_url(p):
        return p
    return ""
