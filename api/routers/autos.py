"""Rutas y funciones para consultar las herramientas del MCP Autos."""

import json
import logging
import os

import anyio
import httpx
from fastapi import APIRouter, HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, Field, ValidationError, field_validator


logger = logging.getLogger(__name__)
MCP_URL = os.getenv("MCP_AUTOS_URL", "http://127.0.0.1:8003/mcp")
MCP_TIMEOUT_SECONDS = 30

router = APIRouter(tags=["MCP Autos"])


class ConsultaAuto(BaseModel):
    auto: str = Field(min_length=1, examples=["Fiat Pulse"])

    @field_validator("auto")
    @classmethod
    def validar_auto(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre del auto no puede estar vacío.")
        return value


class RespuestaAuto(BaseModel):
    estado: str
    respuesta: str


ERRORES_MCP = {
    502: {"description": "El MCP no está disponible o devolvió un error."},
    504: {"description": "El MCP superó el tiempo de espera de 30 segundos."},
}


async def ejecutar_herramienta(nombre: str, argumentos: dict) -> RespuestaAuto:
    # Cada petición administra y cierra su propia sesión MCP.
    try:
        with anyio.fail_after(MCP_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
                async with streamable_http_client(MCP_URL, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(nombre, arguments=argumentos)
    except TimeoutError as error:
        logger.warning("Tiempo de espera agotado al ejecutar %s", nombre)
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera.") from error
    except Exception as error:
        logger.exception("Error al comunicarse con el MCP para ejecutar %s", nombre)
        raise HTTPException(
            status_code=502,
            detail="No se pudo completar la llamada al MCP. Verificá que esté activo en " + MCP_URL,
        ) from error

    if result.isError:
        logger.error("La herramienta %s devolvió un error MCP: %s", nombre, result.content)
        raise HTTPException(status_code=502, detail="La herramienta MCP devolvió un error.")

    try:
        datos = result.structuredContent
        if datos is None:
            texto = next(block.text for block in result.content if block.type == "text")
            datos = json.loads(texto)
        respuesta = RespuestaAuto.model_validate(datos)
    except (ValidationError, ValueError, StopIteration) as error:
        logger.exception("Respuesta inválida de la herramienta %s", nombre)
        raise HTTPException(status_code=502, detail="El MCP devolvió una respuesta inválida.") from error

    # El MCP puede informar un error dentro del JSON aunque isError sea False.
    if respuesta.estado != "Ok":
        raise HTTPException(status_code=502, detail=respuesta.respuesta)
    return respuesta


@router.get("/mejor_auto", response_model=RespuestaAuto, responses=ERRORES_MCP,
         summary="Consultar el mejor auto")
async def mejor_auto() -> RespuestaAuto:
    return await ejecutar_herramienta("mejor_auto", {})


@router.post("/es_mejor_auto", response_model=RespuestaAuto, responses=ERRORES_MCP,
          summary="Consultar si un auto es el mejor")
async def es_mejor_auto(consulta: ConsultaAuto) -> RespuestaAuto:
    return await ejecutar_herramienta("es_mejor_auto", {"auto": consulta.auto})
