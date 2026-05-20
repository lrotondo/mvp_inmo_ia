from __future__ import annotations

import logging
import os
import re

from app.meta_client import (
    send_whatsapp_cta_url_message,
    send_whatsapp_text_message,
)

logger = logging.getLogger(__name__)

_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
    re.I,
)
_STANDALONE_URL_LINE_RE = re.compile(
    r"^\s*(https?://\S+)\s*$",
    re.M,
)

_CTA_LABEL_SHORT: dict[str, str] = {
    "📸 Ver galería de fotos": "📸 Ver galería",
    "Ver galería de fotos": "Ver galería",
    "📸 Ver fotos": "📸 Ver fotos",
    "🎥 Ver video": "🎥 Ver video",
    "🔄 Tour 360°": "🔄 Tour 360°",
}


def friendly_cta_links_enabled() -> bool:
    raw = os.environ.get("FRIENDLY_CTA_LINKS", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def cta_button_label(markdown_label: str) -> str:
    """Etiqueta del botón (máx. 20 caracteres en WhatsApp)."""
    label = (markdown_label or "").strip() or "Abrir enlace"
    short = _CTA_LABEL_SHORT.get(label, label)
    if len(short) <= 20:
        return short
    return short[:20]


def extract_markdown_links(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Separa texto visible y pares (etiqueta, url) de links markdown."""
    body = text or ""
    links: list[tuple[str, str]] = []
    for match in _MARKDOWN_LINK_RE.finditer(body):
        links.append((match.group(1).strip(), match.group(2).strip()))

    cleaned = _MARKDOWN_LINK_RE.sub("", body)
    cleaned = _STANDALONE_URL_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, links


def history_text_for_delivery(cleaned_body: str, links: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if cleaned_body.strip():
        parts.append(cleaned_body.strip())
    for label, _url in links:
        parts.append(f"{label} (botón enviado)")
    return "\n\n".join(parts) if parts else cleaned_body


async def deliver_text_with_friendly_links(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    message: str,
    graph_version: str | None = None,
) -> str:
    """
    Envía texto sin URLs visibles. Links markdown → botones CTA de WhatsApp.
    Retorna texto para historial (sin URLs crudas).
    """
    body = (message or "").strip() or "No pude generar una respuesta en este momento."

    if not friendly_cta_links_enabled():
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )
        return body

    cleaned, links = extract_markdown_links(body)
    if not links:
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )
        return body

    if cleaned.strip():
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=cleaned,
            graph_version=graph_version,
            preview_url=False,
        )

    for label, url in links:
        try:
            await send_whatsapp_cta_url_message(
                access_token=access_token,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id,
                body=label,
                button_label=cta_button_label(label),
                url=url,
                graph_version=graph_version,
            )
        except Exception:
            logger.exception(
                "CTA fallo label=%r url=%s; fallback texto con link",
                label,
                url[:60],
            )
            fallback = f"{label}\n{url}"
            await send_whatsapp_text_message(
                access_token=access_token,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id,
                message=fallback,
                graph_version=graph_version,
                preview_url=False,
            )

    history = history_text_for_delivery(cleaned, links)
    logger.info("friendly_cta: enviados %s botones", len(links))
    return history or body
