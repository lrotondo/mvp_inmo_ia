from __future__ import annotations

import html
import os
from typing import Dict

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.catalog import filter_properties, format_catalog, load_properties
from app.groq_client import chat_completion
from app.twilio_auth import validate_twilio_signature


app = FastAPI(title="WhatsApp Inmobiliaria MVP")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _public_webhook_url(request: Request) -> str:
    explicit = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/twilio/whatsapp"
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}{request.url.path}"


@app.post("/twilio/whatsapp")
async def twilio_whatsapp(request: Request) -> Response:
    form = await request.form()
    form_dict: Dict[str, str] = {str(k): str(v) for k, v in form.multi_items()}

    signature = request.headers.get("X-Twilio-Signature", "")
    public_url = _public_webhook_url(request)
    if not validate_twilio_signature(public_url, form_dict, signature):
        raise HTTPException(status_code=403, detail="Firma Twilio invalida")

    user_text = form_dict.get("Body", "").strip()
    rows = load_properties()
    hits = filter_properties(user_text, rows)
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
        f"Consulta del cliente: {user_text}\n\n"
        f"Catalogo (hasta 3 opciones):\n{catalog}"
    )

    answer = await chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    safe = html.escape(answer, quote=True)
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe}</Message>"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@app.get("/twilio/whatsapp", response_class=PlainTextResponse)
def twilio_whatsapp_get() -> str:
    return "Use POST (Twilio webhook)."


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "whatsapp_render", "health": "/health"}
