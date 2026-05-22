"""One-off patch script for bedroom + listing choice fixes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch_detail_media() -> None:
    p = ROOT / "app" / "detail_media.py"
    text = p.read_text(encoding="utf-8")

    old = '''    r"(?:la|el)\\s+(?:opci[oó]n|de)\\s*\\d+|opci[oó]n\\s*\\d+|"
    r"esa\\s+(?:me\\s+)?(?:gusta|interesa)|"'''
    new = '''    r"(?:la|el)\\s+(?:opci[oó]n|de)\\s*\\d+|opci[oó]n\\s*\\d+|"
    r"(?:la|el)\\s+duplex|(?:la|el)\\s+d[uú]plex|el\\s+duplex|el\\s+d[uú]plex|"
    r"esa\\s+(?:me\\s+)?(?:gusta|interesa)|"'''
    if old not in text:
        raise RuntimeError("detail_media interest anchor missing")
    text = text.replace(old, new, 1)

    old_resolve = '''def resolve_detail_property_row(
    *,
    catalog_csv_path: str | None,
    current_user_text: str,
    outbound_message: str,
    history: list | None,
    property_ref: str,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> dict[str, Any] | None:
    """Resuelve fila del catálogo para enviar ficha + media."""
    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        outbound_message=outbound_message,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
        catalog_csv_path=catalog_csv_path,
    )
    if not ref and (property_ref or "").strip():
        ref = property_ref.strip()

    row: dict[str, Any] | None = None
    if ref:
        row = get_property_row_by_ref(catalog_csv_path, ref)

    if row is None:
        listado_rows = _rows_from_recent_listado(history, catalog_csv_path)
        for blob in (current_user_text, outbound_message):
            if not (blob or "").strip():
                continue
            row = find_property_row_for_user_text(
                catalog_csv_path,
                blob,
                rows_scope=listado_rows or None,
            )
            if row is not None:
                break

    if row is None and history:
        for turn in reversed(history or []):
            if turn.role != "user":
                continue
            row = find_property_row_for_user_text(
                catalog_csv_path, turn.content
            )
            if row is not None:
                break

    return row'''

    new_resolve = '''def resolve_detail_property_row(
    *,
    catalog_csv_path: str | None,
    current_user_text: str,
    outbound_message: str,
    history: list | None,
    property_ref: str,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    capture_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resuelve fila del catálogo para enviar ficha + media."""
    from app.listing_context import (
        load_last_listing_rows,
        resolve_listing_choice_row,
    )

    listado_rows = load_last_listing_rows(catalog_csv_path, capture_data)
    if not listado_rows:
        listado_rows = _rows_from_recent_listado(history, catalog_csv_path)

    choice_row = resolve_listing_choice_row(current_user_text, listado_rows)
    if choice_row is not None:
        return choice_row

    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        outbound_message=outbound_message,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
        catalog_csv_path=catalog_csv_path,
        capture_data=capture_data,
        listing_rows=listado_rows,
    )
    if not ref and (property_ref or "").strip():
        ref = property_ref.strip()

    row: dict[str, Any] | None = None
    if ref:
        row = get_property_row_by_ref(catalog_csv_path, ref)
        if row is None and listado_rows:
            ref_id = ref.strip().lower()
            for candidate in listado_rows:
                if str(candidate.get("ID", "")).strip().lower() == ref_id:
                    row = candidate
                    break

    if row is None and listado_rows:
        row = find_property_row_for_user_text(
            catalog_csv_path,
            current_user_text,
            rows_scope=listado_rows,
        )

    if row is None and history and not user_showed_property_interest(current_user_text):
        for turn in reversed(history or []):
            if turn.role != "user":
                continue
            row = find_property_row_for_user_text(
                catalog_csv_path, turn.content
            )
            if row is not None:
                break

    return row'''

    if old_resolve not in text:
        raise RuntimeError("resolve_detail_property_row block missing")
    text = text.replace(old_resolve, new_resolve, 1)

    old_pref = '''def property_ref_for_detail_enrich(
    *,
    current_user_text: str,
    outbound_message: str = "",
    history: list,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    fallback_ref: str = "",
    catalog_csv_path: str | None = None,
) -> str:
    """Referencia desde mensaje del usuario (prioridad), historial o fallback."""
    ref_user = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        history=[],
        current_user_text=current_user_text,
        user_only=True,
    )
    if ref_user.strip():
        return ref_user.strip()

    opt_ref = _property_ref_from_option_number(current_user_text, catalog_csv_path)
    if opt_ref:
        return opt_ref

    if (fallback_ref or "").strip():
        return fallback_ref.strip()

    if (outbound_message or "").strip() and (
        bot_promises_visual_material(outbound_message)
        or user_showed_property_interest(current_user_text)
    ):
        ref_bot = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            history=[],
            current_user_text=outbound_message,
            user_only=True,
        )
        if ref_bot.strip():
            return ref_bot.strip()

    opt_out = _property_ref_from_option_number(outbound_message, catalog_csv_path)
    if opt_out:
        return opt_out'''

    new_pref = '''def property_ref_for_detail_enrich(
    *,
    current_user_text: str,
    outbound_message: str = "",
    history: list,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    fallback_ref: str = "",
    catalog_csv_path: str | None = None,
    capture_data: dict[str, Any] | None = None,
    listing_rows: list[dict[str, Any]] | None = None,
) -> str:
    """Referencia desde mensaje del usuario (prioridad), historial o fallback."""
    from app.listing_context import (
        load_last_listing_rows,
        property_ref_from_listing_choice,
        property_ref_from_listing_option_number,
    )

    scoped_rows = listing_rows
    if scoped_rows is None:
        scoped_rows = load_last_listing_rows(catalog_csv_path, capture_data)

    if scoped_rows:
        ref_listing = property_ref_from_listing_choice(
            current_user_text, scoped_rows
        )
        if ref_listing.strip():
            return ref_listing.strip()

        opt_listing = property_ref_from_listing_option_number(
            current_user_text, scoped_rows
        )
        if opt_listing.strip():
            return opt_listing.strip()

    user_interest = user_showed_property_interest(current_user_text)

    if not user_interest:
        ref_user = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            history=[],
            current_user_text=current_user_text,
            user_only=True,
        )
        if ref_user.strip():
            return ref_user.strip()

    if (fallback_ref or "").strip():
        return fallback_ref.strip()

    if not user_interest and (outbound_message or "").strip() and (
        bot_promises_visual_material(outbound_message)
    ):
        ref_bot = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            history=[],
            current_user_text=outbound_message,
            user_only=True,
        )
        if ref_bot.strip():
            return ref_bot.strip()

    if not user_interest:
        opt_out = _property_ref_from_option_number(
            outbound_message, catalog_csv_path
        )
        if opt_out:
            return opt_out'''

    if old_pref not in text:
        raise RuntimeError("property_ref_for_detail_enrich block missing")
    text = text.replace(old_pref, new_pref, 1)

    old_enrich_sig = '''def enrich_detail_media_from_catalog(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
    current_user_text: str = "",
    flow_path: str = "compra",
    history: list | None = None,
    catalog_sale_path: str | None = None,
    catalog_rent_path: str | None = None,
) -> str:'''
    new_enrich_sig = '''def enrich_detail_media_from_catalog(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
    current_user_text: str = "",
    flow_path: str = "compra",
    history: list | None = None,
    catalog_sale_path: str | None = None,
    catalog_rent_path: str | None = None,
    capture_data: dict[str, Any] | None = None,
) -> str:'''
    if old_enrich_sig not in text:
        raise RuntimeError("enrich sig missing")
    text = text.replace(old_enrich_sig, new_enrich_sig, 1)

    old_row_call = '''    row = resolve_detail_property_row(
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        outbound_message=body,
        history=history,
        property_ref=ref or property_ref,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
    )'''
    new_row_call = '''    row = resolve_detail_property_row(
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        outbound_message=body,
        history=history,
        property_ref=ref or property_ref,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        capture_data=capture_data,
    )'''
    if old_row_call not in text:
        raise RuntimeError("enrich row call missing")
    text = text.replace(old_row_call, new_row_call, 1)

    p.write_text(text, encoding="utf-8")
    print("detail_media patched")


def patch_pipeline() -> None:
    p = ROOT / "app" / "pipeline" / "inbound.py"
    text = p.read_text(encoding="utf-8")

    if "merge_last_listing_into_capture" not in text:
        text = text.replace(
            "from app.session_state import SessionState",
            "from app.listing_context import merge_last_listing_into_capture\n"
            "from app.session_state import SessionState",
        )
        text = text.replace(
            "from app.property_matching import extract_property_ref",
            "from app.listing_context import (\n"
            "    load_last_listing_rows,\n"
            "    property_ref_from_listing_choice,\n"
            ")\n"
            "from app.property_matching import extract_property_ref",
        )

    old_ref = '''    property_ref = plan.property_ref
    if interest_classification and interest_classification.property_ref.strip():
        property_ref = interest_classification.property_ref.strip()
    if not property_ref:
        property_ref = extract_property_ref('''

    new_ref = '''    property_ref = plan.property_ref
    if interest_classification and interest_classification.property_ref.strip():
        property_ref = interest_classification.property_ref.strip()

    listing_rows = load_last_listing_rows(
        plan.catalog_path_used, session.capture_data
    )
    if plan.kind.value == "detail" and listing_rows:
        choice_ref = property_ref_from_listing_choice(user_text, listing_rows)
        if choice_ref.strip():
            property_ref = choice_ref.strip()

    if not property_ref:
        property_ref = extract_property_ref('''

    if old_ref in text and "property_ref_from_listing_choice" not in text.split("if not property_ref")[0]:
        text = text.replace(old_ref, new_ref, 1)

    old_enrich = '''    clean_answer = enrich_detail_media_from_catalog(
        clean_answer,
        catalog_csv_path=plan.catalog_path_used,
        property_ref=property_ref,
        current_user_text=user_text,
        flow_path=flow_path,
        history=history,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
    )'''

    new_enrich = '''    clean_answer = enrich_detail_media_from_catalog(
        clean_answer,
        catalog_csv_path=plan.catalog_path_used,
        property_ref=property_ref,
        current_user_text=user_text,
        flow_path=flow_path,
        history=history,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
        capture_data=session.capture_data,
    )'''

    if old_enrich in text:
        text = text.replace(old_enrich, new_enrich, 1)

    old_capture = '''    capture_data: dict[str, Any] | None = None
    if plan.profile and flow_path in ("compra", "alquiler"):
        capture_data = session_capture_with_profile(session, plan.profile, flow_path)'''

    new_capture = '''    capture_data: dict[str, Any] | None = None
    if plan.profile and flow_path in ("compra", "alquiler"):
        capture_data = session_capture_with_profile(session, plan.profile, flow_path)
    if plan.kind == TurnKind.LISTING and plan.candidate_ids:
        base = capture_data if capture_data is not None else dict(session.capture_data)
        capture_data = merge_last_listing_into_capture(
            base,
            property_ids=plan.candidate_ids,
            branch=flow_path,
            catalog_path=plan.catalog_path_used,
        )'''

    if old_capture in text:
        text = text.replace(old_capture, new_capture, 1)

    p.write_text(text, encoding="utf-8")
    print("pipeline patched")


def patch_listing_delivery() -> None:
    p = ROOT / "app" / "listing_delivery.py"
    text = p.read_text(encoding="utf-8")
    old = '''    consolidated = consolidate_history_text(
        intro_text,
        history_items,
        closing_text,
    )
    logger.info(
        "listado_multi_imagen enviado items=%s ids=%s",
        len(history_items),
        parsed.property_ids,
    )
    return consolidated or parsed.text_without_tag or body'''

    new = '''    consolidated = consolidate_history_text(
        intro_text,
        history_items,
        closing_text,
    )
    if parsed.property_ids:
        tag = f"[LISTADO:{','.join(parsed.property_ids)}]"
        consolidated = f"{consolidated}\\n\\n{tag}".strip()
    logger.info(
        "listado_multi_imagen enviado items=%s ids=%s",
        len(history_items),
        parsed.property_ids,
    )
    return consolidated or parsed.text_without_tag or body'''

    if old in text:
        text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
        print("listing_delivery patched")
    else:
        print("listing_delivery skip (already patched?)")


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

    old = '''    if plan.kind == TurnKind.INTAKE and plan.profile:
        return build_intake_outbound(plan.profile)

    catalog_block = ""'''
    new = '''    if plan.kind == TurnKind.INTAKE and plan.profile:
        return build_intake_outbound(plan.profile)

    if plan.kind == TurnKind.DETAIL:
        from app.listing_context import load_last_listing_rows

        rows = load_last_listing_rows(
            plan.catalog_path_used,
            None,
        )
        return await build_detail_outbound(user_text, listing_rows=rows)

    catalog_block = ""'''
    if old in text and "TurnKind.DETAIL" not in text.split("generate_turn_reply")[1][:400]:
        text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
        print("turn_handler patched")
    else:
        print("turn_handler skip")


def main() -> None:
    patch_detail_media()
    patch_pipeline()
    patch_listing_delivery()
    patch_turn_handler()


if __name__ == "__main__":
    main()
