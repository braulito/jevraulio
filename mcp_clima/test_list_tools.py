import json
import unittest
from unittest.mock import patch

import httpx
from mcp.shared.memory import create_connected_server_and_client_session

from server import CLIMA_URL, clima, mcp


def respuesta(tiempos, temperaturas, status=200):
    return httpx.Response(
        status,
        json={"hourly": {"time": tiempos, "temperature_2m": temperaturas}},
        request=httpx.Request("GET", CLIMA_URL),
    )


class ClimaTests(unittest.TestCase):
    def test_ultimos_valores_y_gmt_menos_tres(self):
        with patch("funciones.httpx.get", return_value=respuesta(
            ["2026-10-18T22:00", "2026-10-18T23:00"], [10.0, 21.5],
        )) as get:
            self.assertEqual(clima(), {"estado": "Ok", "respuesta": "2026-10-18 20:00, 21.5 °C"})
            get.assert_called_once_with(CLIMA_URL, timeout=30.0)

    def test_conversion_cambia_fecha(self):
        with patch("funciones.httpx.get", return_value=respuesta(["2026-01-01T01:00"], [-2.5])):
            self.assertEqual(clima()["respuesta"], "2025-12-31 22:00, -2.5 °C")

    def test_datos_invalidos(self):
        for tiempos, temperaturas in [
            ([], []), (["2026-10-18T23:00"], []),
            (["2026-10-18T23:00"], [None]), (["fecha invalida"], [20]),
        ]:
            with self.subTest(tiempos=tiempos, temperaturas=temperaturas):
                with patch("funciones.httpx.get", return_value=respuesta(tiempos, temperaturas)), self.assertLogs(level="ERROR"):
                    self.assertEqual(clima(), {"estado": "Error", "respuesta": "Error interno", "status_code": 500})

    def test_error_http_y_timeout(self):
        with patch("funciones.httpx.get", return_value=respuesta([], [], status=503)), self.assertLogs(level="ERROR"):
            self.assertEqual(clima()["estado"], "Error")
        with patch("funciones.httpx.get", side_effect=httpx.TimeoutException("Tiempo agotado")), self.assertLogs(level="ERROR"):
            self.assertEqual(clima()["estado"], "Error")


class ToolDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_and_call(self):
        async with create_connected_server_and_client_session(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(set(tools), {"clima", "mejor_clima"})
            self.assertEqual(tools["clima"].inputSchema["properties"], {})
            self.assertEqual(tools["clima"].inputSchema.get("required", []), [])
            with patch("funciones.httpx.get", return_value=respuesta(["2026-10-18T23:00"], [21.5])):
                result = await client.call_tool("clima", {})
            self.assertFalse(result.isError)
            self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": "2026-10-18 20:00, 21.5 °C"})
            result = await client.call_tool("mejor_clima", {})
            self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": "Templado"})


if __name__ == "__main__":
    unittest.main()
