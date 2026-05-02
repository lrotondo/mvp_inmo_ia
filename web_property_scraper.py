import argparse
import csv
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from html import unescape
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


LISTING_KEYWORDS = [
    "propiedad",
    "inmueble",
    "departamento",
    "dpto",
    "casa",
    "ph",
    "venta",
    "usd",
    "us$",
    "u$s",
]

NOISE_FEATURE_TERMS = [
    "inicio",
    "en venta",
    "en alquiler",
    "tasaciones",
    "nosotros",
    "contacto",
    "facebook",
    "twitter",
    "linkedin",
    "correo electronico",
    "iniciar sesion",
]

NEIGHBORHOOD_HINTS = [
    "barrio",
    "zona",
    "localidad",
    "ciudad",
]


@dataclass
class PropertyRow:
    property_id: str
    address: str
    neighborhood: str
    price: str
    rooms: str
    features: str
    photo_links: str

    def as_csv_row(self) -> Dict[str, str]:
        return {
            "ID": self.property_id,
            "Direccion": self.address,
            "Barrio": self.neighborhood,
            "Precio": self.price,
            "Ambientes": self.rooms,
            "Caracteristicas": self.features,
            "Link_Fotos": self.photo_links,
        }


@dataclass
class PropertyPhotoRow:
    property_id: str
    photo_url: str
    photo_order: int

    def as_csv_row(self) -> Dict[str, str]:
        return {
            "ID": self.property_id,
            "Foto_URL": self.photo_url,
            "Orden_Foto": str(self.photo_order),
        }


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_html(value: str) -> str:
    return normalize_spaces(BeautifulSoup(value or "", "html.parser").get_text(" "))


def same_domain(base_url: str, candidate: str) -> bool:
    base_domain = urlparse(base_url).netloc.lower()
    cand_domain = urlparse(candidate).netloc.lower()
    return cand_domain == "" or cand_domain == base_domain


def is_vivas_domain(url: str) -> bool:
    return "inmobiliariavivastandil.com.ar" in urlparse(url).netloc.lower()


def is_property_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return "/propiedad/" in path


def extract_links(base_url: str, soup: BeautifulSoup) -> List[str]:
    links = []
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, anchor["href"])
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            cleaned = f"{cleaned}?{parsed.query}"
        links.append(cleaned)
    return links


def find_price(text: str) -> str:
    price_regex = re.compile(
        r"(?i)(?:u\$s|us\$|usd|\$)\s*[\d\.\,]+(?:\s*(?:mil|m|k))?"
    )
    match = price_regex.search(text)
    return normalize_spaces(match.group(0)) if match else ""


def find_rooms(text: str) -> str:
    room_regex = re.compile(r"(?i)\b(\d{1,2})\s*(?:amb(?:iente)?s?)\b")
    match = room_regex.search(text)
    return f"{match.group(1)} ambientes" if match else ""


def find_neighborhood(text: str) -> str:
    lines = [normalize_spaces(line) for line in text.split("\n") if line.strip()]
    for line in lines:
        lower_line = line.lower()
        if any(hint in lower_line for hint in NEIGHBORHOOD_HINTS):
            return line
    return ""


def find_location_in_text(text: str) -> str:
    match = re.search(r"(?i)\ben\s+([a-zA-Záéíóúñ\s]+?)(?:\.|,|$)", text)
    if match:
        return normalize_spaces(match.group(1))
    if re.search(r"(?i)\brauch\b", text):
        return "Rauch"
    if re.search(r"(?i)\btandil\b", text):
        return "Tandil"
    return ""


def format_price_value(raw_value: str) -> str:
    value = normalize_spaces(raw_value).replace(",", ".")
    if not value:
        return ""
    try:
        number = float(value)
        return f"{int(round(number)):,}".replace(",", ".")
    except ValueError:
        digits = re.sub(r"[^\d]", "", value)
        return digits


def looks_like_listing(text: str, url: str) -> bool:
    if is_vivas_domain(url):
        return is_property_url(url)

    if is_property_url(url):
        return True
    lower_text = text.lower()
    url_text = url.lower()
    keyword_hits = sum(1 for key in LISTING_KEYWORDS if key in lower_text)
    keyword_hits += sum(1 for key in LISTING_KEYWORDS if key in url_text)
    return keyword_hits >= 2 and bool(find_price(text))


def get_meta_value(meta: Dict[str, List[str]], key: str) -> str:
    values = meta.get(key, [])
    if isinstance(values, list) and values:
        return normalize_spaces(str(values[0]))
    return ""


def collect_feature_terms(item: Dict) -> str:
    embedded = item.get("_embedded", {})
    term_groups = embedded.get("wp:term", [])
    feature_terms: List[str] = []
    for group in term_groups:
        for term in group:
            if term.get("taxonomy") != "property_feature":
                continue
            name = normalize_spaces(unescape(term.get("name", "")))
            if name and name not in feature_terms:
                feature_terms.append(name)
    return " | ".join(feature_terms[:20])


