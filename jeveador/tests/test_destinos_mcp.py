"""Destinos ficticios de descubrimiento; no se abren conexiones."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from funciones import destinos_mcp


class DestinosTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.archivo = Path(temporal.name) / "destinos.json"
        self.archivo.write_text(json.dumps({"destinos": ["http://127.0.0.1:8123/mcp"]}), encoding="utf-8")
        parche = patch.object(destinos_mcp, "RUTA_POLITICA", self.archivo)
        parche.start()
        self.addCleanup(parche.stop)

    def test_localhost_se_normaliza_al_literal_autorizado(self):
        """El descubrimiento usa la IP loopback permitida y evita resolver nombres externos."""
        self.assertEqual(destinos_mcp.validar_destino("http://localhost:8123/mcp"), (True, "http://127.0.0.1:8123/mcp"))

    def test_otro_puerto_host_o_ruta_se_rechaza(self):
        """La habilitación en SQLite no autoriza destinos ajenos a la política de descubrimiento."""
        for url in ["http://127.0.0.1:8124/mcp", "http://169.254.169.254/mcp", "http://prueba.invalid:8123/mcp", "http://127.0.0.1:8123/admin"]:
            with self.subTest(url=url), self.assertLogs(level="ERROR"):
                self.assertEqual(destinos_mcp.validar_destino(url), (False, {"status_code": 503}))

    def test_politica_ausente_o_invalida_impide_descubrir(self):
        """Una política ilegible o inválida no habilita conexiones por defecto."""
        for texto in ["no es json", "{}", '{"destinos": ["http://externo.invalid/mcp"]}']:
            self.archivo.write_text(texto, encoding="utf-8")
            with self.assertLogs(level="ERROR"):
                self.assertEqual(destinos_mcp.validar_destino("http://localhost:8123/mcp"), (False, {"status_code": 503}))
