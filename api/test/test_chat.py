"""Pruebas del chat sin solicitudes reales ni consumo de OpenAI."""

import json
import os
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager

import httpx
from fastapi.testclient import TestClient

from main import app
from funciones import billing
from funciones import chat_funciones as mcp
from funciones import openai_funciones as llm
from schemas.chat import RespuestaOpenAI
from mcp.types import Tool


AsyncClientReal = httpx.AsyncClient


def mensaje(texto):
    return {"status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": texto}]},
    ]}


def llamada(nombre="mejor_auto", argumentos="{}"):
    return {"status": "completed", "output": [
        {"type": "function_call", "name": nombre, "arguments": argumentos, "call_id": "call_1"},
    ]}


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.herramientas = [
            {"type": "function", "name": "mejor_auto", "description": "Mejor auto desde MCP",
             "parameters": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": False},
            {"type": "function", "name": "es_mejor_auto", "description": "Consultar auto desde MCP",
             "parameters": {"type": "object", "properties": {"auto": {"type": "string"}},
                            "required": ["auto"], "additionalProperties": False}, "strict": False},
        ]
        discovery = patch("funciones.chat_funciones.obtener_herramientas_mcp", new_callable=AsyncMock)
        self.discovery = discovery.start()
        self.discovery.return_value = self.herramientas
        self.addCleanup(discovery.stop)
        self.env = patch.dict(os.environ, {"API_KEY": "clave-simulada", "MODELO_OPENAI": "gpt-4.1-mini", "MAX_RONDAS": "3"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.console = patch("funciones.billing.registrar_consumo")
        self.billing_mock = self.console.start()
        self.addCleanup(self.console.stop)

    def simular_openai(self, respuestas):
        solicitudes = []

        def handler(request):
            solicitudes.append(json.loads(request.content))
            respuesta = respuestas.pop(0)
            if isinstance(respuesta, Exception):
                raise respuesta
            status, body = respuesta
            return httpx.Response(status, json=body)

        client = AsyncClientReal(transport=httpx.MockTransport(handler))
        mock = patch("funciones.openai_funciones.httpx.AsyncClient", return_value=client)
        mock.start()
        self.addCleanup(mock.stop)
        return solicitudes

    def test_swagger_registra_tres_rutas(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("post", schema["paths"]["/chat"])
        self.assertIn("get", schema["paths"]["/mejor_auto"])
        self.assertIn("post", schema["paths"]["/es_mejor_auto"])

    def test_mejor_auto_entrega_resultado_a_llm(self):
        solicitudes = self.simular_openai([
            (200, llamada()), (200, mensaje("Según el MCP, el mejor auto es Fiat Pulse.")),
        ])
        with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
            mcp.return_value = {"estado": "Ok", "respuesta": "Fiat Pulse"}
            response = self.client.post("/chat", json={"mensaje": "¿Cuál es el mejor auto?"})
            mcp.assert_awaited_once_with("mejor_auto", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["herramientas"], ["mejor_auto"])
        output = solicitudes[1]["input"][-1]
        self.assertEqual(output["type"], "function_call_output")
        self.assertEqual(output["call_id"], "call_1")
        self.assertEqual(json.loads(output["output"])["respuesta"], "Fiat Pulse")
        self.assertFalse(solicitudes[0]["store"])

    def test_es_mejor_auto_valida_y_envia_nombre(self):
        self.simular_openai([
            (200, llamada("es_mejor_auto", '{"auto":" Toyota Corolla "}')),
            (200, mensaje("No, según el MCP.")),
        ])
        with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
            mcp.return_value = {"estado": "Ok", "respuesta": "No"}
            response = self.client.post("/chat", json={"mensaje": "¿Toyota Corolla es el mejor?"})
            mcp.assert_awaited_once_with("es_mejor_auto", {"auto": " Toyota Corolla "})
        self.assertEqual(response.status_code, 200)

    def test_dato_faltante_no_llama_mcp(self):
        self.simular_openai([(200, mensaje("¿Qué auto querés consultar?"))])
        with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
            response = self.client.post("/chat", json={"mensaje": "¿Mi auto es el mejor?"})
            mcp.assert_not_awaited()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["herramientas"], [])

    def test_sin_clave(self):
        with patch.dict(os.environ, {"API_KEY": ""}):
            response = self.client.post("/chat", json={"mensaje": "Hola"})
        self.assertEqual(response.status_code, 503)

    def test_mensaje_vacio(self):
        response = self.client.post("/chat", json={"mensaje": "   "})
        self.assertEqual(response.status_code, 422)

    def test_herramienta_o_argumentos_invalidos(self):
        for nombre, argumentos in [
            ("desconocida", "{}"), ("mejor_auto", '{"auto":"Fiat"}'),
            ("es_mejor_auto", "{}"), ("es_mejor_auto", '{ "auto": 123 }'),
            ("es_mejor_auto", "no-json"),
        ]:
            with self.subTest(nombre=nombre, argumentos=argumentos):
                self.simular_openai([(200, llamada(nombre, argumentos))])
                with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
                    response = self.client.post("/chat", json={"mensaje": "Consultar auto"})
                    mcp.assert_not_awaited()
                self.assertEqual(response.status_code, 502)

    def test_openai_rechaza_credenciales_sin_exponer_detalles(self):
        self.simular_openai([(401, {"error": {"message": "detalle-privado"}})])
        response = self.client.post("/chat", json={"mensaje": "Hola"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("detalle-privado", response.text)
        self.assertNotIn("clave-simulada", response.text)

    def test_timeout_openai(self):
        self.simular_openai([httpx.ReadTimeout("timeout simulado")])
        response = self.client.post("/chat", json={"mensaje": "Hola"})
        self.assertEqual(response.status_code, 504)

    def test_limite_rondas(self):
        solicitudes = self.simular_openai([(200, llamada()) for _ in range(3)])
        with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
            mcp.return_value = {"estado": "Ok", "respuesta": "Fiat Pulse"}
            response = self.client.post("/chat", json={"mensaje": "Consultar"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(solicitudes), 3)

    def test_max_rondas_invalido(self):
        for valor in ("", "texto", "0", "-1", "1.5"):
            with self.subTest(valor=valor), patch.dict(os.environ, {"MAX_RONDAS": valor}):
                response = self.client.post("/chat", json={"mensaje": "Hola"})
                self.assertEqual(response.status_code, 503)

    def test_modelo_env_y_cache_estable(self):
        solicitudes = self.simular_openai([(200, llamada()), (200, mensaje("Fiat Pulse"))])
        with patch.dict(os.environ, {"MODELO_OPENAI": "gpt-4.1-mini-2025-04-14"}):
            with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
                mcp.return_value = {"estado": "Ok", "respuesta": "Fiat Pulse"}
                response = self.client.post("/chat", json={"mensaje": "Mejor auto"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(solicitudes[0]["model"], "gpt-4.1-mini-2025-04-14")
        self.assertEqual(solicitudes[0]["prompt_cache_key"], solicitudes[1]["prompt_cache_key"])
        self.assertNotEqual(llm.clave_cache_prompt("otro-modelo", self.herramientas), solicitudes[0]["prompt_cache_key"])

    def test_tokens_completos_y_costo_sin_doble_conteo(self):
        body = mensaje("respuesta privada")
        body["model"] = "gpt-4.1-mini-2025-04-14"
        body["usage"] = {
            "input_tokens": 2000, "input_tokens_details": {"cached_tokens": 1000},
            "output_tokens": 100, "output_tokens_details": {"reasoning_tokens": 40},
            "total_tokens": 2100,
        }
        self.simular_openai([(200, body)])
        response = self.client.post("/chat", json={"mensaje": "mensaje privado"})
        self.assertEqual(response.status_code, 200)
        self.billing_mock.assert_called_once()
        resumen = self.billing_mock.call_args.args[0]
        impreso = json.dumps(resumen)
        self.assertEqual(set(resumen), {"tokens", "costo_estimado_usd", "metodo", "herramientas"})
        self.assertEqual(resumen["metodo"], "respuesta")
        self.assertEqual(resumen["tokens"], body["usage"])
        self.assertAlmostEqual(resumen["costo_estimado_usd"], 0.00066)
        self.assertNotIn("respuesta privada", impreso)
        self.assertNotIn("mensaje privado", impreso)
        self.assertNotIn("clave-simulada", impreso)

    def test_costo_sin_cache_y_modelo_desconocido(self):
        usage = {"input_tokens": 1000, "output_tokens": 100}
        self.assertAlmostEqual(billing.costo_uso(usage, "gpt-4.1-mini"), 0.00056)
        self.assertIsNone(billing.costo_uso(usage, "modelo-desconocido"))
        self.assertIsNone(billing.costo_uso(None, "gpt-4.1-mini"))

    def test_luna_usa_modelo_env_y_razonamiento_none(self):
        solicitudes = self.simular_openai([(200, mensaje("Hola"))])
        with patch.dict(os.environ, {"MODELO_OPENAI": "gpt-6-luna"}):
            response = self.client.post("/chat", json={"mensaje": "Hola"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(solicitudes[0]["model"], "gpt-6-luna")
        self.assertEqual(solicitudes[0]["reasoning"], {"effort": "none"})
        self.assertEqual(solicitudes[0]["service_tier"], "default")

    def test_luna_costo_lectura_y_escritura_cache(self):
        usage = {
            "input_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 1000, "cache_write_tokens": 500},
            "output_tokens": 100,
            "output_tokens_details": {"reasoning_tokens": 40},
        }
        self.assertAlmostEqual(billing.costo_uso(usage, "gpt-6-luna"), 0.0001725)
        self.assertAlmostEqual(billing.costo_uso({"input_tokens": 1000, "output_tokens": 100}, "gpt-6-luna"), 0.00015)

    def test_luna_tarifa_contexto_largo(self):
        self.assertAlmostEqual(billing.costo_uso({"input_tokens": 300000, "output_tokens": 100}, "gpt-6-luna"), 0.060075)

    def test_nueva_herramienta_y_resultado_sin_formato_autos(self):
        nueva = {
            "type": "function", "name": "sumar", "description": "Suma publicada solo en MCP",
            "parameters": {"type": "object", "properties": {
                "numeros": {"type": "array", "items": {"type": "number"}},
                "redondear": {"type": "boolean", "default": False},
            }, "required": ["numeros"]}, "strict": False,
        }
        self.discovery.return_value = [nueva]
        solicitudes = self.simular_openai([
            (200, llamada("sumar", '{"numeros":[2,3]}')), (200, mensaje("El total es 5.")),
        ])
        with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
            mcp.return_value = {"structuredContent": {"total": 5}, "content": [], "isError": False}
            response = self.client.post("/chat", json={"mensaje": "Sumá 2 y 3"})
            mcp.assert_awaited_once_with("sumar", {"numeros": [2, 3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(solicitudes[0]["tools"], [nueva])
        self.assertEqual(response.json()["herramientas"], ["sumar"])
        self.assertEqual(json.loads(solicitudes[1]["input"][-1]["output"])["structuredContent"], {"total": 5})

    def test_esquema_anidado_valida_tipos(self):
        self.discovery.return_value = [{
            "name": "sumar", "parameters": {"type": "object", "properties": {
                "numeros": {"type": "array", "items": {"type": "number"}},
            }, "required": ["numeros"]},
        }]
        self.simular_openai([(200, llamada("sumar", '{"numeros":["texto"]}'))])
        with patch("funciones.chat_funciones.llamar_herramienta_mcp", new_callable=AsyncMock) as mcp:
            response = self.client.post("/chat", json={"mensaje": "Sumar"})
            mcp.assert_not_awaited()
        self.assertEqual(response.status_code, 502)

    def test_cambio_catalogo_cambia_cache(self):
        nuevas = deepcopy(self.herramientas)
        nuevas[0]["description"] = "Descripción cambiada en el MCP"
        self.assertNotEqual(llm.clave_cache_prompt("gpt-4.1-mini", self.herramientas),
                            llm.clave_cache_prompt("gpt-4.1-mini", nuevas))

    def test_catalogo_se_consulta_en_cada_peticion(self):
        with patch("funciones.openai_funciones.consultar_llm", new_callable=AsyncMock) as llm:
            llm.return_value = RespuestaOpenAI.model_validate(mensaje("Hola"))
            self.assertEqual(self.client.post("/chat", json={"mensaje": "Hola"}).status_code, 200)
            self.assertEqual(self.client.post("/chat", json={"mensaje": "Hola"}).status_code, 200)
        self.assertEqual(self.discovery.await_count, 2)


class BillingTests(unittest.TestCase):
    def setUp(self):
        guardar = patch("funciones.billing.guardar_billing")
        self.guardar_mock = guardar.start()
        self.addCleanup(guardar.stop)

    def test_registra_tokens_y_costo(self):
        datos = {
            "tokens": {"input_tokens": 257, "output_tokens": 15, "total_tokens": 272},
            "costo_estimado_usd": 3.32e-05,
            "metodo": "tool_call", "herramientas": [],
        }
        with self.assertLogs(billing.logger, level="INFO") as logs:
            billing.registrar_consumo(datos)
        self.assertEqual(logs.records[0].getMessage(), 'TOKENS TOTALES: 272, COSTO: USD 0.0000332000, METODO: tool_call, HERRAMIENTAS: ""')
        self.assertEqual(len(logs.records), 1)
        self.guardar_mock.assert_called_once_with(datos)

    def test_datos_no_disponibles_no_inventa_consumo(self):
        with self.assertLogs(billing.logger, level="INFO") as logs:
            billing.registrar_consumo({"tokens": None, "costo_estimado_usd": None})
        self.assertEqual(logs.records[0].getMessage(), "TOKENS TOTALES: no disponible, COSTO: no disponible, METODO: no disponible, HERRAMIENTAS: ninguna")

    def test_identifica_tool_call_y_respuesta_con_mcp(self):
        tool = {"type": "function_call", "name": "herramienta_nueva", "call_id": "call_1"}
        self.assertEqual(billing.identificar_metodo([tool], []), ("tool_call", []))
        entrada = [tool, {"type": "function_call_output", "call_id": "call_1", "output": "resultado"}]
        self.assertEqual(billing.identificar_metodo(mensaje("Respuesta")["output"], entrada), ("mcp", ["herramienta_nueva"]))


class DescubrimientoTests(unittest.IsolatedAsyncioTestCase):
    async def test_paginacion_descripciones_y_opcionales(self):
        session = AsyncMock()
        schema = {"type": "object", "properties": {"cantidad": {"type": "integer", "default": 1}}}
        session.list_tools.side_effect = [
            SimpleNamespace(tools=[Tool(name="zeta", description="Descripción MCP", inputSchema=schema)], nextCursor="pagina2"),
            SimpleNamespace(tools=[Tool(name="alfa", inputSchema={"type": "object", "properties": {}})], nextCursor=None),
        ]

        @asynccontextmanager
        async def transporte(*args, **kwargs):
            yield None, None, None

        # Este caso usa la función real de descubrimiento y una sesión MCP simulada.
        with patch("funciones.chat_funciones.streamable_http_client", transporte):
            with patch("funciones.chat_funciones.ClientSession") as factory:
                factory.return_value.__aenter__.return_value = session
                tools = await mcp.obtener_herramientas_mcp()
        self.assertEqual([tool["name"] for tool in tools], ["alfa", "zeta"])
        self.assertEqual(tools[1]["description"], "Descripción MCP")
        self.assertEqual(tools[1]["parameters"], schema)
        self.assertFalse(tools[1]["strict"])
        session.list_tools.assert_any_await(cursor=None)
        session.list_tools.assert_any_await(cursor="pagina2")


if __name__ == "__main__":
    unittest.main()