def get_embedded_city(item: Dict) -> str:
    embedded = item.get("_embedded", {})
    term_groups = embedded.get("wp:term", [])
    for group in term_groups:
        for term in group:
            if term.get("taxonomy") == "property_city":
                return normalize_spaces(unescape(term.get("name", "")))
    return ""


def get_embedded_images(item: Dict) -> str:
    image_links: List[str] = []
    embedded = item.get("_embedded", {})
    featured_media = embedded.get("wp:featuredmedia", [])
    for media in featured_media:
        src = media.get("source_url")
        if src and src not in image_links:
            image_links.append(src)

    content_html = item.get("content", {}).get("rendered", "")
    for match in re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)', content_html, re.I):
        if match not in image_links:
            image_links.append(match)
    return " | ".join(image_links[:20])


def fetch_properties_from_wp_api(start_url: str, timeout_seconds: int) -> List[PropertyRow]:
    base = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    endpoint = f"{base}/wp-json/wp/v2/properties"
    first_response = requests.get(
        f"{endpoint}?per_page=100&page=1&_embed=1", timeout=timeout_seconds
    )
    if first_response.status_code != 200:
        return []

    total_pages = int(first_response.headers.get("X-WP-TotalPages", "1"))
    payload_pages = [first_response.json()]
    for page in range(2, total_pages + 1):
        response = requests.get(
            f"{endpoint}?per_page=100&page={page}&_embed=1",
            timeout=timeout_seconds,
        )
        if response.status_code != 200:
            continue
        payload_pages.append(response.json())

    rows: List[PropertyRow] = []
    seen_ids: Set[str] = set()
    for items in payload_pages:
        for item in items:
            meta = item.get("property_meta", {})
            property_id = get_meta_value(meta, "fave_property_id") or f"WP-{item.get('id')}"
            if property_id in seen_ids:
                continue
            seen_ids.add(property_id)

            price_raw = get_meta_value(meta, "fave_property_price")
            currency = get_meta_value(meta, "fave_property_price_postfix") or get_meta_value(
                meta, "fave_currency"
            )
            price_value = format_price_value(price_raw)
            price = f"{currency} {price_value}".strip() if price_value else ""

            rooms_raw = get_meta_value(meta, "fave_property_rooms")
            rooms = f"{rooms_raw} ambientes" if rooms_raw.isdigit() else ""
            title = strip_html(item.get("title", {}).get("rendered", ""))
            neighborhood = get_embedded_city(item) or get_meta_value(meta, "fave_property_map_address")
            address = get_meta_value(meta, "fave_property_address") or title
            features = collect_feature_terms(item)
            if not features:
                features = strip_html(item.get("excerpt", {}).get("rendered", ""))

            rows.append(
                PropertyRow(
                    property_id=property_id,
                    address=address,
                    neighborhood=neighborhood,
                    price=price,
                    rooms=rooms,
                    features=features,
                    photo_links=get_embedded_images(item),
                )
            )

    return rows


def collect_photos(page_url: str, soup: BeautifulSoup) -> str:
    photo_urls = []
    for image in soup.find_all("img", src=True):
        src = urljoin(page_url, image["src"])
        if src not in photo_urls:
            photo_urls.append(src)
    return " | ".join(photo_urls[:20])


