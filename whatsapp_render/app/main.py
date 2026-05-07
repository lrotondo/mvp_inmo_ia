from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.catalog import filter_properties, format_catalog, load_properties
from app.groq_client import chat_completion
from app.meta_auth import validate_meta_signature, validate_meta_verify_token
from app.meta_client import send_whatsapp_text_message


app = FastAPI(title="WhatsApp Inmobiliaria MVP")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _build_ai_answer(user_text: str) -> tuple[str, str]:
    text = user_text.strip()
    rows = load_properties()
    hits = filter_properties(text, rows)
    catalog = format_catalog(hits)
    if not catalog:
        catalog = (
            "(sin coincidencias con el filtro simple; pedi mas detalles o "
            "propon ampliar criterios.)"
        )

    system_prompt = (
        "Sos un asesor inmobiliario experto en Tandil y zona. "
        "Responde cordial y breve por WhatsApp. "
        "Solo usa datos del catalogo. Si no alcanza, decilo y no inventes."
    )
    user_prompt = (
        f"Consulta del cliente: {text}\n\n"
        f"Catalogo (hasta 3 opciones):\n{catalog}"
    )
    return system_prompt, user_prompt


def _extract_incoming_messages(payload: dict[str, Any]) -> list[tuple[str, str]]:
    incoming: list[tuple[str, str]] = []
    entries = payload.get("entry") or []
    for entry in entries:
        changes = entry.get("changes") or []
        for change in changes:
            value = change.get("value") or {}
            contacts = value.get("contacts") or []
            contact_wa_id = str((contacts[0] or {}).get("wa_id", "")) if contacts else ""
            messages = value.get("messages") or []
            for msg in messages:
                sender = str(msg.get("from") or contact_wa_id).strip()
                msg_type = str(msg.get("type") or "")
                if msg_type != "text":
                    continue
                body = str((msg.get("text") or {}).get("body", "")).strip()
                if sender and body:
                    incoming.append((sender, body))
    return incoming


@app.get("/meta/whatsapp")
def meta_webhook_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    if hub_mode == "subscribe" and validate_meta_verify_token(hub_verify_token or ""):
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Meta verify token invalido")


@app.post("/meta/whatsapp")
async def meta_webhook_post(request: Request) -> dict[str, bool]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not validate_meta_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Firma Meta invalida")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Payload invalido") from exc

    incoming = _extract_incoming_messages(payload)
    for wa_id, user_text in incoming:
        system_prompt, user_prompt = _build_ai_answer(user_text)
        answer = await chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        await send_whatsapp_text_message(to_wa_id=wa_id, message=answer)

    return {"ok": True}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "whatsapp_render", "health": "/health", "webhook": "/meta/whatsapp"}
