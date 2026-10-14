"""Páginas administrativas con API simulada, sin .env ni acceso SQLite."""

import ast
import os
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from app import crear_app


class PaginasApiTests(unittest.TestCase):
    def setUp(self):
        pila = ExitStack()
        self.addCleanup(pila.close)
        pila.enter_context(patch.dict(os.environ, {"MAX_CONTEXTO": "20", "PAGINA_SIZE": "10", "API_URL": "http://api-ficticia.invalid/chat/jev"}, clear=True))
        pila.enter_context(patch("dotenv.load_dotenv", side_effect=AssertionError("No cargar .env")))
        pila.enter_context(patch("sqlite3.connect", side_effect=AssertionError("Pagina no debe consultar SQLite")))
        self.registro = {"id": 7, "nombre": "mcp_clima", "url": "http://localhost:8005/mcp", "habilitado": 0}
        self.costos = {
            "registros": [], "costo_jev": 1, "costo_openai": 2,
            "tokens_jev": 100, "tokens_openai": 200, "total_registros": 0,
            "pagina": 1, "total_paginas": 1, "desde": 0, "hasta": 0,
            "mostrar_jev": True, "mostrar_openai": True,
        }
        salidas = {
            "consultar_costos_api": self.costos, "consultar_mcps_api": [self.registro],
            "consultar_mcp_api": self.registro, "agregar_mcp_api": self.registro,
            "guardar_estado_mcp_api": dict(self.registro, habilitado=1),
            "eliminar_mcp_api": {"id": 7, "eliminado": True},
            "consultar_umbral_api": {"id": 1, "valor": 0.85},
            "guardar_umbral_api": {"id": 1, "valor": 0.725},
        }
        self.api = {nombre: pila.enter_context(patch("funciones." + nombre, return_value=(True, datos))) for nombre, datos in salidas.items()}
        self.app = crear_app(cargar_entorno=False)
        self.app.config["TESTING"] = True
        self.cliente = self.app.test_client()

    def token(self, pagina="mcps"):
        self.cliente.get("/" + pagina)
        with self.cliente.session_transaction() as sesion:
            return sesion["csrf_" + pagina]

    def assertModal(self, respuesta):
        self.assertEqual(respuesta.status_code, 503)
        html = respuesta.get_data(as_text=True)
        self.assertIn('id="modal-error"', html)
        self.assertIn("js/modal_error.js", html)

    def test_costos_envia_pagina_size_y_filtros_a_api(self):
        respuesta = self.cliente.get("/costos?pagina=2&filtros=1&mostrar_jev=1")
        self.assertEqual(respuesta.status_code, 200)
        self.api["consultar_costos_api"].assert_called_once_with(pagina=2, pagina_size=10, mostrar_jev=True, mostrar_openai=False)
        self.assertNotIn('id="modal-error"', respuesta.get_data(as_text=True))

    def test_umbral_lee_porcentaje_y_guarda_decimal(self):
        respuesta = self.cliente.get("/umbral")
        self.assertIn('value="85"', respuesta.get_data(as_text=True))
        token = self.token("umbral")
        respuesta = self.cliente.post("/umbral", data={"porcentaje": "72.5", "csrf_token": token})
        self.assertEqual(respuesta.status_code, 302)
        self.api["guardar_umbral_api"].assert_called_once_with(0.725)

    def test_mcps_listado_estado_alta_y_borrado(self):
        token = self.token()
        respuesta = self.cliente.post("/mcps", data={"id_mcp": "7", "habilitado": "1", "csrf_token": token})
        self.assertEqual(respuesta.status_code, 302)
        self.api["guardar_estado_mcp_api"].assert_called_once_with(7, 1)
        respuesta = self.cliente.post("/mcps/agregar", data={"nombre": "mcp_clima", "url": "http://localhost:8005/mcp", "csrf_token": token})
        self.assertEqual(respuesta.status_code, 302)
        self.api["agregar_mcp_api"].assert_called_once_with("mcp_clima", "http://localhost:8005/mcp")
        self.assertEqual(self.cliente.get("/mcps/7/borrar").status_code, 200)
        self.api["eliminar_mcp_api"].assert_not_called()
        respuesta = self.cliente.post("/mcps/7/borrar", data={"csrf_token": token})
        self.assertEqual(respuesta.status_code, 302)
        self.api["eliminar_mcp_api"].assert_called_once_with(7)

    def test_cada_lectura_fallida_abre_modal(self):
        casos = [("consultar_costos_api", "/costos"), ("consultar_umbral_api", "/umbral"), ("consultar_mcps_api", "/mcps"), ("consultar_mcp_api", "/mcps/7/borrar")]
        for nombre, ruta in casos:
            with self.subTest(nombre=nombre):
                original = self.api[nombre].return_value
                self.api[nombre].return_value = (False, {})
                self.assertModal(self.cliente.get(ruta))
                self.api[nombre].return_value = original

    def test_listados_404_muestran_ausencia_de_datos_sin_modal(self):
        for nombre, rutas in (
            ("consultar_costos_api", ("/costos", "/costos.html")),
            ("consultar_mcps_api", ("/mcps", "/mcps.html")),
        ):
            self.api[nombre].return_value = (False, {"status_code": 404})
            for ruta in rutas:
                with self.subTest(ruta=ruta):
                    respuesta = self.cliente.get(ruta)
                    self.assertEqual(respuesta.status_code, 200)
                    html = respuesta.get_data(as_text=True)
                    self.assertIn("No hay información disponible.", html)
                    self.assertNotIn('id="modal-error"', html)
                    self.assertNotIn("<table>", html)
                    self.assertNotIn("aviso-error", html)
                    if nombre == "consultar_mcps_api":
                        self.assertIn('action="/mcps/agregar"', html)
                    else:
                        self.assertNotIn("Costo OpenAI:", html)
                        self.assertNotIn("Costo JEV:", html)

    def test_404_fuera_de_listados_sigue_abriendo_modal(self):
        self.api["consultar_umbral_api"].return_value = (False, {"status_code": 404})
        self.assertModal(self.cliente.get("/umbral"))
        token = self.token()
        self.api["guardar_estado_mcp_api"].return_value = (False, {"status_code": 404})
        self.api["consultar_mcps_api"].return_value = (False, {"status_code": 404})
        respuesta = self.cliente.post("/mcps", data={"id_mcp": "7", "habilitado": "1", "csrf_token": token})
        self.assertModal(respuesta)
        self.assertIn("No hay información disponible.", respuesta.get_data(as_text=True))

    def test_listado_404_no_oculta_error_al_agregar_mcp(self):
        token = self.token()
        self.api["agregar_mcp_api"].return_value = (False, {"status_code": 409})
        self.api["consultar_mcps_api"].return_value = (False, {"status_code": 404})
        respuesta = self.cliente.post("/mcps/agregar", data={"nombre": "prueba", "url": "http://localhost/mcp", "csrf_token": token})
        self.assertModal(respuesta)
        html = respuesta.get_data(as_text=True)
        self.assertIn("No hay información disponible.", html)
        self.assertIn('value="prueba"', html)

    def test_cada_escritura_fallida_abre_modal(self):
        token_mcps = self.token()
        token_umbral = self.token("umbral")
        casos = [
            ("guardar_umbral_api", "/umbral", {"porcentaje": "80", "csrf_token": token_umbral}),
            ("guardar_estado_mcp_api", "/mcps", {"id_mcp": "7", "habilitado": "1", "csrf_token": token_mcps}),
            ("agregar_mcp_api", "/mcps/agregar", {"nombre": "prueba", "url": "http://localhost/mcp", "csrf_token": token_mcps}),
            ("eliminar_mcp_api", "/mcps/7/borrar", {"csrf_token": token_mcps}),
        ]
        for nombre, ruta, datos in casos:
            with self.subTest(nombre=nombre):
                original = self.api[nombre].return_value
                self.api[nombre].return_value = (False, {})
                self.assertModal(self.cliente.post(ruta, data=datos))
                self.api[nombre].return_value = original

    def test_respuestas_incompletas_tambien_abren_modal(self):
        for salida in ({}, [], {**self.costos, "registros": [{}]}, {**self.costos, "pagina": "texto"}):
            self.api["consultar_costos_api"].return_value = (True, salida)
            self.assertModal(self.cliente.get("/costos"))
        self.api["consultar_umbral_api"].return_value = (True, {"id": 1, "valor": None})
        self.assertModal(self.cliente.get("/umbral"))
        self.api["consultar_mcps_api"].return_value = (True, [{}])
        self.assertModal(self.cliente.get("/mcps"))

    def test_excepcion_de_cliente_y_fallo_durante_recuperacion_abren_modal(self):
        self.api["consultar_costos_api"].side_effect = TimeoutError()
        self.assertModal(self.cliente.get("/costos"))
        self.api["consultar_mcp_api"].return_value = (False, {})
        self.assertModal(self.cliente.post("/mcps/7/borrar", data={"csrf_token": "invalido"}))

    def test_respuesta_de_escritura_incompleta_o_borrado_no_confirmado_abre_modal(self):
        token_mcps = self.token()
        token_umbral = self.token("umbral")
        casos = [
            ("guardar_umbral_api", "/umbral", {"porcentaje": "80", "csrf_token": token_umbral}, {}),
            ("guardar_estado_mcp_api", "/mcps", {"id_mcp": "7", "habilitado": "1", "csrf_token": token_mcps}, {}),
            ("agregar_mcp_api", "/mcps/agregar", {"nombre": "prueba", "url": "http://localhost/mcp", "csrf_token": token_mcps}, {}),
            ("eliminar_mcp_api", "/mcps/7/borrar", {"csrf_token": token_mcps}, {"id": 7, "eliminado": False}),
        ]
        for nombre, ruta, datos, salida in casos:
            self.api[nombre].return_value = (True, salida)
            self.assertModal(self.cliente.post(ruta, data=datos))

    def test_validacion_local_no_envia_escrituras(self):
        token = self.token("umbral")
        self.assertEqual(self.cliente.post("/umbral", data={"porcentaje": "101", "csrf_token": token}).status_code, 400)
        self.api["guardar_umbral_api"].assert_not_called()
        self.assertEqual(self.cliente.post("/mcps", data={"id_mcp": "7", "habilitado": "1"}).status_code, 400)
        self.api["guardar_estado_mcp_api"].assert_not_called()

    def test_aliases_y_chat_no_tienen_modal_en_exito(self):
        for ruta in ("/costos.html", "/umbral.html", "/mcps.html", "/", "/index.html"):
            respuesta = self.cliente.get(ruta)
            self.assertEqual(respuesta.status_code, 200)
            self.assertNotIn('id="modal-error"', respuesta.get_data(as_text=True))

    def test_pagina_no_importa_bases(self):
        carpeta = Path(__file__).resolve().parents[1]
        actual = ast.parse((carpeta / "app.py").read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(nodo, ast.ImportFrom) and nodo.module == "bases" for nodo in ast.walk(actual)))


if __name__ == "__main__":
    unittest.main()
