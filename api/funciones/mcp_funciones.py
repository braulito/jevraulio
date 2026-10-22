"""Cliente MCP compartido por el chat con Jeveador."""

import logging
import re

import anyio
import httpx
from fastapi import HTTPException
from jsonschema import SchemaError
from jsonschema.validators import validator_for
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from funciones.seguridad_mcp import autorizar_herramienta, validar_definiciones_mcp, validar_destino, validar_resultado_mcp


logger = logging.getLogger(__name__)


async def obtener_herramientas_mcp(url: str) -> list[dict]:
    permitido, salida = validar_destino(url)
    if not permitido:
        raise HTTPException(status_code=salida["status_code"], detail="El destino MCP no está autorizado o su política no está disponible.")
    url = salida
    herramientas = []
    try:
        with anyio.fail_after(30):
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        cursor = None
                        vistos = set()
                        while True:
                            pagina = await session.list_tools(cursor=cursor)
                            if len(herramientas) + len(pagina.tools) > 64 or len(vistos) >= 64:
                                raise ValueError("El catálogo MCP excede los límites de herramientas o páginas.")
                            herramientas.extend(pagina.tools)
                            cursor = pagina.nextCursor
                            if not cursor:
                                break
                            if cursor in vistos:
                                raise ValueError("El MCP repitió un cursor de paginación.")
                            vistos.add(cursor)
    except TimeoutError as e:
        logger.error("Error al listar herramientas MCP: %s", e)
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera al listar herramientas.") from e
    except Exception as e:
        logger.error("Error al listar herramientas MCP: %s", e)
        raise HTTPException(status_code=502, detail="No se pudieron obtener las herramientas del MCP.") from e

    definiciones = []
    nombres = set()
    for tool in sorted(herramientas, key=lambda item: item.name):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", tool.name) or tool.name in nombres:
            raise HTTPException(status_code=502, detail="El MCP publicó nombres de herramientas inválidos o duplicados.")
        try:
            validator_for(tool.inputSchema).check_schema(tool.inputSchema)
        except SchemaError as e:
            logger.error("Error en el esquema de una herramienta MCP: %s", e)
            raise HTTPException(status_code=502, detail="El MCP publicó un esquema de parámetros inválido.") from e
        nombres.add(tool.name)
        definiciones.append({
            "type": "function",
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
            # Conservar parámetros opcionales y esquemas abiertos del MCP.
            "strict": False,
        })
    correcto, salida = validar_definiciones_mcp(definiciones)
    if not correcto:
        raise HTTPException(status_code=salida["status_code"], detail="El catálogo de ejecución MCP no cumple los límites de seguridad.")
    return salida


async def llamar_herramienta_mcp(nombre: str, argumentos: dict, url: str) -> dict:
    permitido, salida = autorizar_herramienta(nombre, url)
    if not permitido:
        raise HTTPException(status_code=salida["status_code"], detail="La herramienta MCP no tiene permiso de ejecución para ese destino.")
    url = salida
    # El pronóstico reúne cuatro consultas paralelas de hasta 30 segundos.
    tiempo_espera = 60 if nombre == "get_pronostico" else 30
    try:
        with anyio.fail_after(tiempo_espera):
            async with httpx.AsyncClient(timeout=tiempo_espera, follow_redirects=False) as client:
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        resultado = await session.call_tool(nombre, arguments=argumentos)
    except TimeoutError as e:
        logger.error("Error al ejecutar una herramienta MCP: %s", e)
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera al ejecutar la herramienta.") from e
    except Exception as e:
        logger.error("Error al ejecutar una herramienta MCP: %s", e)
        raise HTTPException(status_code=502, detail="No se pudo ejecutar la herramienta en el MCP.") from e
    # Preservar cualquier resultado MCP, incluido isError, sin exigir estado/respuesta.
    correcto, salida = validar_resultado_mcp(resultado.model_dump(mode="json", exclude_none=True))
    if not correcto:
        raise HTTPException(status_code=salida["status_code"], detail="El MCP devolvió un resultado inválido o demasiado grande.")
    return salida
