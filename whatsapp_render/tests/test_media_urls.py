from __future__ import annotations

from app.catalog import primary_photo_url
from app.media_urls import (
    detail_image_url,
    extract_google_drive_file_id,
    google_drive_direct_image_url,
    is_google_drive_url,
    is_likely_direct_image_url,
    is_social_or_page_url,
    normalize_photo_url,
    preview_link_for_text,
)

_DRIVE_ID = "1Mo8GYB3DLTy6MNx3uaWs4yGuiM6LNwX0"
_DRIVE_LH3 = google_drive_direct_image_url(_DRIVE_ID)


def test_is_social_instagram() -> None:
    assert is_social_or_page_url("https://www.instagram.com/p/ABC123/")
    assert not is_social_or_page_url("https://images.wasi.co/inmuebles/x.jpg")


def test_is_likely_direct_image_jpg() -> None:
    assert is_likely_direct_image_url(
        "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800"
    )
    assert not is_likely_direct_image_url("https://instagram.com/foo")


def test_detail_image_url_prefers_primary_over_instagram_gallery() -> None:
    primary = "https://images.wasi.co/inmuebles/photo.jpg"
    gallery = "https://www.instagram.com/reel/xyz/"
    assert detail_image_url(primary, gallery) == primary


def test_preview_link_for_text_skips_instagram() -> None:
    primary = "https://images.wasi.co/inmuebles/photo.jpg"
    gallery = "https://www.instagram.com/p/abc/"
    assert preview_link_for_text(primary, gallery) == primary


def test_extract_google_drive_file_id_from_view_url() -> None:
    url = f"https://drive.google.com/file/d/{_DRIVE_ID}/view?usp=sharing"
    assert extract_google_drive_file_id(url) == _DRIVE_ID


def test_extract_google_drive_file_id_from_open_url() -> None:
    url = f"https://drive.google.com/open?id={_DRIVE_ID}"
    assert extract_google_drive_file_id(url) == _DRIVE_ID


def test_extract_google_drive_file_id_from_uc_export_view() -> None:
    url = f"https://drive.google.com/uc?export=view&id={_DRIVE_ID}"
    assert extract_google_drive_file_id(url) == _DRIVE_ID


def test_extract_google_drive_file_id_from_googleusercontent() -> None:
    assert extract_google_drive_file_id(_DRIVE_LH3) == _DRIVE_ID


def test_normalize_photo_url_drive_view() -> None:
    view = f"https://drive.google.com/file/d/{_DRIVE_ID}/view?usp=sharing"
    assert normalize_photo_url(view) == _DRIVE_LH3


def test_normalize_photo_url_idempotent_for_googleusercontent() -> None:
    assert normalize_photo_url(_DRIVE_LH3) == _DRIVE_LH3


def test_normalize_photo_url_non_drive_unchanged() -> None:
    wasi = "https://images.wasi.co/inmuebles/x.jpg"
    assert normalize_photo_url(wasi) == wasi


def test_is_google_drive_url() -> None:
    view = f"https://drive.google.com/file/d/{_DRIVE_ID}/view"
    assert is_google_drive_url(view)
    assert is_google_drive_url(_DRIVE_LH3)
    assert not is_google_drive_url("https://images.wasi.co/x.jpg")


def test_is_likely_direct_image_url_accepts_normalized_drive() -> None:
    view = f"https://drive.google.com/file/d/{_DRIVE_ID}/view?usp=sharing"
    assert is_likely_direct_image_url(view)
    assert is_likely_direct_image_url(_DRIVE_LH3)


def test_detail_image_url_normalizes_drive_primary() -> None:
    view = f"https://drive.google.com/file/d/{_DRIVE_ID}/view?usp=sharing"
    assert detail_image_url(view, "") == _DRIVE_LH3


def test_primary_photo_url_normalizes_drive_row() -> None:
    view = f"https://drive.google.com/file/d/{_DRIVE_ID}/view?usp=sharing"
    row = {"foto_principal": view}
    assert primary_photo_url(row) == _DRIVE_LH3
