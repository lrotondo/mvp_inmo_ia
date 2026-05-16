from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from sqlalchemy import select

from app.conversation import HistoryTurn
from app.db import get_engine, session_scope
from app.models import ChatSession

logger = logging.getLogger(__name__)

FlowPath = Literal["nuevo", "compra", "alquiler", "captacion"]
VALID_FLOW_PATHS: frozenset[str] = frozenset({"nuevo", "compra", "alquiler", "captacion"})

_COMPRA_RE = re.compile(
    r"\b(comprar|compra|comprador|invertir|inversi[oó]n|adquirir|venta\s+de)\b",
    re.I,
)
_ALQUILER_RE = re.compile(
    r"\b("
    r"alquilar|alquiler|alquilo|inquilino|renta|rentar|"
    r"en\s+alquiler|para\s+alquilar|de\s+alquiler|alquileres"
    r")\b",
    re.I,
)
_CAPTACION_RE = re.compile(
    r"\b("
    r"vender|vendo|tasar|tasi[oó]n|publicar\s+mi|mi\s+propiedad|"
    r"soy\s+propietario|propietario|captaci[oó]n|quiero\s+vender"
    r")\b",
    re.I,
)
_SWITCH_COMPRA_RE = re.compile(
    r"\b(busco\s+comprar|quiero\s+comprar|opciones\s+de\s+compra)\b",
    re.I,
)
_SWITCH_ALQUILER_RE = re.compile(
    r"\b("
    r"busco\s+alquilar|quiero\s+alquilar|opciones\s+de\s+alquiler|"
    r"necesito\s+alquilar|busco\s+alquiler|departamento\s+en\s+alquiler|"
    r"casa\s+en\s+alquiler|depto\s+en\s+alquiler"
    r")\b",
    re.I,
)
_SWITCH_CAPTACION_RE = re.compile(
    r"\b(quiero\s+vender|tengo\s+.*\s+para\s+vender|vender\s+mi)\b",
    re.I,
)

_memory_lock = Lock()
_memory_sessions: dict[tuple[str, str], dict[str, Any]] = {}


@dataclass
class SessionState:
    flow_path: FlowPath = "nuevo"
    bot_paused: bool = False
    capture_data: dict[str, Any] = field(default_factory=dict)


def _memory_key(phone_number_id: str, wa_id: str) -> tuple[str, str]:
    return phone_number_id.strip(), wa_id.strip()


