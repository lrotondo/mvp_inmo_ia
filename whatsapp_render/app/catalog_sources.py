from __future__ import annotations

import csv
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

CatalogKind = Literal["csv", "google_sheet"]

_SPREADSHEET_URL_RE = re.compile(
    r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
    re.I,
)
_SPREADSHEET_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{20,}$")

# Fila 1 de la planilla / CSV: ID, Direccion, Barrio, Precio, Ambientes,
# Caracteristicas, Link_Fotos, Tour_360

_HEADER_ALIASES: dict[str, str] = {
    "id": "ID",
    "direccion": "Direccion",
    "dirección": "Direccion",
    "barrio": "Barrio",
    "precio": "Precio",
    "ambientes": "Ambientes",
    "caracteristicas": "Caracteristicas",
    "características": "Caracteristicas",
    "link_fotos": "Link_Fotos",
    "link fotos": "Link_Fotos",
    "fotos": "Link_Fotos",
    "tour_360": "Tour_360",
    "tour 360": "Tour_360",
    "tour_360_url": "Tour_360",
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


def fetch_rows_from_google_sheet(ref: CatalogRef) -> list[dict[str, Any]]:
    if not ref.spreadsheet_id:
        logger.warning("Google Sheet sin spreadsheet_id ref=%r", ref.raw)
        return []

    credentials = _load_credentials()
    if credentials is None:
        logger.warning(
            "Sin credenciales Google (GOOGLE_SERVICE_ACCOUNT_JSON); "
            "no se puede leer sheet %s",
            ref.spreadsheet_id,
        )
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
            "catalog_fetch source=google_sheet spreadsheet_id=%s rows=%s",
            ref.spreadsheet_id,
            len(rows),
        )
        return rows
    except Exception:
        logger.exception(
            "Error leyendo Google Sheet spreadsheet_id=%s",
            ref.spreadsheet_id,
        )
        return []


def fetch_rows_from_csv(ref: CatalogRef) -> list[dict[str, Any]]:
    path = resolve_csv_path(ref.csv_path or ref.raw)
    if not path.exists():
        logger.warning("CSV de catalogo no existe: %s", path)
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = {
                _normalize_header(k): (v or "").strip()
                for k, v in row.items()
                if k
            }
            if normalized.get("ID"):
                rows.append(normalized)
    logger.info("catalog_fetch source=csv path=%s rows=%s", path, len(rows))
    return rows


def fetch_rows(ref: CatalogRef) -> list[dict[str, Any]]:
    if ref.kind == "google_sheet":
        return fetch_rows_from_google_sheet(ref)
    return fetch_rows_from_csv(ref)
