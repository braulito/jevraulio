"""Consulta administrativa simulada, sin cargar .env ni servicios reales."""

import io
import json
import os
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import funciones
from app import crear_app


class CostosJevTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="jev_costos_admin_")
        self.addCleanup(temporal.cleanup)
        self.salida = Path(temporal.name) / "salida.json"
        self.tokens = Path(temporal.name) / "tokens_count.json"
        destino_tokens = patch.object(funciones, "TOKENS_JSON", self.tokens)
        destino_tokens.start()
        self.addCleanup(destino_tokens.stop)
        destino = patch.object(funciones, "SALIDA_JSON", self.salida)
        destino.start()
        self.addCleanup(destino.stop)
        entorno = patch.dict(os.environ, {
            "JEV_ADMIN_URL": "https://admin-ficticio.invalid/costos",
            "JEV_ADMIN_KEY": "clave-ficticia",
        }, clear=True)
        entorno.start()
        self.addCleanup(entorno.stop)
        configuracion = patch.multiple(funciones,
            JEV_ADMIN_URL="https://admin-ficticio.invalid/costos",
            JEV_ADMIN_KEY="clave-ficticia",
            JEV_ADMIN_TOKENS="https://admin-ficticio.invalid/tokens",
        )
        configuracion.start()
        self.addCleanup(configuracion.stop)

    def test_get_autenticado_devuelve_creditos(self):
        datos = {"data": [{"limit": 10, "usage": 1.25, "limit_remaining": 8.75}]}
        with patch("funciones.urlopen", return_value=io.BytesIO(json.dumps(datos).encode())) as enviar:
            self.assertEqual(funciones.consultar_costos_jev(), (
                True, {"credito_total": 10, "usados": 1.25, "restantes": 8.75},
            ))
        peticion = enviar.call_args.args[0]
        self.assertEqual(peticion.get_method(), "GET")
        self.assertEqual(peticion.full_url, "https://admin-ficticio.invalid/costos")
        self.assertEqual(peticion.get_header("Authorization"), "Bearer clave-ficticia")
        self.assertIsNone(peticion.data)
        self.assertEqual(enviar.call_args.kwargs["timeout"], 30)
        self.assertFalse(self.salida.exists())

    def test_excepcion_generica_termina_sin_exponer_detalles(self):
        with patch("funciones.urlopen", side_effect=RuntimeError("detalle-privado")), patch.object(funciones.logger, "error") as registrar:
            self.assertEqual(funciones.consultar_costos_jev(), (False, {}))
        self.assertFalse(self.salida.exists())
        self.assertEqual(registrar.call_args.args[1], "RuntimeError")
        self.assertNotIn("detalle-privado", str(registrar.call_args))
        self.assertNotIn("clave-ficticia", str(registrar.call_args))

    def test_json_invalido_conserva_salida_anterior(self):
        self.salida.write_text('{"anterior": true}', encoding="utf-8")
        with patch("funciones.urlopen", return_value=io.BytesIO(b"no es json")), patch.object(funciones.logger, "error"):
            funciones.consultar_costos_jev()
        self.assertEqual(json.loads(self.salida.read_text(encoding="utf-8")), {"anterior": True})

    def test_configuracion_ausente_no_hace_get(self):
        with patch.object(funciones, "JEV_ADMIN_KEY", ""), patch("funciones.urlopen") as enviar, patch.object(funciones.logger, "error") as registrar:
            funciones.consultar_costos_jev()
        enviar.assert_not_called()
        registrar.assert_called_once()

    def test_respuesta_sin_creditos_se_registra_y_termina(self):
        with patch("funciones.urlopen", return_value=io.BytesIO(b"{}")), patch.object(funciones.logger, "error") as registrar:
            self.assertEqual(funciones.consultar_costos_jev(), (False, {}))
        self.assertEqual(registrar.call_args.args[1], "KeyError")

    def test_cargar_costos_muestra_modal_si_falla_api_sql(self):
        with patch("funciones.consultar_costos_api", return_value=(False, {})) as consultar, patch("dotenv.load_dotenv", side_effect=AssertionError("No cargar .env")):
            app = crear_app(cargar_entorno=False)
            for ruta in ("/costos", "/costos.html"):
                respuesta = app.test_client().get(ruta)
                self.assertEqual(respuesta.status_code, 503)
                self.assertIn('id="modal-error"', respuesta.get_data(as_text=True))
        self.assertEqual(consultar.call_count, 2)

    def test_costos_no_consulta_administracion_jev_ni_imprime_creditos(self):
        with patch("funciones.consultar_costos_jev") as creditos, patch("funciones.consultar_tokens_jev") as tokens, patch("funciones.consultar_costos_api", return_value=(False, {})), patch("builtins.print") as imprimir:
            app = crear_app(cargar_entorno=False)
            app.test_client().get("/costos")
        creditos.assert_not_called()
        tokens.assert_not_called()
        imprimir.assert_not_called()
        self.assertFalse(logging.getLogger("werkzeug").propagate)

    def test_tokens_hace_get_autenticado_y_guarda_respuesta_completa(self):
        datos = {"data": [{"input_tokens": 123, "output_tokens": 45}], "total": 168}
        with patch("funciones.urlopen", return_value=io.BytesIO(json.dumps(datos).encode())) as enviar:
            self.assertEqual(funciones.consultar_tokens_jev(), (True, datos))
        peticion = enviar.call_args.args[0]
        self.assertEqual(peticion.get_method(), "GET")
        self.assertEqual(peticion.full_url, "https://admin-ficticio.invalid/tokens")
        self.assertEqual(peticion.get_header("Authorization"), "Bearer clave-ficticia")
        self.assertEqual(json.loads(self.tokens.read_text(encoding="utf-8")), datos)

    def test_tokens_error_generico_no_expone_detalles(self):
        with patch("funciones.urlopen", side_effect=RuntimeError("detalle-privado")), patch.object(funciones.logger, "error") as registrar:
            self.assertEqual(funciones.consultar_tokens_jev(), (False, {}))
        self.assertFalse(self.tokens.exists())
        self.assertNotIn("detalle-privado", str(registrar.call_args))
        self.assertNotIn("clave-ficticia", str(registrar.call_args))

    def test_tokens_json_invalido_conserva_archivo_anterior(self):
        self.tokens.write_text('{"anterior": true}', encoding="utf-8")
        with patch("funciones.urlopen", return_value=io.BytesIO(b"no es json")), patch.object(funciones.logger, "error"):
            self.assertEqual(funciones.consultar_tokens_jev(), (False, {}))
        self.assertEqual(json.loads(self.tokens.read_text(encoding="utf-8")), {"anterior": True})

    def test_tokens_sin_url_no_hace_get(self):
        with patch.object(funciones, "JEV_ADMIN_TOKENS", ""), patch("funciones.urlopen") as enviar, patch.object(funciones.logger, "error"):
            self.assertEqual(funciones.consultar_tokens_jev(), (False, {}))
        enviar.assert_not_called()

    def test_tokens_error_de_escritura_se_registra(self):
        with patch.object(funciones, "TOKENS_JSON", self.tokens.parent / "ausente" / "tokens_count.json"), patch("funciones.urlopen", return_value=io.BytesIO(b"{}")), patch.object(funciones.logger, "error") as registrar:
            self.assertEqual(funciones.consultar_tokens_jev(), (False, {}))
        self.assertEqual(registrar.call_args.args[1], "FileNotFoundError")


if __name__ == "__main__":
    unittest.main()
