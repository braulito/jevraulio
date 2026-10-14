"""MCP Finanzas: herramientas locales respaldadas por el MCP de Frankfurter."""

import logging
import math
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings
from pydantic import Field

from funciones import (
    FRANKFURTER_MCP_URL, consultar_frankfurter, normalizar_moneda,
    parametros_opcionales,
)

logging.basicConfig(level=logging.INFO)
# Este componente no lee .env, ni explícitamente ni mediante FastMCP.
Settings.model_config["env_file"] = None
mcp = FastMCP("mcp_finanzas", host="127.0.0.1", port=8006, json_response=True)
logger = logging.getLogger(__name__)

Moneda = Annotated[str, Field(description="Código ISO 4217 de tres letras, por ejemplo USD o EUR")]
Fecha = Annotated[str | None, Field(description="Fecha histórica YYYY-MM-DD; omitir para la última disponible")]
Proveedor = Annotated[str | None, Field(description="Clave de institución devuelta por get_proveedores; omitir para tipos combinados")]


def _fallo(codigo: int) -> dict:
    return {"estado": "Error", "respuesta": "No se pudo completar la consulta financiera", "status_code": codigo}


async def _ejecutar(herramienta: str, argumentos: dict) -> dict:
    try:
        resultado, salida = await consultar_frankfurter(herramienta, argumentos)
        if not resultado:
            return _fallo(salida["status_code"])
        return {"estado": "Ok", "respuesta": salida, "fuente": "Frankfurter", "mcp_externo": FRANKFURTER_MCP_URL}
    except Exception as e:
        logger.error("Error interno al procesar la respuesta de Finanzas: %s", e)
        return _fallo(500)


@mcp.tool()
async def convertir_divisas(
    importe: Annotated[float, Field(gt=0, allow_inf_nan=False, description="Importe positivo a convertir")],
    moneda_origen: Moneda,
    moneda_destino: Moneda,
    fecha: Fecha = None,
    proveedor: Proveedor = None,
) -> dict:
    """Convierte un importe entre dos monedas mediante el MCP externo de Frankfurter.

    CUÁNDO USARLA
    Para '¿cuántos euros son 100 dólares?' o 'convertí 250 EUR a USD el
    2024-06-03'. Requiere importe y ambas monedas; si faltan, pedir aclaración.
    No asumir que 'pesos' significa una moneda concreta. Sin fecha obtiene
    el último tipo de referencia disponible; con fecha usa un tipo histórico.
    proveedor es opcional y se obtiene de get_proveedores.

    RESULTADO Y LÍMITES
    Devuelve estado='Ok', respuesta original de convert y fuente Frankfurter.
    Conservar la fecha efectiva y las monedas que informa el servicio.
    Son tipos de referencia, no precios de compraventa en tiempo real;
    no incluyen comisiones ni realizan transferencias. No aporta dólar blue,
    MEP, tarjeta, pronósticos ni recomendaciones de inversión. No inventar
    un tipo si la moneda, fecha o fuente no está disponible. Para consultar
    solo un tipo sin convertir un importe usar get_tipos_cambio.
    Ante fallos devuelve estado='Error' y status_code, sin un importe usable.
    """
    try:
        if isinstance(importe, bool) or not math.isfinite(importe) or importe <= 0:
            raise ValueError("Importe inválido")
        argumentos = parametros_opcionales(fecha, proveedor)
        argumentos.update({"amount": importe, "from": normalizar_moneda(moneda_origen), "to": normalizar_moneda(moneda_destino)})
        return await _ejecutar("convert", argumentos)
    except ValueError as e:
        logger.error("Argumentos inválidos para Finanzas: %s", e)
        return _fallo(400)
    except Exception as e:
        logger.error("Error interno en convertir_divisas: %s", e)
        return _fallo(500)


@mcp.tool()
async def get_tipos_cambio(
    moneda_base: Moneda,
    monedas_destino: Annotated[str | None, Field(description="Códigos ISO separados por comas, por ejemplo USD,GBP; omitir para todas")] = None,
    fecha: Fecha = None,
    proveedor: Proveedor = None,
) -> dict:
    """Consulta tipos de cambio de referencia mediante get_rates de Frankfurter.

    Para 'tipo de cambio del euro al dólar', 'USD contra EUR y GBP' o
    'cotización EUR/USD el 2024-06-03'. Requiere moneda_base explícita;
    destinos se separan por comas, y omitirlos solicita todos los disponibles.
    Sin fecha usa el último dato disponible; no garantiza un dato de hoy.
    Puede consultar varios destinos en una sola llamada. proveedor permite
    elegir una institución de get_proveedores; sin él usa tipos combinados.
    Devuelve estado='Ok', datos originales con sus fechas y fuente Frankfurter.
    Informar cada fecha efectiva; no presentar datos de distintas fechas como
    simultáneos. Para convertir un importe corresponde convertir_divisas.
    No consulta dólar blue, MEP, tarjeta, acciones, criptomonedas, tendencias
    ni rangos de fechas. No predice ni recomienda inversiones. Solo monedas
    y fechas soportadas por la fuente. Ante fallo devuelve estado='Error'
    y status_code; no hay una cotización utilizable.
    """
    try:
        argumentos = parametros_opcionales(fecha, proveedor)
        argumentos["base"] = normalizar_moneda(moneda_base)
        if monedas_destino is not None:
            argumentos["quotes"] = ",".join(dict.fromkeys(normalizar_moneda(codigo) for codigo in monedas_destino.split(",")))
        return await _ejecutar("get_rates", argumentos)
    except ValueError as e:
        logger.error("Argumentos inválidos para Finanzas: %s", e)
        return _fallo(400)
    except Exception as e:
        logger.error("Error interno en get_tipos_cambio: %s", e)
        return _fallo(500)


@mcp.tool()
async def get_monedas() -> dict:
    """Lista códigos ISO 4217 y nombres de monedas admitidas por Frankfurter.

    Para '¿qué monedas podés convertir?' o '¿está soportado el peso argentino?'.
    No recibe argumentos. Devuelve el catálogo original de list_currencies
    con fuente Frankfurter, o estado='Error' con status_code si falla.
    La presencia en el catálogo no garantiza datos para toda fecha o fuente.
    No devuelve cotizaciones ni conversiones de importes.
    """
    return await _ejecutar("list_currencies", {})


@mcp.tool()
async def get_proveedores() -> dict:
    """Lista instituciones y cobertura de los tipos de referencia de Frankfurter.

    Para '¿de dónde salen los tipos de cambio?' o '¿qué fuentes hay disponibles?'.
    No recibe argumentos. Delega en list_providers y conserva claves, frecuencia,
    tipo de cotización y fechas de cobertura devueltas por el servicio.
    Las claves pueden usarse en proveedor de convertir_divisas o get_tipos_cambio.
    No lista bancos para operar ni recomienda una institución. No devuelve
    cotizaciones. Devuelve estado='Ok' y fuente, o estado='Error' con status_code.
    """
    return await _ejecutar("list_providers", {})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
