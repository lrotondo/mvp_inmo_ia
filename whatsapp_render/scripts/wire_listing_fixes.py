"""Wire last_listing persistence and capture_data through delivery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch_inbound() -> None:
    p = ROOT / "app" / "pipeline" / "inbound.py"
    text = p.read_text(encoding="utf-8")

    if "merge_last_listing_into_capture" not in text:
        text = text.replace(
            "from app.property_matching import extract_property_ref",
            "from app.listing_context import (\n"
            "    load_last_listing_rows,\n"
            "    merge_last_listing_into_capture,\n"
            "    property_ref_from_listing_choice,\n"
            ")\n"
            "from app.property_matching import extract_property_ref",
        )

    old = """    property_ref = plan.property_ref
    if interest_classification and interest_classification.property_ref.strip():
        property_ref = interest_classification.property_ref.strip()
    if not property_ref:"""

    new = """    property_ref = plan.property_ref
    if interest_classification and interest_classification.property_ref.strip():
        property_ref = interest_classification.property_ref.strip()

    listing_rows = load_last_listing_rows(
        plan.catalog_path_used, session.capture_data
    )
    if plan.kind == TurnKind.DETAIL and listing_rows:
        choice_ref = property_ref_from_listing_choice(user_text, listing_rows)
        if choice_ref.strip():
            property_ref = choice_ref.strip()

    if not property_ref:"""

    if old in text and "property_ref_from_listing_choice" not in text.split("if not property_ref")[0]:
        text = text.replace(old, new, 1)

    old_enrich = """    clean_answer = enrich_detail_media_from_catalog(
        clean_answer,
        catalog_csv_path=plan.catalog_path_used,
        property_ref=property_ref,
        current_user_text=user_text,
        flow_path=flow_path,
        history=history,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
    )"""

    new_enrich = """    capture_data: dict[str, Any] | None = None
    if plan.profile and flow_path in ("compra", "alquiler"):
        capture_data = session_capture_with_profile(session, plan.profile, flow_path)
    if plan.kind == TurnKind.LISTING and plan.candidate_ids:
        base = capture_data if capture_data is not None else dict(session.capture_data)
        capture_data = merge_last_listing_into_capture(
            base,
            property_ids=plan.candidate_ids,
            branch=flow_path,
            catalog_path=plan.catalog_path_used,
        )

    clean_answer = enrich_detail_media_from_catalog(
        clean_answer,
        catalog_csv_path=plan.catalog_path_used,
        property_ref=property_ref,
        current_user_text=user_text,
        flow_path=flow_path,
        history=history,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
        capture_data=capture_data or session.capture_data,
    )"""

    if old_enrich in text:
        text = text.replace(old_enrich, new_enrich, 1)
        old_capture = """    capture_data: dict[str, Any] | None = None
    if plan.profile and flow_path in ("compra", "alquiler"):
        capture_data = session_capture_with_profile(session, plan.profile, flow_path)

    logger.info("""
        if old_capture in text:
            text = text.replace(old_capture, "\n    logger.info(", 1)

    p.write_text(text, encoding="utf-8")
    print("inbound ok")


def patch_detail_media_enrich() -> None:
    p = ROOT / "app" / "detail_media.py"
    text = p.read_text(encoding="utf-8")
    old_sig = """def enrich_detail_media_from_catalog(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
    current_user_text: str = "",
    flow_path: str = "compra",
    history: list | None = None,
    catalog_sale_path: str | None = None,
    catalog_rent_path: str | None = None,
) -> str:"""
    new_sig = old_sig.replace(
        "catalog_rent_path: str | None = None,\n) -> str:",
        "catalog_rent_path: str | None = None,\n    capture_data: dict[str, Any] | None = None,\n) -> str:",
    )
    if old_sig in text:
        text = text.replace(old_sig, new_sig, 1)

    old_ref = """    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        outbound_message=body,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
        catalog_csv_path=catalog_csv_path,
    )"""
    new_ref = old_ref.replace(
        "catalog_csv_path=catalog_csv_path,\n    )",
        "catalog_csv_path=catalog_csv_path,\n        capture_data=capture_data,\n    )",
    )
    if old_ref in text and "capture_data=capture_data" not in text.split("enrich_detail_media_from_catalog")[1][:2500]:
        text = text.replace(old_ref, new_ref, 1)

    old_row = """    row = resolve_detail_property_row(
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        outbound_message=body,
        history=history,
        property_ref=ref or property_ref,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
    )
    if row is None:
        row = get_property_row_by_ref(catalog_csv_path, ref)"""
    new_row = old_row.replace(
        "catalog_rent_path=catalog_rent_path,\n    )",
        "catalog_rent_path=catalog_rent_path,\n        capture_data=capture_data,\n    )",
    )
    if old_row in text:
        text = text.replace(old_row, new_row, 1)

    old_try = """async def try_deliver_single_property_visual(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    message: str,
    catalog_csv_path: str | None,
    current_user_text: str,
    flow_path: str,
    history: list | None,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    property_ref: str = "",
    graph_version: str | None = None,
) -> str | None:"""
    new_try = old_try.replace(
        'graph_version: str | None = None,\n) -> str | None:',
        'graph_version: str | None = None,\n    capture_data: dict[str, Any] | None = None,\n) -> str | None:',
    )
    if old_try in text:
        text = text.replace(old_try, new_try, 1)

    old_resolve_call = """    row = resolve_detail_property_row(
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        outbound_message=body,
        history=history,
        property_ref=property_ref,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
    )

    if not should_deliver_property_detail_ficha("""
    new_resolve_call = old_resolve_call.replace(
        "catalog_rent_path=catalog_rent_path,\n    )\n\n    if not should_deliver",
        "catalog_rent_path=catalog_rent_path,\n        capture_data=capture_data,\n    )\n\n    if not should_deliver",
    )
    if old_resolve_call in text:
        text = text.replace(old_resolve_call, new_resolve_call, 1)

    p.write_text(text, encoding="utf-8")
    print("detail_media enrich ok")


def patch_listing_delivery() -> None:
    p = ROOT / "app" / "listing_delivery.py"
    text = p.read_text(encoding="utf-8")

    if "capture_data: dict" not in text.split("async def deliver_bot_response")[1][:800]:
        text = text.replace(
            "    property_ref: str = \"\",\n) -> str:",
            "    property_ref: str = \"\",\n    capture_data: dict[str, Any] | None = None,\n) -> str:",
            1,
        )
        for old_call in (
            """            property_ref=property_ref,
            graph_version=graph_version,
        )
        if visual_sent is not None:
            return strip_listado_tags(visual_sent)""",
        ):
            pass
        text = text.replace(
            "property_ref=property_ref,\n            graph_version=graph_version,",
            "property_ref=property_ref,\n            capture_data=capture_data,\n            graph_version=graph_version,",
        )

    old_return = """    consolidated = consolidate_history_text(
        intro_text,
        history_items,
        closing_text,
    )
    logger.info(
        "listado_multi_imagen enviado items=%s ids=%s","""

    new_return = """    consolidated = consolidate_history_text(
        intro_text,
        history_items,
        closing_text,
    )
    if parsed.property_ids:
        tag = f"[LISTADO:{','.join(parsed.property_ids)}]"
        consolidated = f"{consolidated}\\n\\n{tag}".strip()
    logger.info(
        "listado_multi_imagen enviado items=%s ids=%s","""

    if old_return in text and "[LISTADO:" not in text[text.find(old_return): text.find(old_return) + 400]:
        text = text.replace(old_return, new_return, 1)

    p.write_text(text, encoding="utf-8")
    print("listing_delivery ok")


def patch_main() -> None:
    p = ROOT / "app" / "main.py"
    text = p.read_text(encoding="utf-8")
    old = """                property_ref=property_ref,
            )"""
    new = """                property_ref=property_ref,
                capture_data=turn_result.capture_data or session.capture_data,
            )"""
    if old in text and "capture_data=turn_result" not in text:
        text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
    print("main ok")


def patch_turn_handler() -> None:
    p = ROOT / "app" / "turn_handler.py"
    text = p.read_text(encoding="utf-8")
    insert = '''async def build_detail_outbound(
    user_text: str,
    *,
    listing_rows: list,
) -> str:
    """Intro corta de detalle; la ficha la arma el backend."""
    from app.listing_context import resolve_listing_choice_row

    row = resolve_listing_choice_row(user_text, listing_rows)
    if row is not None:
        titulo = str(row.get("Titulo", "")).strip()
        if titulo:
            return f"¡Excelente elección! Te paso la ficha de *{titulo}* 👇"
    return "¡Excelente elección! Te paso la ficha con todos los detalles 👇"


'''
    if "build_detail_outbound" not in text:
        text = text.replace(
            "async def generate_turn_reply(",
            insert + "async def generate_turn_reply(",
        )

    old = """    if plan.kind == TurnKind.INTAKE and plan.profile:
        return build_intake_outbound(plan.profile)

    catalog_block = \"\""""
    new = """    if plan.kind == TurnKind.INTAKE and plan.profile:
        return build_intake_outbound(plan.profile)

    if plan.kind == TurnKind.DETAIL:
        from app.listing_context import load_last_listing_rows

        rows = load_last_listing_rows(plan.catalog_path_used, None)
        return await build_detail_outbound(user_text, listing_rows=rows)

    catalog_block = \"\""""
    if old in text and "TurnKind.DETAIL" not in text[text.find("generate_turn_reply"): text.find("catalog_block")]:
        text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
    print("turn_handler ok")


if __name__ == "__main__":
    patch_inbound()
    patch_detail_media_enrich()
    patch_listing_delivery()
    patch_main()
    patch_turn_handler()
