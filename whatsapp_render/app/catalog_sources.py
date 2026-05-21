from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

CatalogKind = Literal["csv", "google_sheet"]

_SPREADSHEET_URL_RE = re.compile(
    r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
    re.I,
)
_SPREADSHEET_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{20,}$")

# Fila 1 de la planilla / CSV: ID, Titulo, Direccion, Barrio, Precio, Dormitorios,
# Ambientes, Caracteristicas, Disponible, foto_principal, Tour_360, url_link_fotos,
# url_link_video

_HEADER_ALIASES: dict[str, str] = {
    "id": "ID",
    "titulo": "Titulo",
    "título": "Titulo",
    "title": "Titulo",
    "direccion": "Direccion",
    "dirección": "Direccion",
    "barrio": "Barrio",
    "precio": "Precio",
    "dormitorios": "Dormitorios",
    "dormitorio": "Dormitorios",
    "bedrooms": "Dormitorios",
    "ambientes": "Ambientes",
    "caracteristicas": "Caracteristicas",
    "características": "Caracteristicas",
    "disponible": "Disponible",
    "foto_principal": "foto_principal",
    "foto principal": "foto_principal",
    "link_fotos": "foto_principal",
    "link fotos": "foto_principal",
    "tour_360": "Tour_360",
    "tour 360": "Tour_360",
    "tour_360_url": "Tour_360",
    "url_link_fotos": "url_link_fotos",
    "link fotos externo": "url_link_fotos",
    "galeria": "url_link_fotos",
    "galería": "url_link_fotos",
    "carrousel": "url_link_fotos",
    "carrusel": "url_link_fotos",
    "url_link_video": "url_link_video",
    "link video": "url_link_video",
    "video": "url_link_video",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CatalogRef:
    kind: CatalogKind
    raw: str
    csv_path: str | None = None
    spreadsheet_id: str | None = None
    gid: str | None = None

    def cache_key(self) -> str:
        if self.kind == "google_sheet" and self.spreadsheet_id:
            gid = self.gid or "0"
            return f"google_sheet:{self.spreadsheet_id}:{gid}"
        if self.csv_path:
            return f"csv:{self.csv_path}"
        return f"unknown:{self.raw}"


def is_google_sheet_ref(value: str | None) -> bool:
    ref = parse_catalog_ref(value)
    return ref is not None and ref.kind == "google_sheet"


def parse_catalog_ref(value: str | None) -> CatalogRef | None:
    raw = (value or "").strip()
    if not raw:
        return None

    url_match = _SPREADSHEET_URL_RE.search(raw)
    if url_match:
        gid_match = re.search(r"[?&#]gid=(\d+)", raw)
        return CatalogRef(
            kind="google_sheet",
            raw=raw,
            spreadsheet_id=url_match.group(1),
            gid=gid_match.group(1) if gid_match else None,
        )

    if _SPREADSHEET_ID_RE.match(raw) and "/" not in raw and not raw.lower().endswith(".csv"):
        return CatalogRef(
            kind="google_sheet",
            raw=raw,
            spreadsheet_id=raw,
        )

    if raw.lower().endswith(".csv") or raw.startswith("data/") or raw.startswith("data\\"):
        return CatalogRef(kind="csv", raw=raw, csv_path=raw)

    path = Path(raw)
    if path.suffix.lower() == ".csv":
        return CatalogRef(kind="csv", raw=raw, csv_path=raw)

    # ID suelto sin extensión csv: tratar como Google Sheet si parece ID
    if _SPREADSHEET_ID_RE.match(raw):
        return CatalogRef(
            kind="google_sheet",
            raw=raw,
            spreadsheet_id=raw,
        )

    return CatalogRef(kind="csv", raw=raw, csv_path=raw)


def resolve_csv_path(catalog_csv_path: str | None) -> Path:
    root = _project_root()
    if not catalog_csv_path or not str(catalog_csv_path).strip():
        return root / "data" / "propiedades_vivas.csv"
    p = Path(str(catalog_csv_path).strip())
    if p.is_absolute():
        return p
    return (root / p).resolve()


def _normalize_header(name: str) -> str:
    key = name.strip().lower()
    return _HEADER_ALIASES.get(key, name.strip())


def rows_from_sheet_values(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values:
        return []
    header_row = values[0]
    headers = [_normalize_header(str(cell)) for cell in header_row]
    rows: list[dict[str, Any]] = []
    for line in values[1:]:
        if not line or all(str(c).strip() == "" for c in line):
            continue
        row_dict: dict[str, Any] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            val = line[idx] if idx < len(line) else ""
            row_dict[header] = str(val).strip() if val is not None else ""
        row_id = str(row_dict.get("ID", "")).strip()
        if row_id:
            rows.append(row_dict)
    return rows


def google_sheet_export_url(ref: CatalogRef) -> str:
    """Export CSV público (planilla compartida: cualquiera con el enlace puede ver)."""
    gid = (ref.gid or "0").strip()
    return (
        f"https://docs.google.com/spreadsheets/d/{ref.spreadsheet_id}/export"
        f"?format=csv&gid={gid}"
    )


def rows_from_csv_text(text: str) -> list[dict[str, Any]]:
    """Parsea CSV (export de Google o archivo) con la misma normalización que archivos locales."""
    if not text or not text.strip():
        return []
    # Google a veces incluye BOM UTF-8
    cleaned = text.lstrip("\ufeff")
    if cleaned.lstrip().lower().startswith("<!doctype") or "<html" in cleaned[:800].lower():
        return []
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(cleaned))
    for row in reader:
        normalized = {
            _normalize_header(k): (v or "").strip()
            for k, v in row.items()
            if k
        }
        if normalized.get("ID"):
            rows.append(normalized)
    return rows


def fetch_rows_from_google_sheet_public(ref: CatalogRef) -> list[dict[str, Any]]:
    """
    Lee planilla vía export CSV sin autenticación.
    Requiere acceso general: cualquiera con el enlace = Lector (o publicada en la web).
    """
    if not ref.spreadsheet_id:
        return []
    url = google_sheet_export_url(ref)
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
        rows = rows_from_csv_text(response.text)
        logger.info(
            "catalog_fetch source=google_sheet_public spreadsheet_id=%s gid=%s rows=%s",
            ref.spreadsheet_id,
            ref.gid or "0",
            len(rows),
        )
        return rows
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Export CSV publico HTTP %s spreadsheet_id=%s (¿enlace con permiso de lectura?)",
            exc.response.status_code,
            ref.spreadsheet_id,
        )
        return []
    except Exception:
        logger.exception(
            "Error export CSV publico spreadsheet_id=%s",
            ref.spreadsheet_id,
        )
        return []


