"""Cliente MCP compartido, con transporte y sesión simulados."""

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from mcp.types import Tool
from funciones import mcp_funciones as mcp


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
        with patch("funciones.mcp_funciones.streamable_http_client", transporte):
            with patch("funciones.mcp_funciones.ClientSession") as factory:
                factory.return_value.__aenter__.return_value = session
                tools = await mcp.obtener_herramientas_mcp("http://mcp.test/mcp")
        self.assertEqual([tool["name"] for tool in tools], ["alfa", "zeta"])
        self.assertEqual(tools[1]["description"], "Descripción MCP")
        self.assertEqual(tools[1]["parameters"], schema)
        self.assertFalse(tools[1]["strict"])
        session.list_tools.assert_any_await(cursor=None)
        session.list_tools.assert_any_await(cursor="pagina2")


class EjecucionMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_url_explicita_y_resultado_mcp_se_conservan(self):
        for nombre, timeout, is_error in [("convertir_divisas", 30, False), ("get_pronostico", 60, True)]:
            with self.subTest(nombre=nombre):
                session = AsyncMock()
                datos = {"isError": is_error, "structuredContent": {"valor": "simulado"}, "content": []}
                session.call_tool.return_value = SimpleNamespace(model_dump=Mock(return_value=datos))

                @asynccontextmanager
                async def transporte(url, *, http_client):
                    self.assertEqual(url, "http://mcp-ficticio.test/mcp")
                    self.assertEqual(http_client.timeout.read, timeout)
                    yield None, None, None

                with patch("funciones.mcp_funciones.streamable_http_client", transporte), \
                        patch("funciones.mcp_funciones.ClientSession") as factory:
                    factory.return_value.__aenter__.return_value = session
                    resultado = await mcp.llamar_herramienta_mcp(nombre, {"dato": "ficticio"}, "http://mcp-ficticio.test/mcp")
                self.assertEqual(resultado, datos)
                session.initialize.assert_awaited_once_with()
                session.call_tool.assert_awaited_once_with(nombre, arguments={"dato": "ficticio"})


if __name__ == "__main__":
    unittest.main()
