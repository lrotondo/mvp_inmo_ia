from __future__ import annotations

from app.media_urls import (
    detail_image_url,
    is_likely_direct_image_url,
    is_social_or_page_url,
    preview_link_for_text,
)


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
