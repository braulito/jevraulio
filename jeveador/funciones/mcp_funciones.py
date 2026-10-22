"""Descubrimiento de herramientas de un MCP mediante Streamable HTTP."""

import logging
from urllib.parse import urlsplit, urlunsplit

import anyio
import httpx
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from funciones.catalogo_validaciones import MAX_HERRAMIENTAS_MCP, MAX_PAGINAS_MCP, validar_herramientas
from funciones.destinos_mcp import validar_destino


logger = logging.getLogger(__name__)


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
    permitido, salida = validar_destino(url)
    if not permitido:
        raise HTTPException(status_code=salida["status_code"], detail="El destino MCP no está autorizado en la política local de descubrimiento.")
    url = salida
    herramientas = []
    fallo_validacion = None
    try:
        with anyio.fail_after(30):
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        cursor = None
                        vistos = set()
                        paginas = 0
                        while True:
                            if paginas >= MAX_PAGINAS_MCP:
                                logger.error("Error en obtener_herramientas_mcp: el catálogo supera el límite de páginas MCP.")
                                raise ValueError("El catálogo supera el límite de páginas MCP.")
                            pagina = await session.list_tools(cursor=cursor)
                            paginas += 1
                            if len(herramientas) + len(pagina.tools) > MAX_HERRAMIENTAS_MCP:
                                logger.error("Error en obtener_herramientas_mcp: el MCP supera el límite de herramientas publicadas.")
                                raise ValueError("El MCP supera el límite de herramientas publicadas.")
                            herramientas.extend(
                                {"name": tool.name, "description": tool.description or "", "inputSchema": tool.inputSchema}
                                for tool in pagina.tools
                            )
                            resultado, salida = validar_herramientas(herramientas)
                            if not resultado:
                                fallo_validacion = salida
                                break
                            herramientas = salida
                            cursor = pagina.nextCursor
                            if not cursor:
                                break
                            if cursor in vistos:
                                raise ValueError("El MCP repitió un cursor de paginación.")
                            vistos.add(cursor)
    except TimeoutError as e:
        logger.error("Error en obtener_herramientas_mcp: tiempo de espera agotado (%s)", e)
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera al listar herramientas.") from None
    except Exception as e:
        # Un fallo de transporte puede incluir la URL: registrar el tipo sin exponerla.
        detalle = str(e) if isinstance(e, ValueError) else type(e).__name__
        logger.error("Error en obtener_herramientas_mcp: %s", detalle)
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener las herramientas del MCP. Verificá que esté encendido y que su URL en mcps apunte al endpoint MCP (/mcp).",
        ) from None

    if fallo_validacion is not None:
        raise HTTPException(status_code=fallo_validacion["status_code"], detail="El MCP publicó un catálogo inválido o fuera de los límites permitidos.")
    return sorted(herramientas, key=lambda item: item["name"])
