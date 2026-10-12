"""Cliente de OpenAI, prompt, caché y lectura de respuestas."""

import hashlib
import json
import os

import httpx
from fastapi import HTTPException

from funciones import billing
from schemas.chat import RespuestaOpenAI


OPENAI_URL = "https://api.openai.com/v1/responses"


INSTRUCCIONES = (
    "Respondé en español de forma breve. Usá las herramientas disponibles según "
    "sus descripciones y esquemas de parámetros. Si falta un dato obligatorio, "
    "pedilo sin inventarlo. Basá las respuestas que requieren datos externos en los resultados de "
    "las herramientas, sin inventar resultados ni afirmar que llamaste una herramienta "
    "si no lo hiciste. Si una herramienta informa un error, explicalo sin inventar datos."
)


def clave_cache_prompt(modelo: str, herramientas: list[dict]) -> str:
    # Compartir caché solo entre solicitudes con el mismo modelo y prefijo fijo.
    prefijo = json.dumps([modelo, INSTRUCCIONES, herramientas], sort_keys=True, ensure_ascii=False)
    return "jev-autos-" + hashlib.sha256(prefijo.encode("utf-8")).hexdigest()[:32]


async def consultar_llm(client: httpx.AsyncClient, entrada: list[dict], herramientas: list[dict]) -> RespuestaOpenAI:
    modelo = os.getenv("MODELO_OPENAI", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    try:
        response = await client.post(
            OPENAI_URL,
            json={
                "model": modelo,
                "service_tier": "default",
                **({"reasoning": {"effort": "none"}} if modelo == "gpt-6-luna" else {}),
                "prompt_cache_key": clave_cache_prompt(modelo, herramientas),
                "instructions": INSTRUCCIONES,
                "input": entrada,
                "tools": herramientas,
                "parallel_tool_calls": False,
                "store": False,
                "include": ["reasoning.encrypted_content"],
                "max_output_tokens": 1200,
            },
        )
        datos = response.json()
        billing.registrar_uso_openai(datos, modelo, entrada)
        response.raise_for_status()
        resultado = RespuestaOpenAI.model_validate(datos)
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="OpenAI superó el tiempo de espera.") from error
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status in (401, 403):
            detail = "OpenAI rechazó las credenciales o permisos. Revisá API_KEY y el acceso al modelo."
        elif status == 429:
            detail = "OpenAI informó un límite de solicitudes o cuota. Revisá la cuota de tu cuenta."
        else:
            detail = "OpenAI rechazó la solicitud. Revisá el modelo configurado o intentá nuevamente."
        raise HTTPException(status_code=502, detail=detail) from error
    except (httpx.RequestError, ValueError) as error:
        raise HTTPException(status_code=502, detail="No se pudo obtener una respuesta válida de OpenAI.") from error

    if resultado.status != "completed":
        raise HTTPException(status_code=502, detail="OpenAI no pudo completar la respuesta.")
    return resultado


def extraer_texto(salida: list[dict]) -> str:
    textos = []
    for item in salida:
        if item.get("type") != "message":
            continue
        contenido = item.get("content", [])
        if not isinstance(contenido, list):
            continue
        for block in contenido:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text":
                texto = block.get("text")
            elif block.get("type") == "refusal":
                texto = block.get("refusal")
            else:
                continue
            if isinstance(texto, str):
                textos.append(texto)
    return "\n".join(textos).strip()
