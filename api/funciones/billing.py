"""Registro del consumo y costo de las llamadas a la LLM."""

import logging

from funciones.base_sqlite import guardar_billing

# Usar el nivel INFO y la salida de consola configurados por Uvicorn.
logger = logging.getLogger("uvicorn.error.billing")


def identificar_metodo(salida: list[dict], entrada: list[dict]) -> tuple[str, list[str]]:
    llamadas = [item for item in salida if item.get("type") == "function_call"]
    if llamadas:
        return "tool_call", []
    resultados = {item.get("call_id") for item in entrada if item.get("type") == "function_call_output"}
    if resultados:
        nombres = [
            item["name"] for item in entrada
            if item.get("type") == "function_call" and item.get("call_id") in resultados and item.get("name")
        ]
        return "mcp", list(dict.fromkeys(nombres))
    return "respuesta", []


def registrar_consumo(datos: dict) -> None:
    """Guarda los datos del consumo en SQLite y registra un resumen en consola."""
    try:
        guardar_billing(datos)
    except Exception:
        logger.exception("No se pudo guardar el consumo y costo de la LLM en SQLite.")
        raise
    '''
    tokens = datos.get("tokens") or {}
    total = tokens.get("total_tokens")
    costo = datos.get("costo_estimado_usd")
    costo_texto = f"USD {costo:.10f}" if costo is not None else "no disponible"
    metodo = datos.get("metodo", "no disponible")
    herramientas = '""' if metodo == "tool_call" else (", ".join(datos.get("herramientas") or []) or "ninguna")
    logger.info(
        "TOKENS TOTALES: %s, COSTO: %s, METODO: %s, HERRAMIENTAS: %s",
        total if total is not None else "no disponible",
        costo_texto,
        metodo,
        herramientas,
    )
    '''


# USD por millón de tokens, tarifa estándar verificada el 11/10/2026.
# https://developers.openai.com/api/docs/models/gpt-4.1-mini
# https://developers.openai.com/api/docs/models/gpt-6-luna
# Orden: entrada, lectura de caché, salida, escritura de caché.
PRECIOS = {
    "gpt-4.1-mini": (0.40, 0.10, 1.60, 0.40),
    "gpt-4.1-mini-2025-04-14": (0.40, 0.10, 1.60, 0.40),
    "gpt-6-luna": (0.10, 0.01, 0.50, 0.125),
}


def costo_uso(usage: dict | None, modelo: str) -> float | None:
    precios = PRECIOS.get(modelo)
    if not usage or precios is None:
        return None
    entrada = usage.get("input_tokens")
    salida = usage.get("output_tokens")
    if entrada is None or salida is None:
        return None
    detalles = usage.get("input_tokens_details") or {}
    cacheados = detalles.get("cached_tokens", 0)
    escritos = detalles.get("cache_write_tokens", 0)
    precio_entrada, precio_cache, precio_salida, precio_escritura = precios
    if modelo == "gpt-6-luna" and entrada > 272_000:
        precio_entrada *= 2
        precio_cache *= 2
        precio_escritura *= 2
        precio_salida *= 1.5
    # Los cacheados ya están incluidos en input_tokens. Los de razonamiento
    # ya están incluidos en output_tokens: no sumarlos una segunda vez.
    costo = (
        (entrada - cacheados - escritos) * precio_entrada
        + cacheados * precio_cache
        + escritos * precio_escritura
        + salida * precio_salida
    ) / 1_000_000
    return round(costo, 10)


def registrar_uso_openai(datos: dict, modelo: str, entrada: list[dict]) -> None:
    usage = datos.get("usage")
    modelo = datos.get("model") or modelo
    metodo, herramientas = identificar_metodo(datos.get("output") or [], entrada)
    registrar_consumo({
        "tokens": usage,
        "costo_estimado_usd": costo_uso(usage, modelo),
        "metodo": metodo,
        "herramientas": herramientas,
    })
