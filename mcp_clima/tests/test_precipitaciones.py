import json
import unittest
from unittest.mock import patch

import httpx
from mcp.shared.memory import create_connected_server_and_client_session

# Importar con URLs ficticias y sin abrir configuración local.
with patch("dotenv.load_dotenv", return_value=False), \
        patch.dict("os.environ", {
            "TEMPERATURA_URL": "https://clima.test/temperatura",
            "PRECIPITACIONES_URL": "https://clima.test/precipitaciones",
            "SENSACION_TERMICA_URL": "https://clima.test/sensacion",
            "PRESION_URL": "https://clima.test/presion",
        }, clear=True):
    from server import PRECIPITACIONES_URL, get_precipitaciones, mcp


def respuesta(tiempos, probabilidades):
    return httpx.Response(
        200,
        json={"hourly": {"time": tiempos, "precipitation_probability": probabilidades}},
        request=httpx.Request("GET", PRECIPITACIONES_URL),
    )


class PrecipitacionesTests(unittest.TestCase):
    def test_ultimos_valores_y_conversion_horaria(self):
        with patch("funciones.httpx.get", return_value=respuesta(
            ["2026-10-18T22:00", "2026-10-18T23:00"], [10, 80],
        )) as get:
            self.assertEqual(get_precipitaciones(), {"estado": "Ok", "respuesta": "2026-10-18 20:00, 80 % de lluvias"})
            get.assert_called_once_with(PRECIPITACIONES_URL, timeout=30.0)

    def test_cambio_de_fecha_y_porcentaje_cero(self):
        with patch("funciones.httpx.get", return_value=respuesta(["2026-01-01T01:00"], [0])):
            self.assertEqual(get_precipitaciones()["respuesta"], "2025-12-31 22:00, 0 % de lluvias")

    def test_datos_invalidos(self):
        for tiempos, probabilidades in [
            ([], []), (["2026-10-18T23:00"], []),
            (["2026-10-18T23:00"], [None]),
            (["2026-10-18T23:00"], [101]),
            (["2026-10-18T23:00"], [-1]),
        ]:
            with self.subTest(tiempos=tiempos, probabilidades=probabilidades):
                with patch("funciones.httpx.get", return_value=respuesta(tiempos, probabilidades)), self.assertLogs(level="ERROR"):
                    self.assertEqual(get_precipitaciones(), {"estado": "Error", "respuesta": "Error interno", "status_code": 500})

    def test_error_de_conexion(self):
        with patch("funciones.httpx.get", side_effect=httpx.TimeoutException("Tiempo agotado")), self.assertLogs(level="ERROR"):
            self.assertEqual(get_precipitaciones()["estado"], "Error")


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_descubrimiento_y_llamada(self):
        async with create_connected_server_and_client_session(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertIn("get_temperatura", tools)
            self.assertEqual(tools["get_precipitaciones"].inputSchema["properties"], {})
            with patch("funciones.httpx.get", return_value=respuesta(["2026-10-18T23:00"], [80])):
                result = await client.call_tool("get_precipitaciones", {})
            self.assertFalse(result.isError)
            self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": "2026-10-18 20:00, 80 % de lluvias"})


if __name__ == "__main__":
    unittest.main()
