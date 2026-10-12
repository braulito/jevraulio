import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings
from pydantic import Field


logging.basicConfig(level=logging.INFO)

# Evita la carga automática de archivos .env por FastMCP.
Settings.model_config["env_file"] = None

mcp = FastMCP("mcp_cocina", host="127.0.0.1", port=8004, json_response=True)


@mcp.tool()
def es_mejor_plato(plato: Annotated[str, Field(min_length=1, description="Nombre plato a analizar")]) -> dict:
    """
    Determina si un único plato es el mejor según MCP Cocina.
    Es aplicable a preguntas como «¿El flan es el mejor plato?»,
    tanto si la respuesta será Sí como si será No.
    Recibe el nombre del plato y devuelve Sí para milanesa/milanesas
    y No para cualquier otro plato. No compara dos platos.
    
    EJEMPLOS
    --------
    
    pregunta: el flan es el mejor plato?
    Argumento: plato='flan'
    Resultado: Como no es milanesa, la respuesta es NO
    """
    try:
        logging.info(plato)
        nombre = plato.strip().casefold()
        respuesta = "Si" if nombre in {"milanesa", "milanesas"} else "No"
        return {"estado": "Ok", "respuesta": respuesta}
    except Exception as error:
        logging.error("Error en es_mejor_plato: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}

@mcp.tool()
def compara_platos(
    plato_a: Annotated[str, Field(min_length=1, description="Nombre del primer plato a comparar")],
    plato_b: Annotated[str, Field(min_length=1, description="Nombre del segundo plato a comparar")],
) -> dict:
    """Compara dos platos y elige el mejor según el MCP Cocina.
    Resuelve preguntas como «Compará flan vs milanesas y decime cuál es mejor».
    El criterio del MCP prefiere milanesas frente a cualquier otro plato.
    Si ambos son el mismo plato, indica empate. Si son distintos y ninguno
    es milanesas, informa que no tiene un criterio para elegir entre ellos.
    
    EJEMPLOS
    --------
    Pregunta: Compará flan vs milanesas y decime cuál es mejor.
    Argumentos: plato_a='flan', plato_b='milanesas'.
    Resultado: Entre esos dos platos, el mejor según el MCP Cocina es Milanesas.
    
    Pregunta: Compará milanesas y flan y decime cuál es mejor.
    Argumentos: plato_a='milanesas', plato_b='flan'.
    Resultado: Entre esos dos platos, el mejor según el MCP Cocina es Milanesas.
    El resultado depende del criterio del MCP, no del orden de los argumentos.
        
    Pregunta: Compará milanesas y milanesas.
    Argumentos: plato_a='milanesas', plato_b='milanesas'.
    Resultado: Pero en este caso como ambos son milanesas,
    el resutado es Empate: ambos nombres corresponden 
    al mismo plato y las milanesas son las mejores.
    
    Pregunta: compara milanesas vs milanesas napolitana
    Argumentos: plato_a='milanesas', plato_b='milanesas napolitana'
    Resultado: como ambas son milanesas, es un empate porque son el mismo
    plato.

    Pregunta: Compará flan y flan.
    Argumentos: plato_a='flan', plato_b='flan'.
    Resultado: Empate: ambos nombres corresponden al mismo plato.
    El empate no implica que el plato sea bueno o malo.

    Pregunta: Compará flan y pizza y decime cuál es mejor.
    Argumentos: plato_a='flan', plato_b='pizza'.
    Resultado: El MCP Cocina no tiene un criterio para elegir el mejor entre esos dos platos.
    """
    try:
        nombres = [plato_a.strip(), plato_b.strip()]
        if not all(nombres):
            return {"estado": "Error", "respuesta": "Indicá los nombres de los dos platos.", "status_code": 400}
        normalizados = ["milanesas" if nombre.casefold() == "milanesa" else nombre.casefold() for nombre in nombres]
        if normalizados[0] == normalizados[1]:
            respuesta = "Empate: ambos nombres corresponden al mismo plato."
        elif "milanesas" in normalizados:
            respuesta = "Entre esos dos platos, el mejor según el MCP Cocina es Milanesas."
        else:
            respuesta = "El MCP Cocina no tiene un criterio para elegir el mejor entre esos dos platos."
        return {"estado": "Ok", "respuesta": respuesta}
    except Exception as error:
        logging.error("Error en compara_platos: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")


#################### DEPRECADAS
'''
@mcp.tool()
def mejor_plato() -> dict:
    """Consulta cuál es el mejor plato según el MCP Cocina
    
    Esta herramienta responde preguntas del tipo "cual es el mejor plato"
    
    NO LLEVA ARGUMENTOS
    
    Si la pregunta es "¿El flan es el mejor plato?" -> NO CORRESPONDE ESTA HERRAMIENTA
    
    """
    try:
        return {"estado": "Ok", "respuesta": "Milanesas"}
    except Exception as error:
        logging.error("Error en mejor_plato: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}

'''
