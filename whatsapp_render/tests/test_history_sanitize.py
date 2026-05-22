from app.conversation import sanitize_assistant_for_history


def test_strips_invented_listing_without_tag():
    invented = (
        "Te paso opciones:\n"
        "1. Casa en *Zona Norte* — USD 120.000\n"
        "2. Depto Villa Urquiza — $450/mes\n"
    )
    clean = sanitize_assistant_for_history(invented)
    assert "Zona Norte" not in clean
    assert "Villa Urquiza" not in clean


def test_keeps_valid_listado_tag():
    msg = "¡Genial!\n\n[LISTADO:5,8]\n\n¿Cuál te interesa?"
    assert "[LISTADO:5,8]" in sanitize_assistant_for_history(msg)
