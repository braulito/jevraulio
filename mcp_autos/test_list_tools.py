import json
import unittest

from mcp.shared.memory import create_connected_server_and_client_session

from server import mcp


class ToolDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_and_calls(self):
        async with create_connected_server_and_client_session(mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

            self.assertEqual(set(tools), {"mejor_auto", "es_mejor_auto"})
            mejor = tools["mejor_auto"]
            self.assertEqual(mejor.description, "Consulta cuál es el mejor auto según el MCP Autos")
            self.assertEqual(mejor.inputSchema["type"], "object")
            self.assertEqual(mejor.inputSchema["properties"], {})
            self.assertEqual(mejor.inputSchema.get("required", []), [])

            es_mejor = tools["es_mejor_auto"]
            self.assertEqual(es_mejor.description, "Consulta si el auto indicado es el mejor según el MCP Autos")
            self.assertEqual(es_mejor.inputSchema["type"], "object")
            self.assertEqual(set(es_mejor.inputSchema["properties"]), {"auto"})
            self.assertEqual(es_mejor.inputSchema["properties"]["auto"]["type"], "string")
            self.assertEqual(es_mejor.inputSchema["properties"]["auto"]["description"], "Nombre del auto a consultar")
            self.assertEqual(es_mejor.inputSchema["required"], ["auto"])

            cases = [
                ("mejor_auto", {}, "Fiat Pulse"),
                ("es_mejor_auto", {"auto": "Fiat Pulse"}, "Si"),
                ("es_mejor_auto", {"auto": "Otro auto"}, "No"),
            ]
            for name, arguments, expected in cases:
                result = await client.call_tool(name, arguments)
                self.assertFalse(result.isError)
                self.assertEqual(json.loads(result.content[0].text), {"estado": "Ok", "respuesta": expected})

            missing_argument = await client.call_tool("es_mejor_auto", {})
            self.assertTrue(missing_argument.isError)

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