def _load_credentials():
    from google.oauth2 import service_account

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        try:
            info = json.loads(raw_json)
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
        except json.JSONDecodeError as exc:
            logger.error("GOOGLE_SERVICE_ACCOUNT_JSON invalido: %s", exc)
            return None

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if creds_path:
        path = Path(creds_path)
        if path.exists():
            return service_account.Credentials.from_service_account_file(
                str(path),
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
        logger.error("GOOGLE_APPLICATION_CREDENTIALS no existe: %s", creds_path)
    return None


def fetch_rows_from_google_sheet_api(ref: CatalogRef) -> list[dict[str, Any]]:
    """API con cuenta de servicio (opcional; si la planilla se compartió con ese email)."""
    credentials = _load_credentials()
    if credentials is None:
        return []

    try:
        from googleapiclient.discovery import build

        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        range_name = "A:Z"
        if ref.gid and ref.gid != "0":
            meta = (
                service.spreadsheets()
                .get(spreadsheetId=ref.spreadsheet_id, fields="sheets.properties")
                .execute()
            )
            sheet_title = None
            for sheet in meta.get("sheets", []):
                props = sheet.get("properties", {})
                if str(props.get("sheetId", "")) == str(ref.gid):
                    sheet_title = props.get("title")
                    break
            if sheet_title:
                range_name = f"'{sheet_title}'!A:Z"

        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=ref.spreadsheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        rows = rows_from_sheet_values(values)
        logger.info(
            "catalog_fetch source=google_sheet_api spreadsheet_id=%s rows=%s",
            ref.spreadsheet_id,
            len(rows),
        )
        return rows
    except Exception:
        logger.exception(
            "Error leyendo Google Sheet API spreadsheet_id=%s",
            ref.spreadsheet_id,
        )
        return []


def fetch_rows_from_google_sheet(ref: CatalogRef) -> list[dict[str, Any]]:
    if not ref.spreadsheet_id:
        logger.warning("Google Sheet sin spreadsheet_id ref=%r", ref.raw)
        return []

    rows = fetch_rows_from_google_sheet_public(ref)
    if rows:
        return rows

    rows = fetch_rows_from_google_sheet_api(ref)
    if rows:
        return rows

    if _load_credentials() is None:
        logger.warning(
            "Sheet %s sin filas: export publico fallo y no hay "
            "GOOGLE_SERVICE_ACCOUNT_JSON. Verifica que la planilla sea "
            "'Cualquiera con el enlace' como Lector.",
            ref.spreadsheet_id,
        )
    return []


def fetch_rows_from_csv(ref: CatalogRef) -> list[dict[str, Any]]:
    path = resolve_csv_path(ref.csv_path or ref.raw)
    if not path.exists():
        logger.warning("CSV de catalogo no existe: %s", path)
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = rows_from_csv_text(handle.read())
    logger.info("catalog_fetch source=csv path=%s rows=%s", path, len(rows))
    return rows


def fetch_rows(ref: CatalogRef) -> list[dict[str, Any]]:
    if ref.kind == "google_sheet":
        return fetch_rows_from_google_sheet(ref)
    return fetch_rows_from_csv(ref)
