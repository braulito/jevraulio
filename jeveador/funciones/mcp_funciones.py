"""Descubrimiento de herramientas de un MCP mediante Streamable HTTP."""

from urllib.parse import urlsplit, urlunsplit

import anyio
import httpx
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def obtener_url_mcp(url: str) -> str:
    url = url.strip()
    if not url:
        raise HTTPException(status_code=503, detail="Falta la URL de un MCP en la tabla mcps.")
    try:
        partes = urlsplit(url)
        if partes.scheme not in {"http", "https"} or not partes.hostname:
            raise ValueError("URL inválida.")
        partes.port  # Comprobar la sintaxis del puerto sin imprimirlo.
    except ValueError:
        raise HTTPException(status_code=503, detail="La URL del MCP en la tabla mcps debe ser HTTP o HTTPS válida.") from None
    # FastMCP de mcp_autos expone el protocolo en /mcp, no en /.
    ruta = "/mcp" if partes.path in {"", "/"} else partes.path
    return urlunsplit((partes.scheme, partes.netloc, ruta, partes.query, ""))


async def obtener_herramientas_mcp(url: str) -> list[dict]:
    url = obtener_url_mcp(url)
    herramientas = []
    try:
        with anyio.fail_after(30):
            async with httpx.AsyncClient(timeout=30) as client:
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        cursor = None
                        vistos = set()
                        while True:
                            pagina = await session.list_tools(cursor=cursor)
                            herramientas.extend(pagina.tools)
                            cursor = pagina.nextCursor
                            if not cursor:
                                break
                            if cursor in vistos:
                                raise ValueError("El MCP repitió un cursor de paginación.")
                            vistos.add(cursor)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera al listar herramientas.") from None
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener las herramientas del MCP. Verificá que esté encendido y que su URL en mcps apunte al endpoint MCP (/mcp).",
        ) from None

    nombres = [tool.name for tool in herramientas]
    if len(set(nombres)) != len(nombres):
        raise HTTPException(status_code=502, detail="El MCP publicó nombres de herramientas duplicados.")
    return [
        {"name": tool.name, "description": tool.description or "", "inputSchema": tool.inputSchema}
        for tool in sorted(herramientas, key=lambda item: item.name)
    ]
