import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field


logging.basicConfig(level=logging.INFO)

mcp = FastMCP("mcp_autos", host="127.0.0.1", port=8003, json_response=True)


@mcp.tool()
def mejor_auto() -> dict:
    """Consulta cuál es el mejor auto según el MCP Autos"""
    try:
        return {"estado": "Ok", "respuesta": "Fiat Pulse"}
    except Exception as error:
        logging.error("Error en mejor_auto: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}


@mcp.tool()
def es_mejor_auto(
    auto: Annotated[str, Field(description="Nombre del auto a consultar")],
) -> dict:
    """Consulta si el auto indicado es el mejor según el MCP Autos"""
    try:
        respuesta = "Si" if auto.strip().casefold() == "fiat pulse" else "No"
        return {"estado": "Ok", "respuesta": respuesta}
    except Exception as error:
        logging.error("Error en es_mejor_auto: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
