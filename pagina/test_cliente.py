"""Pruebas de la página con respuestas simuladas y sin cargar .env."""

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app import crear_app


class ClienteChatTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"API_URL": "http://api.test/chat/jev"}, clear=True):
            self.app = crear_app(cargar_entorno=False)

    def test_hola_sin_coincidencias_se_muestra(self):
        texto = "Por ahora no puedo ayudarte con ese pedido. ¿Querés probar con otra consulta?"
        respuesta = io.StringIO(json.dumps({"estado": "Ok", "respuesta": texto, "herramientas": []}))
        respuesta.status = 200
        with patch("cliente_api.urlopen", return_value=respuesta) as consultar:
            resultado = self.app.test_client().post("/chat", json={"mensaje": "hola"})
        self.assertEqual(resultado.status_code, 200)
        self.assertEqual(resultado.json, {"respuesta": texto})
        peticion = consultar.call_args.args[0]
        self.assertEqual(peticion.full_url, "http://api.test/chat/jev")
        self.assertEqual(json.loads(peticion.data), {"mensaje": "hola"})
        self.assertEqual(consultar.call_args.kwargs["timeout"], 200)

    def test_fallo_api_registra_codigo_http_sin_datos_sensibles(self):
        error = HTTPError("http://api.test/chat/jev", 503, "fallo simulado", {}, None)
        with patch("cliente_api.urlopen", side_effect=error), patch.object(self.app.logger, "error") as registrar:
            resultado = self.app.test_client().post("/chat", json={"mensaje": "hola"})
        self.assertEqual(resultado.status_code, 502)
        registrar.assert_called_once_with(
            "No se pudo consultar el chat de la API. Tipo: %s; HTTP: %s", "HTTPError", 503,
        )

    def test_confirmacion_con_contexto_llega_a_api(self):
        contexto = ["Usuario: el mejor es el falco", "Asistente: ¿Querés que consulte si el Falco es el mejor auto?"]
        respuesta = io.StringIO(json.dumps({"estado": "Ok", "respuesta": "No", "herramientas": ["es_mejor_auto"]}))
        respuesta.status = 200
        with patch("cliente_api.urlopen", return_value=respuesta) as consultar:
            resultado = self.app.test_client().post("/chat", json={"mensaje": "si", "contexto": contexto})
        self.assertEqual(resultado.status_code, 200)
        self.assertEqual(json.loads(consultar.call_args.args[0].data), {"mensaje": "si", "contexto": contexto})

    def test_contexto_invalido_no_llama_api(self):
        with patch("cliente_api.urlopen") as consultar:
            resultado = self.app.test_client().post("/chat", json={"mensaje": "si", "contexto": "Falco"})
        self.assertEqual(resultado.status_code, 400)
        consultar.assert_not_called()

    def test_limite_configurado_se_entrega_al_navegador_y_se_valida(self):
        with patch.dict(os.environ, {"MAX_CONTEXTO": "3", "API_URL": "http://api.test/chat/jev"}, clear=True):
            app = crear_app(cargar_entorno=False)
        cliente = app.test_client()
        self.assertIn('data-max-contexto="3"', cliente.get("/").get_data(as_text=True))
        with patch("app.consultar_chat", return_value="respuesta") as consultar:
            self.assertEqual(cliente.post("/chat", json={"mensaje": "sí", "contexto": ["anterior"] * 3}).status_code, 200)
            self.assertEqual(cliente.post("/chat", json={"mensaje": "sí", "contexto": ["anterior"] * 4}).status_code, 400)
        consultar.assert_called_once()

    def test_limite_invalido_no_arranca(self):
        for valor in ("0", "-1", "abc"):
            with self.subTest(valor=valor), patch.dict(os.environ, {"MAX_CONTEXTO": valor}, clear=True):
                with self.assertRaisesRegex(ValueError, "MAX_CONTEXTO debe ser un entero mayor que cero"):
                    crear_app(cargar_entorno=False)


if __name__ == "__main__":
    unittest.main()
