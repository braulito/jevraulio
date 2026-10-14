"""Cliente del MCP externo de Frankfurter, sin cargar configuración local."""

import json
import logging
from datetime import date
import re

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

FRANKFURTER_MCP_URL = "https://mcp.frankfurter.dev/"
TIMEOUT = 20.0
HERRAMIENTAS = {"convert", "get_rates", "list_currencies", "list_providers"}
logger = logging.getLogger(__name__)


def normalizar_moneda(valor: str) -> str:
    """Validar el formato ISO; Frankfurter determina si está soportada."""
    codigo = valor.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", codigo):
        raise ValueError("Código de moneda inválido")
    return codigo


def parametros_opcionales(fecha: str | None, proveedor: str | None) -> dict:
    parametros = {}
    if fecha is not None:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fecha):
            raise ValueError("Fecha inválida")
        date.fromisoformat(fecha)
        parametros["date"] = fecha
    if proveedor is not None:
        clave = proveedor.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{1,32}", clave):
            raise ValueError("Proveedor inválido")
        parametros["provider"] = clave
    return parametros


def _codigo_error(error: Exception) -> int:
    """Clasificar también errores agrupados por el transporte asíncrono."""
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return 504
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    if isinstance(error, McpError) and error.error.code == -32602:
        return 400
    for interno in getattr(error, "exceptions", ()):
        codigo = _codigo_error(interno)
        if codigo != 502:
            return codigo
    return 502


def _extraer_datos(respuesta):
    if respuesta.isError:
        return False, {"status_code": 502}
    if respuesta.structuredContent is not None:
        return True, respuesta.structuredContent
    textos = [bloque.text for bloque in respuesta.content if bloque.type == "text"]
    if not textos or not any(texto.strip() for texto in textos):
        return False, {"status_code": 502}
    if len(textos) == 1:
        try:
            return True, json.loads(textos[0])
        except (ValueError, TypeError):
            pass
    return True, "\n".join(textos)


async def consultar_frankfurter(herramienta: str, argumentos: dict) -> tuple:
    """Inicializar una sesión MCP, ejecutar una herramienta y cerrar recursos.

    Devuelve (True, datos) o (False, {status_code: código}). El plazo total
    incluye conexión, inicialización, llamada y cierre, y cabe dentro de
    los 30 segundos de espera del cliente de JEV.
    """
    try:
        if herramienta not in HERRAMIENTAS:
            return False, {"status_code": 400}
        with anyio.fail_after(TIMEOUT):
            async with streamablehttp_client(
                FRANKFURTER_MCP_URL, timeout=TIMEOUT, sse_read_timeout=TIMEOUT,
            ) as (lectura, escritura, _):
                async with ClientSession(lectura, escritura) as sesion:
                    await sesion.initialize()
                    respuesta = await sesion.call_tool(herramienta, argumentos)
                    resultado, salida = _extraer_datos(respuesta)
        if not resultado:
            logger.error("Frankfurter devolvió un fallo de herramienta o una respuesta vacía")
        return resultado, salida
    except Exception as e:
        codigo = _codigo_error(e)
        logger.error("Falló la consulta MCP a Frankfurter; status_code=%s: %s", codigo, e)
        return False, {"status_code": codigo}
