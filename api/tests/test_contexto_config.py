"""Configuración y límites con valores ficticios, sin leer archivos .env."""

import ast
import os
import runpy
import unittest
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from schemas.chat import ConsultaChat


RAIZ = Path(__file__).resolve().parents[2]


class ContextoConfigTests(unittest.TestCase):
    def test_limite_configurado_y_validacion_en_ambos_servicios(self):
        for servicio, archivo_schema, modelo in (
            ("api", "chat_jev.py", "ConsultaChatJev"),
            ("jeveador", "jev.py", "ConsultaJev"),
        ):
            with self.subTest(servicio=servicio):
                obtener = runpy.run_path(str(RAIZ / servicio / "funciones/contexto_config.py"))["obtener_max_contexto"]
                with patch.dict(os.environ, {"MAX_CONTEXTO": "3"}, clear=True):
                    self.assertEqual(obtener(), 3)
                    arbol = ast.parse((RAIZ / servicio / "schemas" / archivo_schema).read_text(encoding="utf-8"))
                    arbol.body = [n for n in arbol.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
                    contexto = dict(globals(), obtener_max_contexto=obtener)
                    exec(compile(arbol, archivo_schema, "exec"), contexto)
                    consulta = contexto[modelo]
                    consulta(mensaje="sí", contexto=["mensaje"] * 3)
                    self.assertEqual(consulta.model_json_schema()["properties"]["contexto"]["maxItems"], 3)
                    with self.assertRaises(ValidationError):
                        consulta(mensaje="sí", contexto=["mensaje"] * 4)

    def test_default_y_valores_invalidos(self):
        for servicio in ("api", "jeveador"):
            obtener = runpy.run_path(str(RAIZ / servicio / "funciones/contexto_config.py"))["obtener_max_contexto"]
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(obtener(), 20)
            for valor in ("0", "-1", "abc", "", "1.5"):
                with self.subTest(servicio=servicio, valor=valor), patch.dict(os.environ, {"MAX_CONTEXTO": valor}, clear=True):
                    with self.assertRaisesRegex(ValueError, "MAX_CONTEXTO debe ser un entero mayor que cero"):
                        obtener()


if __name__ == "__main__":
    unittest.main()
