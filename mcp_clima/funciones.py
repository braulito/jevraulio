"""Consultas HTTP compartidas por las herramientas meteorológicas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging

import httpx


def obtener_datos_horarios(url: str) -> dict:
    """Consultar el endpoint y devolver hourly; propagar errores a la herramienta."""
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()["hourly"]


def combinar_pronostico(consultas: dict) -> dict:
    """Ejecutar consultas independientes y conservar datos parciales y sus fechas."""
    def consultar(item):
        variable, funcion = item
        try:
            resultado = funcion()
            if resultado["estado"] != "Ok":
                return variable, {"estado": "sin_datos", "respuesta": f"No hay datos para {variable}"}
            fecha, valor = resultado["respuesta"].split(",", 1)
            datetime.strptime(fecha, "%Y-%m-%d %H:%M")
            if not valor.strip():
                raise ValueError("El resultado no contiene un valor")
            return variable, {"estado": "Ok", "fecha_local": fecha, "valor": valor.strip()}
        except Exception:
            logging.error("No se pudieron obtener datos de pronóstico para %s", variable)
            return variable, {"estado": "sin_datos", "respuesta": f"No hay datos para {variable}"}

    with ThreadPoolExecutor(max_workers=4) as executor:
        datos = dict(executor.map(consultar, consultas.items()))

    fechas = {dato["fecha_local"] for dato in datos.values() if dato["estado"] == "Ok"}
    if not fechas:
        return {"estado": "Error", "respuesta": "No hay datos para ninguna variable del pronóstico", "status_code": 500, "datos": datos}

    respuesta = {
        "ubicacion": "Buenos Aires (CABA)",
        "zona_horaria": "GMT-3",
        "fecha_local": next(iter(fechas)) if len(fechas) == 1 else None,
        "fechas_coinciden": len(fechas) == 1,
        "datos": datos,
    }
    if len(fechas) > 1:
        respuesta["advertencia"] = "Las fechas y horas no coinciden; cada variable corresponde a su propio horario."
    return {"estado": "Ok", "respuesta": respuesta}