def _parse_capture_data(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _serialize_capture_data(data: dict[str, Any]) -> str | None:
    if not data:
        return None
    return json.dumps(data, ensure_ascii=False)


def _row_to_state(row: ChatSession) -> SessionState:
    path = str(row.flow_path or "nuevo").strip().lower()
    if path not in VALID_FLOW_PATHS:
        path = "nuevo"
    return SessionState(
        flow_path=path,  # type: ignore[arg-type]
        bot_paused=bool(row.bot_paused),
        capture_data=_parse_capture_data(row.capture_data),
    )


def get_or_create_session(phone_number_id: str, wa_id: str) -> SessionState:
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    if get_engine() is None:
        with _memory_lock:
            raw = _memory_sessions.get(_memory_key(pnid, wid))
            if raw is None:
                state = SessionState()
                _memory_sessions[_memory_key(pnid, wid)] = {
                    "flow_path": state.flow_path,
                    "bot_paused": state.bot_paused,
                    "capture_data": state.capture_data,
                }
                return state
            return SessionState(
                flow_path=raw.get("flow_path", "nuevo"),  # type: ignore[arg-type]
                bot_paused=bool(raw.get("bot_paused")),
                capture_data=dict(raw.get("capture_data") or {}),
            )

    with session_scope() as session:
        stmt = select(ChatSession).where(
            ChatSession.phone_number_id == pnid,
            ChatSession.wa_id == wid,
        )
        row = session.scalars(stmt).first()
        if row is None:
            row = ChatSession(
                phone_number_id=pnid,
                wa_id=wid,
                flow_path="nuevo",
                bot_paused=False,
                capture_data=None,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.flush()
            return SessionState()
        return _row_to_state(row)


def save_session(
    phone_number_id: str,
    wa_id: str,
    *,
    flow_path: FlowPath | None = None,
    bot_paused: bool | None = None,
    capture_data: dict[str, Any] | None = None,
) -> SessionState:
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    current = get_or_create_session(pnid, wid)

    new_path: FlowPath = flow_path if flow_path is not None else current.flow_path
    new_paused = bot_paused if bot_paused is not None else current.bot_paused
    new_capture = capture_data if capture_data is not None else current.capture_data

    if get_engine() is None:
        with _memory_lock:
            _memory_sessions[_memory_key(pnid, wid)] = {
                "flow_path": new_path,
                "bot_paused": new_paused,
                "capture_data": new_capture,
            }
        return SessionState(
            flow_path=new_path,
            bot_paused=new_paused,
            capture_data=dict(new_capture),
        )

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        stmt = select(ChatSession).where(
            ChatSession.phone_number_id == pnid,
            ChatSession.wa_id == wid,
        )
        row = session.scalars(stmt).first()
        if row is None:
            row = ChatSession(
                phone_number_id=pnid,
                wa_id=wid,
                flow_path=new_path,
                bot_paused=new_paused,
                capture_data=_serialize_capture_data(new_capture),
                updated_at=now,
            )
            session.add(row)
        else:
            row.flow_path = new_path
            row.bot_paused = new_paused
            row.capture_data = _serialize_capture_data(new_capture)
            row.updated_at = now

    return SessionState(
        flow_path=new_path,
        bot_paused=new_paused,
        capture_data=dict(new_capture),
    )


def _user_recently_sought_alquiler(history: list[HistoryTurn], max_user_turns: int = 5) -> bool:
    seen = 0
    for turn in reversed(history):
        if turn.role != "user":
            continue
        if _ALQUILER_RE.search(turn.content) or _SWITCH_ALQUILER_RE.search(turn.content):
            return True
        seen += 1
        if seen >= max_user_turns:
            break
    return False


def _detect_flow_from_text(text: str) -> FlowPath | None:
    body = text.strip()
    if not body:
        return None
    if _CAPTACION_RE.search(body):
        return "captacion"
    if _ALQUILER_RE.search(body):
        return "alquiler"
    if _COMPRA_RE.search(body):
        return "compra"
    return None


def resolve_flow_path(
    session: SessionState,
    current_user_text: str,
    history: list[HistoryTurn],
) -> FlowPath:
    current = session.flow_path

    if _SWITCH_CAPTACION_RE.search(current_user_text):
        return "captacion"
    if _SWITCH_ALQUILER_RE.search(current_user_text):
        return "alquiler"
    if _SWITCH_COMPRA_RE.search(current_user_text):
        return "compra"

    detected = _detect_flow_from_text(current_user_text)
    if detected is not None:
        if current == "nuevo" or detected != current:
            logger.info("Flow path detectado: %s -> %s", current, detected)
            return detected

    if current != "nuevo":
        if current == "compra" and _user_recently_sought_alquiler(history):
            logger.info("Flow path: compra -> alquiler (intención alquiler en historial)")
            return "alquiler"
        return current

    for turn in reversed(history):
        if turn.role != "user":
            continue
        hist_detected = _detect_flow_from_text(turn.content)
        if hist_detected is not None:
            logger.info("Flow path desde historial: nuevo -> %s", hist_detected)
            return hist_detected

    return "nuevo"


def merge_capture_from_conversation(
    session: SessionState,
    history: list[HistoryTurn],
    current_user_text: str,
) -> dict[str, Any]:
    """Heurística ligera para enriquecer capture_data en rama captación."""
    if session.flow_path != "captacion":
        return dict(session.capture_data)

    data = dict(session.capture_data)
    blob = " ".join(
        t.content for t in history if t.role == "user"
    ) + " " + current_user_text

    tipo_match = re.search(
        r"\b(casa|departamento|depto|terreno|lote|local|ph|quinta|campo)\b",
        blob,
        re.I,
    )
    if tipo_match and "tipo" not in data:
        data["tipo"] = tipo_match.group(1).capitalize()

    if "barrio" not in data or "ubicacion" not in data:
        zona = re.search(
            r"(?:barrio|zona|ubicad[oa]\s+en)\s+([A-Za-zÁÉÍÓÚáéíóúñ0-9\s]{3,40})",
            blob,
            re.I,
        )
        if zona:
            data["ubicacion"] = zona.group(1).strip()

    amb_match = re.search(r"(\d+)\s*amb(?:ientes)?", blob, re.I)
    m2_match = re.search(r"(\d+)\s*m[²2]", blob, re.I)
    if amb_match and "ambientes" not in data:
        data["ambientes"] = amb_match.group(1)
    if m2_match and "metros" not in data:
        data["metros"] = m2_match.group(1)

    return data


def capture_is_complete(capture_data: dict[str, Any]) -> bool:
    has_tipo = bool(capture_data.get("tipo"))
    has_location = bool(capture_data.get("ubicacion") or capture_data.get("barrio"))
    has_size = bool(
        capture_data.get("ambientes") or capture_data.get("metros")
    )
    return has_tipo and has_location and has_size


def capture_summary_text(capture_data: dict[str, Any]) -> str:
    if not capture_data:
        return ""
    parts = []
    for key in ("tipo", "ubicacion", "barrio", "ambientes", "metros"):
        val = capture_data.get(key)
        if val:
            parts.append(f"{key}: {val}")
    return " | ".join(parts)
