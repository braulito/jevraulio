import json
import unittest
from unittest.mock import patch

import httpx
from mcp.shared.memory import create_connected_server_and_client_session

from server import PRESION_URL, get_presion, mcp


def respuesta(tiempos, presiones, status=200):
    return httpx.Response(
        status,
        json={"hourly": {"time": tiempos, "surface_pressure": presiones}},
        request=httpx.Request("GET", PRESION_URL),
    )


class PresionTests(unittest.TestCase):
    def test_ultimo_valor_y_cambio_de_fecha(self):
        with patch("funciones.httpx.get", return_value=respuesta(
            ["2025-12-31T23:00", "2026-01-01T01:00"], [1000.0, 1013.2],
        )) as get:
            self.assertEqual(get_presion(), {"estado": "Ok", "respuesta": "2025-12-31 22:00, 1013.2 hPa"})
            get.assert_called_once_with(PRESION_URL, timeout=30.0)

    def test_datos_invalidos(self):
        for tiempos, presiones in [
            ([], []), (["2026-10-18T23:00"], []),
            (["2026-10-18T23:00"], [None]),
            (["2026-10-18T23:00"], [True]),
            (["2026-10-18T23:00"], [0]),
            (["2026-10-18T23:00"], [-1]),
            (["2026-10-18T23:00"], [float("nan")]),
        ]:
            with self.subTest(tiempos=tiempos, presiones=presiones):
                with patch("funciones.httpx.get") as get, self.assertLogs(level="ERROR"):
                    get.return_value.json.return_value = {"hourly": {"time": tiempos, "surface_pressure": presiones}}
                    self.assertEqual(get_presion(), {"estado": "Error", "respuesta": "Error interno", "status_code": 500})

    def test_errores_http_y_conexion(self):
        with patch("funciones.httpx.get", return_value=respuesta([], [], 503)), self.assertLogs(level="ERROR"):
            self.assertEqual(get_presion()["estado"], "Error")
        with patch("funciones.httpx.get", side_effect=httpx.TimeoutException("Tiempo agotado")), self.assertLogs(level="ERROR"):
            self.assertEqual(get_presion()["estado"], "Error")


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_descubrimiento_y_llamada(self):
        async with create_connected_server_and_client_session(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(tools["get_presion"].inputSchema["properties"], {})
            with patch("funciones.httpx.get", return_value=respuesta(["2026-10-18T23:00"], [1013.2])):
                result = await client.call_tool("get_presion", {})
            self.assertFalse(result.isError)
            self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": "2026-10-18 20:00, 1013.2 hPa"})


if __name__ == "__main__":
    unittest.main()
