"""Pruebas sin red, archivos .env, bases reales ni proveedores de LLM."""

from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import anyio
import httpx
from mcp.shared.memory import create_connected_server_and_client_session

import funciones
import server


def respuesta(datos=None, textos=(), error=False):
    return SimpleNamespace(
        isError=error, structuredContent=datos,
        content=[SimpleNamespace(type="text", text=texto) for texto in textos],
    )


class ClienteTests(unittest.IsolatedAsyncioTestCase):
    async def consultar(self, result=None, error=None):
        sesion = SimpleNamespace(initialize=AsyncMock(), call_tool=AsyncMock(return_value=result, side_effect=error))
        cerrado = []

        @asynccontextmanager
        async def transporte(*args, **kwargs):
            self.assertEqual(args, (funciones.FRANKFURTER_MCP_URL,))
            self.assertEqual(kwargs["timeout"], funciones.TIMEOUT)
            try:
                yield ("lectura", "escritura", None)
            finally:
                cerrado.append("transporte")

        @asynccontextmanager
        async def cliente(lectura, escritura):
            self.assertEqual((lectura, escritura), ("lectura", "escritura"))
            try:
                yield sesion
            finally:
                cerrado.append("sesion")

        with patch.object(funciones, "streamablehttp_client", transporte), patch.object(funciones, "ClientSession", cliente):
            resultado = await funciones.consultar_frankfurter("convert", {"amount": 100, "from": "USD", "to": "EUR"})
        sesion.initialize.assert_awaited_once_with()
        sesion.call_tool.assert_awaited_once_with("convert", {"amount": 100, "from": "USD", "to": "EUR"})
        self.assertEqual(cerrado, ["sesion", "transporte"])
        return resultado

    async def test_datos_estructurados(self):
        datos = {"amount": 90, "currency": "EUR", "date": "2024-06-03"}
        self.assertEqual(await self.consultar(respuesta(datos, textos=['otro contenido'])), (True, datos))

    async def test_json_y_texto(self):
        for textos, esperado in [(['{"EUR": 0.9}'], {"EUR": 0.9}), (["dato financiero"], "dato financiero"), (["uno", "dos"], "uno\ndos")]:
            with self.subTest(textos=textos):
                self.assertEqual(await self.consultar(respuesta(textos=textos)), (True, esperado))

    async def test_error_remoto_y_respuesta_vacia(self):
        for result in [respuesta(error=True, textos=['detalle externo']), respuesta(), respuesta(textos=['   '])]:
            self.assertEqual(await self.consultar(result), (False, {"status_code": 502}))

    async def test_errores_transporte_registran_excepcion(self):
        request = httpx.Request("POST", funciones.FRANKFURTER_MCP_URL)
        errores = [
            (httpx.ReadTimeout("fallo de transporte simulado"), 504),
            (httpx.ConnectError("fallo de transporte simulado"), 502),
            (httpx.HTTPStatusError("fallo de transporte simulado", request=request, response=httpx.Response(503, request=request)), 503),
            (RuntimeError("fallo de transporte simulado"), 502),
        ]
        for error, codigo in errores:
            with self.subTest(codigo=codigo), self.assertLogs(funciones.logger, level="ERROR") as logs:
                self.assertEqual(await self.consultar(error=error), (False, {"status_code": codigo}))
            self.assertIn("fallo de transporte simulado", "".join(logs.output))

    async def test_herramienta_desconocida_no_abre_transporte(self):
        with patch.object(funciones, "streamablehttp_client") as transporte:
            self.assertEqual(await funciones.consultar_frankfurter("otra", {}), (False, {"status_code": 400}))
        transporte.assert_not_called()

    async def test_plazo_total(self):
        @asynccontextmanager
        async def lento(*args, **kwargs):
            await anyio.sleep(1)
            yield (None, None, None)
        with patch.object(funciones, "TIMEOUT", 0.01), patch.object(funciones, "streamablehttp_client", lento):
            self.assertEqual(await funciones.consultar_frankfurter("get_rates", {}), (False, {"status_code": 504}))