def infer_address(soup: BeautifulSoup) -> str:
    selectors = [
        "h1",
        "[class*='address']",
        "[class*='direccion']",
        "[itemprop='streetAddress']",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node and normalize_spaces(node.get_text()):
            return normalize_spaces(node.get_text())
    return ""


def infer_features(soup: BeautifulSoup) -> str:
    selectors = [
        "[class*='feature']",
        "[class*='caracteristica']",
        "[class*='amenit']",
        "ul li",
    ]
    features = []
    for selector in selectors:
        for node in soup.select(selector):
            text = normalize_spaces(node.get_text())
            if not text:
                continue
            if len(text) < 3 or len(text) > 140:
                continue
            normalized = text.lower()
            if any(noise in normalized for noise in NOISE_FEATURE_TERMS):
                continue
            if text.startswith("ID:"):
                continue
            if text not in features:
                features.append(text)
            if len(features) >= 20:
                return " | ".join(features)
    return " | ".join(features)


def get_property_id(page_url: str, soup: BeautifulSoup) -> str:
    body_text = normalize_spaces(soup.get_text(" "))
    id_regexes = [
        re.compile(r"(?i)\b(?:id|codigo|cod\.?|ref(?:erencia)?)\s*[:#-]?\s*([a-z0-9\-_/]+)"),
        re.compile(r"(?i)\b([a-z]{2,5}-\d{3,10})\b"),
    ]
    for pattern in id_regexes:
        found = pattern.search(body_text)
        if found:
            return found.group(1)

    path = urlparse(page_url).path.strip("/").split("/")
    if len(path) >= 2 and path[0] == "propiedad":
        prefix_id = path[1].split("_")[0]
        if prefix_id.isdigit():
            return f"VIV-{prefix_id}"
    if path and path[-1]:
        return path[-1]
    return page_url


def extract_label_value(soup: BeautifulSoup, label: str) -> str:
    pattern = re.compile(rf"(?i)^\s*{re.escape(label)}\s*:")
    for item in soup.select("li, span, p, div"):
        text = normalize_spaces(item.get_text(" ", strip=True))
        if not text:
            continue
        if pattern.search(text):
            value = pattern.sub("", text).strip()
            if value:
                return value
    return ""


def build_property_row(page_url: str, soup: BeautifulSoup) -> PropertyRow:
    page_text = soup.get_text("\n", strip=True)
    rooms = find_rooms(page_text)
    if not rooms:
        rooms_raw = extract_label_value(soup, "Habitaciones") or extract_label_value(
            soup, "Habitacion"
        )
        if rooms_raw.isdigit():
            rooms = f"{rooms_raw} ambientes"

    neighborhood = find_neighborhood(page_text)
    if not neighborhood:
        neighborhood = find_location_in_text(page_text)

    return PropertyRow(
        property_id=get_property_id(page_url, soup),
        address=infer_address(soup),
        neighborhood=neighborhood,
        price=find_price(page_text),
        rooms=rooms,
        features=infer_features(soup),
        photo_links=collect_photos(page_url, soup),
    )


def crawl_properties(
    start_url: str,
    max_pages: int,
    delay_seconds: float,
    timeout_seconds: int,
) -> List[PropertyRow]:
    wp_api_rows = fetch_properties_from_wp_api(start_url, timeout_seconds)
    if wp_api_rows:
        return wp_api_rows

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }
    )

    visited: Set[str] = set()
    queued: Set[str] = set()
    pending = deque([start_url])
    queued.add(start_url)
    rows: List[PropertyRow] = []
    seen_ids: Set[str] = set()

    while pending and len(visited) < max_pages:
        current = pending.popleft()
        if current in visited:
            continue
        visited.add(current)

        try:
            response = session.get(current, timeout=timeout_seconds)
            if response.status_code >= 400:
                continue
        except requests.RequestException:
            continue

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        text = normalize_spaces(soup.get_text(" ", strip=True))
        if looks_like_listing(text, current):
            row = build_property_row(current, soup)
            if row.property_id not in seen_ids and row.price:
                seen_ids.add(row.property_id)
                rows.append(row)

        for link in extract_links(current, soup):
            if link in visited or link in queued:
                continue
            if not same_domain(start_url, link):
                continue
            if is_vivas_domain(start_url):
                link_path = urlparse(link).path.lower()
                if "/propiedad/" in link_path or "/tipo-propiedad/" in link_path:
                    queued.add(link)
                    pending.append(link)
                continue

            queued.add(link)
            pending.append(link)

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return rows


def build_photo_rows(rows: List[PropertyRow]) -> List[PropertyPhotoRow]:
    photo_rows: List[PropertyPhotoRow] = []
    for row in rows:
        if not row.photo_links:
            continue
        links = [normalize_spaces(link) for link in row.photo_links.split("|")]
        clean_links: List[str] = []
        for link in links:
            if not link:
                continue
            if link not in clean_links:
                clean_links.append(link)
        for index, link in enumerate(clean_links, start=1):
            photo_rows.append(
                PropertyPhotoRow(
                    property_id=row.property_id,
                    photo_url=link,
                    photo_order=index,
                )
            )
    return photo_rows


def write_csv(output_file: str, rows: List[PropertyRow]) -> None:
    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ID",
                "Direccion",
                "Barrio",
                "Precio",
                "Ambientes",
                "Caracteristicas",
                "Link_Fotos",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_row())


def write_photos_csv(output_file: str, rows: List[PropertyPhotoRow]) -> None:
    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ID",
                "Foto_URL",
                "Orden_Foto",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_row())


def default_photos_output(properties_output: str) -> str:
    base, ext = os.path.splitext(properties_output)
    final_ext = ext if ext else ".csv"
    return f"{base}_fotos{final_ext}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrapea un sitio inmobiliario y exporta propiedades a CSV."
    )
    parser.add_argument("url", help="URL inicial del sitio a analizar.")
    parser.add_argument(
        "-o",
        "--output",
        default="propiedades.csv",
        help="Ruta de salida del CSV (default: propiedades.csv).",
    )
    parser.add_argument(
        "--photos-output",
        default="",
        help="Ruta de salida del CSV de fotos (default: <output>_fotos.csv).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="Cantidad maxima de paginas a rastrear (default: 200).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Pausa entre requests en segundos (default: 0.2).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Timeout por request en segundos (default: 15).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = crawl_properties(
        start_url=args.url,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        timeout_seconds=args.timeout,
    )
    photo_rows = build_photo_rows(rows)
    photos_output = args.photos_output or default_photos_output(args.output)

    write_csv(args.output, rows)
    write_photos_csv(photos_output, photo_rows)
    print(f"Propiedades detectadas: {len(rows)}")
    print(f"CSV generado en: {args.output}")
    print(f"Fotos detectadas: {len(photo_rows)}")
    print(f"CSV de fotos generado en: {photos_output}")


if __name__ == "__main__":
    main()
