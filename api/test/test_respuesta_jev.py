"""Redacción final con LLM simulada, sin cargar .env ni consumir tokens."""

import ast
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException


class RespuestaJevTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        archivo = Path(__file__).resolve().parents[1] / "funciones/respuesta_jev_funciones.py"
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        arbol.body = [n for n in arbol.body if isinstance(n, ast.AsyncFunctionDef)]
        self.llm = SimpleNamespace(consultar_llm=AsyncMock(return_value=SimpleNamespace(output=[])),
                                   extraer_texto=Mock(return_value="Entiendo tu preferencia por el Falcon Futura."))
        self.c = {"os": os, "json": json, "httpx": httpx, "HTTPException": HTTPException, "llm": self.llm}
        exec(compile(arbol, str(archivo), "exec"), self.c)
        self.env = patch.dict(os.environ, {"API_KEY": "clave-ficticia"})
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_envia_resultado_y_contexto_sin_habilitar_mas_herramientas(self):
        resultado = {"content": [{"type": "text", "text": '{"respuesta":"No"}'}]}
        contexto = ["Usuario: cuál es el mejor auto", "Asistente: Fiat Pulse"]
        texto = await self.c["redactar_respuesta"]("no, es el falcon futura", contexto,
                                                   "es_mejor_auto", {"auto": "Falcon Futura"}, resultado)
        self.assertEqual(texto, self.llm.extraer_texto.return_value)
        llamada = self.llm.consultar_llm.call_args
        self.assertEqual(llamada.args[2], [])
        entrada = llamada.args[1]
        self.assertIn("Fiat Pulse", entrada[1]["content"])
        self.assertEqual(entrada[2]["content"], "no, es el falcon futura")
        self.assertEqual(entrada[-2]["name"], "es_mejor_auto")
        self.assertEqual(json.loads(entrada[-1]["output"]), resultado)
        self.assertEqual(entrada[-1]["call_id"], entrada[-2]["call_id"])

    async def test_clima_conserva_fecha_y_se_redacta_como_pronostico(self):
        resultado = {"structuredContent": {"estado": "Ok", "respuesta": "2026-10-18 20:00, 13.2 °C"}}
        await self.c["redactar_respuesta"]("que clima hace", [], "get_clima", {}, resultado)
        llamada = self.llm.consultar_llm.call_args
        entrada = llamada.args[1]
        instrucciones = entrada[0]["content"]
        self.assertIn("Incluí siempre la fecha", instrucciones)
        self.assertIn("no una observación de la temperatura actual", instrucciones)
        self.assertIn("GMT-3", instrucciones)
        self.assertEqual(json.loads(entrada[-1]["output"]), resultado)
        self.assertEqual(llamada.args[2], [])

    async def test_texto_vacio_no_se_presenta_como_respuesta(self):
        self.llm.extraer_texto.return_value = ""
        with self.assertRaises(HTTPException) as error:
            await self.c["redactar_respuesta"]("pedido", [], "consultar", {}, {})
        self.assertEqual(error.exception.status_code, 502)

    async def test_llamada_adicional_no_se_ejecuta(self):
        self.llm.consultar_llm.return_value.output = [{"type": "function_call", "name": "otra"}]
        with self.assertRaises(HTTPException):
            await self.c["redactar_respuesta"]("pedido", [], "consultar", {}, {})

    async def test_aclaracion_sin_herramientas_con_contexto(self):
        self.llm.extraer_texto.return_value = "¿Te referís a un auto o a un plato?"
        opciones = [{"capacidades": [{"descripcion": "Consulta el mejor plato", "parametros": {"type": "object"}}]}]
        texto = await self.c["redactar_aclaracion"]("el mejor", ["Usuario: quiero consultar algo"], opciones)
        self.assertEqual(texto, "¿Te referís a un auto o a un plato?")
        entrada = self.llm.consultar_llm.call_args.args[1]
        self.assertEqual(self.llm.consultar_llm.call_args.args[2], [])
        self.assertEqual(json.loads(entrada[1]["content"])["opciones"], opciones)
        self.assertIn("No menciones MCP", entrada[0]["content"])

    async def test_capacidades_usa_descripciones_y_parametros_sin_habilitar_tools(self):
        capacidades = [{"nombre": "mcp_nuevo", "herramientas": [{
            "name": "consultar_datos", "description": "Consultar datos nuevos",
            "inputSchema": {"type": "object", "properties": {"dato": {"type": "string"}}, "required": ["dato"]},
        }]}]
        self.llm.extraer_texto.return_value = "Puedo consultar datos nuevos si me indicás qué dato necesitás."
        texto = await self.c["redactar_capacidades"]("¿Qué podés hacer?", [], capacidades)
        self.assertEqual(texto, self.llm.extraer_texto.return_value)
        llamada = self.llm.consultar_llm.call_args
        self.assertEqual(llamada.args[2], [])
        datos = json.loads(llamada.args[1][-1]["content"])
        self.assertEqual(datos["capacidades_disponibles"], [{
            "descripcion": "Consultar datos nuevos", "parametros": capacidades[0]["herramientas"][0]["inputSchema"],
        }])
        self.assertNotIn("mcp_nuevo", llamada.args[1][-1]["content"])
        self.assertNotIn("consultar_datos", llamada.args[1][-1]["content"])

    async def test_capacidades_vacias_no_consulta_llm(self):
        for capacidades in [[], [{"nombre": "mcp_vacio", "herramientas": []}]]:
            with self.subTest(capacidades=capacidades):
                texto = await self.c["redactar_capacidades"]("¿Qué ofrecés?", [], capacidades)
                self.assertEqual(texto, "En este momento no tengo herramientas disponibles para ofrecerte consultas.")
        self.llm.consultar_llm.assert_not_awaited()

    async def test_capacidades_rechaza_texto_vacio_o_llamadas(self):
        capacidades = [{"nombre": "prueba", "herramientas": [{"name": "prueba", "description": "Consulta datos", "inputSchema": {}}]}]
        for output, texto in [([], ""), ([{"type": "function_call", "name": "prueba"}], "Respuesta")]:
            with self.subTest(output=output):
                self.llm.consultar_llm.return_value.output = output
                self.llm.extraer_texto.return_value = texto
                with self.assertRaises(HTTPException) as error:
                    await self.c["redactar_capacidades"]("¿Qué ofrecés?", [], capacidades)
                self.assertEqual(error.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
