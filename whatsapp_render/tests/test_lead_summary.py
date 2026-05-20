from __future__ import annotations

import unittest

from app.leads import is_transcript_summary


class TestIsTranscriptSummary(unittest.TestCase):
    def test_detects_cliente_lines(self) -> None:
        text = (
            "Cliente: Hello!\n"
            "Cliente: Comprar\n"
            "Cliente: Zona de la terminal\n"
            "Cliente: 80000\n"
        )
        self.assertTrue(is_transcript_summary(text))

    def test_accepts_prose_summary(self) -> None:
        text = (
            "Andrea busca comprar en la zona de la terminal con presupuesto "
            "aproximado de USD 80.000 y pidió más fotos de la opción 1."
        )
        self.assertFalse(is_transcript_summary(text))

    def test_empty_is_transcript(self) -> None:
        self.assertTrue(is_transcript_summary(""))
