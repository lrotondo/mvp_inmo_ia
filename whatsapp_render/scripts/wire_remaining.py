from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch_main() -> None:
    p = ROOT / "app/main.py"
    t = p.read_text(encoding="utf-8")
    old = "                property_ref=property_ref,\n            )\n        except MetaSendError"
    new = (
        "                property_ref=property_ref,\n"
        "                capture_data=turn_result.capture_data or session.capture_data,\n"
        "            )\n        except MetaSendError"
    )
    if old in t and "capture_data=turn_result" not in t:
        t = t.replace(old, new, 1)
        p.write_text(t, encoding="utf-8")
        print("main ok")
    else:
        print("main skip")


def patch_inbound() -> None:
    p = ROOT / "app/pipeline/inbound.py"
    t = p.read_text(encoding="utf-8")
    needle = (
        "    if interest_classification and interest_classification.property_ref.strip():\n"
        "        property_ref = interest_classification.property_ref.strip()\n"
        "    if not property_ref:"
    )
    insert = (
        "    if interest_classification and interest_classification.property_ref.strip():\n"
        "        property_ref = interest_classification.property_ref.strip()\n"
        "\n"
        "    listing_rows = load_last_listing_rows(\n"
        "        plan.catalog_path_used, session.capture_data\n"
        "    )\n"
        "    if plan.kind == TurnKind.DETAIL and listing_rows:\n"
        "        choice_ref = property_ref_from_listing_choice(user_text, listing_rows)\n"
        "        if choice_ref.strip():\n"
        "            property_ref = choice_ref.strip()\n"
        "\n"
        "    if not property_ref:"
    )
    if "property_ref_from_listing_choice" not in t and needle in t:
        t = t.replace(needle, insert, 1)
        p.write_text(t, encoding="utf-8")
        print("inbound choice ok")
    else:
        print("inbound choice skip")


def patch_detail_media() -> None:
    p = ROOT / "app/detail_media.py"
    t = p.read_text(encoding="utf-8")
    if "capture_data: dict[str, Any] | None = None," not in t.split("enrich_detail_media_from_catalog")[1][:400]:
        t = t.replace(
            "    catalog_rent_path: str | None = None,\n) -> str:\n    \"\"\"Detalle / elección",
            "    catalog_rent_path: str | None = None,\n"
            "    capture_data: dict[str, Any] | None = None,\n) -> str:\n    \"\"\"Detalle / elección",
            1,
        )
    pairs = [
        (
            "        catalog_csv_path=catalog_csv_path,\n    )\n    if not ref:",
            "        catalog_csv_path=catalog_csv_path,\n        capture_data=capture_data,\n    )\n    if not ref:",
        ),
        (
            "        catalog_rent_path=catalog_rent_path,\n    )\n    if row is None:\n        row = get_property_row_by_ref",
            "        catalog_rent_path=catalog_rent_path,\n        capture_data=capture_data,\n    )\n    if row is None:\n        row = get_property_row_by_ref",
        ),
        (
            "    graph_version: str | None = None,\n) -> str | None:\n    \"\"\"\n    Envía foto",
            "    graph_version: str | None = None,\n    capture_data: dict[str, Any] | None = None,\n) -> str | None:\n    \"\"\"\n    Envía foto",
        ),
        (
            "        catalog_rent_path=catalog_rent_path,\n    )\n\n    if not should_deliver_property_detail_ficha",
            "        catalog_rent_path=catalog_rent_path,\n        capture_data=capture_data,\n    )\n\n    if not should_deliver_property_detail_ficha",
        ),
    ]
    for old, new in pairs:
        if old in t:
            t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print("detail_media ok")


def patch_listing_delivery() -> None:
    p = ROOT / "app/listing_delivery.py"
    t = p.read_text(encoding="utf-8")
    if "capture_data: dict[str, Any] | None = None" not in t.split("async def deliver_bot_response")[1][:800]:
        t = t.replace(
            '    property_ref: str = "",\n) -> str:',
            '    property_ref: str = "",\n    capture_data: dict[str, Any] | None = None,\n) -> str:',
            1,
        )
        t = t.replace(
            "property_ref=property_ref,\n            graph_version=graph_version,",
            "property_ref=property_ref,\n            capture_data=capture_data,\n            graph_version=graph_version,",
        )
    old = (
        "    consolidated = consolidate_history_text(\n"
        "        intro_text,\n"
        "        history_items,\n"
        "        closing_text,\n"
        "    )\n"
        "    logger.info(\n"
        '        "listado_multi_imagen enviado items=%s ids=%s",'
    )
    new = (
        "    consolidated = consolidate_history_text(\n"
        "        intro_text,\n"
        "        history_items,\n"
        "        closing_text,\n"
        "    )\n"
        "    if parsed.property_ids:\n"
        "        tag = \"[LISTADO:\" + \",\".join(parsed.property_ids) + \"]\"\n"
        "        consolidated = f\"{consolidated}\\n\\n{tag}\".strip()\n"
        "    logger.info(\n"
        '        "listado_multi_imagen enviado items=%s ids=%s",'
    )
    if old in t and "tag = f" not in t[t.find(old) : t.find(old) + 500]:
        t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print("listing_delivery ok")


if __name__ == "__main__":
    patch_inbound()
    patch_detail_media()
    patch_listing_delivery()
    patch_main()