class FinanzasTests(unittest.IsolatedAsyncioTestCase):
    async def test_conversion_y_traduccion_argumentos(self):
        datos = {"result": {"amount": 90, "currency": "EUR"}, "date": "2024-06-03"}
        with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock, return_value=(True, datos)) as consulta:
            result = await server.convertir_divisas(100, " usd ", "eur", "2024-06-03", "ecb")
        consulta.assert_awaited_once_with("convert", {"amount": 100, "from": "USD", "to": "EUR", "date": "2024-06-03", "provider": "ECB"})
        self.assertEqual(result["estado"], "Ok")
        self.assertEqual(result["respuesta"], datos)
        self.assertEqual(result["fuente"], "Frankfurter")

    async def test_tipos_varios_destinos_y_opcionales_omitidos(self):
        with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock, return_value=(True, [])) as consulta:
            await server.get_tipos_cambio("eur", " usd,gbp,USD ")
            consulta.assert_awaited_once_with("get_rates", {"base": "EUR", "quotes": "USD,GBP"})
            consulta.reset_mock()
            await server.get_tipos_cambio("EUR")
            consulta.assert_awaited_once_with("get_rates", {"base": "EUR"})

    async def test_catalogos_y_fallos_conservan_codigo(self):
        with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock, return_value=(False, {"status_code": 404})) as consulta:
            self.assertEqual((await server.get_monedas())["status_code"], 404)
            consulta.assert_awaited_once_with("list_currencies", {})
            consulta.reset_mock()
            self.assertEqual((await server.get_proveedores())["estado"], "Error")
            consulta.assert_awaited_once_with("list_providers", {})

    async def test_entradas_invalidas_no_consultan_servicio(self):
        with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock) as consulta:
            for importe in [0, -1, float("nan"), float("inf"), True]:
                self.assertEqual((await server.convertir_divisas(importe, "USD", "EUR"))["status_code"], 400)
            for fecha in ["2024-02-30", "20240603", "2024-6-03", ""]:
                self.assertEqual((await server.get_tipos_cambio("USD", fecha=fecha))["status_code"], 400)
            for moneda in ["", "US", "pesos", "123"]:
                self.assertEqual((await server.get_tipos_cambio(moneda))["status_code"], 400)
            self.assertEqual((await server.get_tipos_cambio("USD", "EUR,"))["status_code"], 400)
            self.assertEqual((await server.get_tipos_cambio("USD", proveedor=""))["status_code"], 400)
        consulta.assert_not_awaited()

    async def test_excepcion_interna(self):
        with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock, side_effect=RuntimeError("fallo interno simulado")), self.assertLogs(server.logger) as logs:
            self.assertEqual((await server.get_monedas())["status_code"], 500)
        self.assertIn("fallo interno simulado", "".join(logs.output))

    async def test_catalogo_mcp_y_ejecucion_en_memoria(self):
        async with create_connected_server_and_client_session(server.mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(set(tools), {"convertir_divisas", "get_tipos_cambio", "get_monedas", "get_proveedores"})
            self.assertEqual(set(tools["convertir_divisas"].inputSchema["required"]), {"importe", "moneda_origen", "moneda_destino"})
            self.assertEqual(tools["get_tipos_cambio"].inputSchema["required"], ["moneda_base"])
            self.assertEqual(tools["get_monedas"].inputSchema["properties"], {})
            with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock, return_value=(True, {"USD": "US Dollar"})) as consulta:
                result = await client.call_tool("get_monedas", {})
            consulta.assert_awaited_once_with("list_currencies", {})
            self.assertFalse(result.isError)
            self.assertEqual(json.loads(result.content[0].text)["estado"], "Ok")
            with patch.object(server, "consultar_frankfurter", new_callable=AsyncMock) as consulta:
                invalid = await client.call_tool("convertir_divisas", {"importe": -1, "moneda_origen": "USD", "moneda_destino": "EUR"})
            self.assertTrue(invalid.isError)
            consulta.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
