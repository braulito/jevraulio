"""Funciones del chat y descubrimiento, validación y ejecución de herramientas MCP."""

import json
import os
import re

import anyio
import httpx
from fastapi import HTTPException
from jsonschema import SchemaError, ValidationError as SchemaValidationError
from jsonschema.validators import validator_for
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from funciones import openai_funciones as llm
from schemas.chat import LlamadaHerramienta, RespuestaChat


async def obtener_herramientas_mcp(url: str | None = None) -> list[dict]:
    herramientas = []
    url = url if url is not None else os.getenv("MCP_AUTOS_URL")
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
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera al listar herramientas.") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="No se pudieron obtener las herramientas del MCP.") from error

    definiciones = []
    nombres = set()
    for tool in sorted(herramientas, key=lambda item: item.name):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", tool.name) or tool.name in nombres:
            raise HTTPException(status_code=502, detail="El MCP publicó nombres de herramientas inválidos o duplicados.")
        try:
            validator_for(tool.inputSchema).check_schema(tool.inputSchema)
        except SchemaError as error:
            raise HTTPException(status_code=502, detail="El MCP publicó un esquema de parámetros inválido.") from error
        nombres.add(tool.name)
        definiciones.append({
            "type": "function",
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
            # Conservar parámetros opcionales y esquemas abiertos del MCP.
            "strict": False,
        })
    return definiciones


async def llamar_herramienta_mcp(nombre: str, argumentos: dict, url: str | None = None) -> dict:
    url = url if url is not None else os.getenv("MCP_AUTOS_URL")
    try:
        with anyio.fail_after(30):
            async with httpx.AsyncClient(timeout=30) as client:
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        resultado = await session.call_tool(nombre, arguments=argumentos)
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="El MCP superó el tiempo de espera al ejecutar la herramienta.") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="No se pudo ejecutar la herramienta en el MCP.") from error
    # Preservar cualquier resultado MCP, incluido isError, sin exigir estado/respuesta.
    return resultado.model_dump(mode="json", exclude_none=True)


async def ejecutar_llamada(llamada: dict, herramientas: list[dict]) -> tuple[str, dict]:
    try:
        tool = LlamadaHerramienta.model_validate(llamada)
        argumentos = json.loads(tool.arguments)
        if not isinstance(argumentos, dict):
            raise ValueError("Los argumentos deben ser un objeto.")
        definicion = next((item for item in herramientas if item["name"] == tool.name), None)
        if definicion is None:
            raise ValueError("La herramienta no fue publicada por el MCP.")
        schema = definicion["parameters"]
        validator_for(schema)(schema).validate(argumentos)
    except (ValidationError, ValueError, SchemaValidationError, SchemaError) as error:
        raise HTTPException(status_code=502, detail="OpenAI solicitó una herramienta o argumentos inválidos.") from error

    resultado = await llamar_herramienta_mcp(tool.name, argumentos)
    return tool.name, {
        "type": "function_call_output",
        "call_id": tool.call_id,
        "output": json.dumps(resultado, ensure_ascii=False),
    }


def obtener_max_rondas() -> int:
    valor = os.getenv("MAX_RONDAS", "").strip()
    try:
        max_rondas = int(valor)
        if max_rondas <= 0:
            raise ValueError("MAX_RONDAS debe ser mayor que cero.")
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="Configurá MAX_RONDAS en api/.env como un entero mayor que cero.",
        ) from error
    return max_rondas


async def responder_chat(mensaje: str) -> RespuestaChat:
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Falta configurar API_KEY en api/.env.")
    max_rondas = obtener_max_rondas()

    entrada = [{"role": "user", "content": mensaje}]
    ejecutadas = []
    try:
        with anyio.fail_after(180):
            herramientas = await obtener_herramientas_mcp()
            async with httpx.AsyncClient(
                timeout=60,
                headers={"Authorization": "Bearer " + api_key},
            ) as client:
                for _ in range(max_rondas):
                    resultado = await llm.consultar_llm(client, entrada, herramientas)
                    llamadas = [item for item in resultado.output if item.get("type") == "function_call"]
                    if llamadas:
                        # Conservar la salida del modelo y asociar cada resultado a su call_id.
                        entrada.extend(resultado.output)
                        for llamada in llamadas:
                            nombre, salida = await ejecutar_llamada(llamada, herramientas)
                            ejecutadas.append(nombre)
                            entrada.append(salida)
                        continue

                    respuesta = llm.extraer_texto(resultado.output)
                    if not respuesta:
                        raise HTTPException(status_code=502, detail="OpenAI no devolvió una respuesta de texto.")
                    return RespuestaChat(respuesta=respuesta, herramientas=ejecutadas)
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="El chat superó el tiempo de espera total.") from error

    raise HTTPException(status_code=502, detail="Se alcanzó el límite de rondas de herramientas del chat.")
