"""Contrato de rutas después de retirar el chat original y MCP Autos."""

import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from fastapi import HTTPException

from fastapi.testclient import TestClient

# El arranque no debe abrir configuración local ni conectarse a SQLite.
with patch("dotenv.load_dotenv", return_value=False), \
        patch("sqlite3.connect", side_effect=AssertionError("No abrir SQLite al importar main")):
    from main import app

from schemas.chat_jev import RespuestaChatJev


class RutasTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(app)
        self.addCleanup(self.cliente.close)

    def test_swagger_publica_solo_chat_jev_y_administracion_sql(self):
        rutas = self.cliente.get("/openapi.json").json()["paths"]
        self.assertEqual(set(rutas), {
            "/chat/jev", "/consultas_sql/costos", "/consultas_sql/mcps",
            "/consultas_sql/mcps/{id_mcp}", "/consultas_sql/umbral",
        })
        self.assertIn("post", rutas["/chat/jev"])

    def test_endpoints_retirados_devuelven_404(self):
        for metodo, ruta in [("POST", "/chat"), ("GET", "/mejor_auto"), ("POST", "/es_mejor_auto")]:
            with self.subTest(ruta=ruta):
                respuesta = self.cliente.request(metodo, ruta, json={"mensaje": "hola", "auto": "ejemplo"})
                self.assertEqual(respuesta.status_code, 404)

    def test_chat_jev_conserva_contexto_y_contrato(self):
        salida = RespuestaChatJev(estado="Ok", respuesta="100 USD convertidos", herramientas=["convertir_divisas"], evaluaciones=[])
        with patch("routers.chat_jev.responder_chat_jev", new_callable=AsyncMock, return_value=salida) as responder:
            resultado = self.cliente.post("/chat/jev", json={"mensaje": "Convertí 100 USD a EUR", "contexto": ["Usuario: quiero una conversión"]})
        self.assertEqual(resultado.status_code, 200)
        self.assertEqual(resultado.json(), {"estado": "Ok", "respuesta": "100 USD convertidos", "herramientas": ["convertir_divisas"]})
        consulta = responder.call_args.args[0]
        self.assertEqual(consulta.contexto, ["Usuario: quiero una conversión"])

    def test_chat_jev_conserva_error_http_y_headers(self):
        for codigo in (502, 503, 504, 429):
            with self.subTest(codigo=codigo):
                error = HTTPException(status_code=codigo, detail="Fallo HTTP simulado", headers={"Retry-After": "10"})
                with patch("routers.chat_jev.responder_chat_jev", new_callable=AsyncMock, side_effect=error), self.assertLogs("routers.chat_jev", level="ERROR") as logs:
                    resultado = self.cliente.post("/chat/jev", json={"mensaje": "pedido"})
                self.assertEqual(resultado.status_code, codigo)
                self.assertEqual(resultado.json(), {"detail": "Fallo HTTP simulado"})
                self.assertEqual(resultado.headers["Retry-After"], "10")
                self.assertIn("Fallo HTTP simulado", "".join(logs.output))

    def test_chat_jev_excepcion_generica_devuelve_500_y_registra_e(self):
        with patch("routers.chat_jev.responder_chat_jev", new_callable=AsyncMock, side_effect=RuntimeError("Fallo interno simulado")), self.assertLogs("routers.chat_jev", level="ERROR") as logs:
            resultado = self.cliente.post("/chat/jev", json={"mensaje": "pedido"})
        self.assertEqual(resultado.status_code, 500)
        self.assertEqual(resultado.json(), {"detail": "Error interno al procesar la respuesta del chat."})
        self.assertIn("Fallo interno simulado", "".join(logs.output))
        self.assertNotIn("Fallo interno simulado", resultado.text)

    def test_chat_jev_error_al_construir_respuesta_tambien_se_captura(self):
        salida = SimpleNamespace(estado="Ok", respuesta="Texto simulado", herramientas=None)
        with patch("routers.chat_jev.responder_chat_jev", new_callable=AsyncMock, return_value=salida), self.assertLogs("routers.chat_jev", level="ERROR") as logs:
            resultado = self.cliente.post("/chat/jev", json={"mensaje": "pedido"})
        self.assertEqual(resultado.status_code, 500)
        self.assertIn("herramientas", "".join(logs.output))


if __name__ == "__main__":
    unittest.main()
