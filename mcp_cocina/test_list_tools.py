import json
import unittest

from mcp.shared.memory import create_connected_server_and_client_session

from server import mcp


class ToolDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_and_calls(self):
        async with create_connected_server_and_client_session(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

            self.assertEqual(set(tools), {"mejor_plato", "es_mejor_plato", "compara_platos"})
            mejor = tools["mejor_plato"]
            self.assertEqual(mejor.description, "Consulta cuál es el mejor plato según el MCP Cocina")
            self.assertEqual(mejor.inputSchema["type"], "object")
            self.assertEqual(mejor.inputSchema["properties"], {})
            self.assertEqual(mejor.inputSchema.get("required", []), [])

            es_mejor = tools["es_mejor_plato"]
            self.assertEqual(es_mejor.description, "Consulta si el plato indicado es el mejor según el MCP Cocina")
            self.assertEqual(es_mejor.inputSchema["type"], "object")
            self.assertEqual(set(es_mejor.inputSchema["properties"]), {"plato"})
            self.assertEqual(es_mejor.inputSchema["properties"]["plato"]["type"], "string")
            self.assertEqual(es_mejor.inputSchema["properties"]["plato"]["description"], "Nombre del plato a consultar")
            self.assertEqual(es_mejor.inputSchema["required"], ["plato"])

            comparar = tools["compara_platos"]
            self.assertIn("Compara dos platos", comparar.description)
            self.assertEqual(set(comparar.inputSchema["properties"]), {"plato_a", "plato_b"})
            self.assertEqual(set(comparar.inputSchema["required"]), {"plato_a", "plato_b"})

            cases = [
                ("mejor_plato", {}, "Milanesas"),
                ("es_mejor_plato", {"plato": "Milanesas"}, "Si"),
                ("es_mejor_plato", {"plato": "  MILANESAS  "}, "Si"),
                ("es_mejor_plato", {"plato": "Otro plato"}, "No"),
            ]
            for name, arguments, expected in cases:
                result = await client.call_tool(name, arguments)
                self.assertFalse(result.isError)
                self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": expected})

            missing_argument = await client.call_tool("es_mejor_plato", {})
            self.assertTrue(missing_argument.isError)

    async def test_compara_platos(self):
        async with create_connected_server_and_client_session(mcp) as client:
            ganador = "Entre esos dos platos, el mejor según el MCP Cocina es Milanesas."
            casos = [
                ("flan", "milanesas", ganador),
                ("milanesas", "flan", ganador),
                ("  MILANESA  ", "flan", ganador),
                (" Flan ", "FLAN", "Empate: ambos nombres corresponden al mismo plato."),
                ("milanesa", "milanesas", "Empate: ambos nombres corresponden al mismo plato."),
                ("flan", "pizza", "El MCP Cocina no tiene un criterio para elegir el mejor entre esos dos platos."),
            ]
            for plato_a, plato_b, esperado in casos:
                with self.subTest(plato_a=plato_a, plato_b=plato_b):
                    resultado = await client.call_tool("compara_platos", {"plato_a": plato_a, "plato_b": plato_b})
                    self.assertFalse(resultado.isError)
                    self.assertEqual(json.loads(resultado.content[0].text), {"estado": "Ok", "respuesta": esperado})
            for argumentos in [{}, {"plato_a": "flan"}, {"plato_a": "", "plato_b": "flan"}]:
                resultado = await client.call_tool("compara_platos", argumentos)
                self.assertTrue(resultado.isError)
            resultado = await client.call_tool("compara_platos", {"plato_a": "   ", "plato_b": "flan"})
            self.assertEqual(json.loads(resultado.content[0].text)["status_code"], 400)

    async def test_decorated_tool_is_discovered_automatically(self):
        async with create_connected_server_and_client_session(mcp) as client:
            before = {tool.name for tool in (await client.list_tools()).tools}

            @mcp.tool()
            def herramienta_temporal(numero: int) -> dict:
                """Herramienta temporal para verificar el descubrimiento automático."""
                return {"numero": numero}

            try:
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                self.assertEqual(set(tools), before | {"herramienta_temporal"})
                added = tools["herramienta_temporal"]
                self.assertEqual(added.description, herramienta_temporal.__doc__)
                self.assertEqual(added.inputSchema["properties"]["numero"]["type"], "integer")
                self.assertEqual(added.inputSchema["required"], ["numero"])
                result = await client.call_tool("herramienta_temporal", {"numero": 3})
                self.assertFalse(result.isError)
                self.assertEqual(json.loads(result.content[0].text), {"numero": 3})
            finally:
                mcp.remove_tool("herramienta_temporal")


if __name__ == "__main__":
    unittest.main()
