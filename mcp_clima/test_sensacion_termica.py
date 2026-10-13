import json
import unittest
from unittest.mock import patch

import httpx
from mcp.shared.memory import create_connected_server_and_client_session

from server import SENSACION_TERMICA_URL, get_sensacion_termica, mcp


def respuesta(tiempos, sensaciones):
    return httpx.Response(
        200,
        json={"hourly": {"time": tiempos, "apparent_temperature": sensaciones}},
        request=httpx.Request("GET", SENSACION_TERMICA_URL),
    )


class SensacionTermicaTests(unittest.TestCase):
    def test_ultimo_valor_y_cambio_de_fecha(self):
        with patch("funciones.httpx.get", return_value=respuesta(
            ["2025-12-31T23:00", "2026-01-01T01:00"], [12.5, -2.3],
        )) as get:
            self.assertEqual(get_sensacion_termica(), {"estado": "Ok", "respuesta": "2025-12-31 22:00, -2.3 °C"})
            get.assert_called_once_with(SENSACION_TERMICA_URL, timeout=30.0)

    def test_datos_invalidos(self):
        for tiempos, sensaciones in [
            ([], []), (["2026-10-18T23:00"], []),
            (["2026-10-18T23:00"], [None]),
            (["2026-10-18T23:00"], [True]),
            (["2026-10-18T23:00"], [float("nan")]),
        ]:
            with self.subTest(tiempos=tiempos, sensaciones=sensaciones):
                # Los no finitos se prueban como JSON ya decodificado.
                with patch("funciones.httpx.get") as get, self.assertLogs(level="ERROR"):
                    get.return_value.json.return_value = {"hourly": {"time": tiempos, "apparent_temperature": sensaciones}}
                    self.assertEqual(get_sensacion_termica(), {"estado": "Error", "respuesta": "Error interno", "status_code": 500})

    def test_error_de_conexion(self):
        with patch("funciones.httpx.get", side_effect=httpx.TimeoutException("Tiempo agotado")), self.assertLogs(level="ERROR"):
            self.assertEqual(get_sensacion_termica()["estado"], "Error")


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_descubrimiento_y_llamada(self):
        async with create_connected_server_and_client_session(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(tools["get_sensacion_termica"].inputSchema["properties"], {})
            with patch("funciones.httpx.get", return_value=respuesta(["2026-10-18T23:00"], [10.5])):
                result = await client.call_tool("get_sensacion_termica", {})
            self.assertFalse(result.isError)
            self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": "2026-10-18 20:00, 10.5 °C"})


if __name__ == "__main__":
    unittest.main()
