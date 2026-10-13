import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import math

import httpx

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings


logging.basicConfig(level=logging.INFO)

# Evita la carga automática de archivos .env por FastMCP.
Settings.model_config["env_file"] = None

mcp = FastMCP("mcp_clima", host="127.0.0.1", port=8005, json_response=True)

CLIMA_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=-34.6131&longitude=-58.3772&hourly=temperature_2m"
)

PRECIPITACIONES_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=-34.6131&longitude=-58.3772&hourly=precipitation_probability"
)


@mcp.tool()
def get_clima() -> dict:
    """Consulta el pronóstico de temperatura para la Ciudad de Buenos Aires (CABA), Argentina.

    CAPACIDAD Y CUÁNDO USARLA
    Obtiene de Open-Meteo la temperatura del último horario disponible
    en el pronóstico de Buenos Aires y su fecha y hora local (GMT-3).
    Es aplicable a consultas sobre temperatura pronosticada en Buenos Aires,
    CABA o Capital Federal, y sobre el último dato del pronóstico disponible.
    Puede aportar la temperatura a una pregunta general sobre el clima o
    el tiempo en esa ciudad, indicando siempre la fecha y hora del dato.
    Para consultas generales sin localidad, la ubicación predeterminada de
    esta herramienta es Buenos Aires (CABA). No falta un parámetro de ciudad
    y no se necesita pedir confirmación de Buenos Aires antes de ejecutarla.
    Preguntas como 'qué clima hace', 'cómo está el tiempo' o 'qué temperatura
    hace', sin fecha ni localidad explícitas, solicitan el dato meteorológico
    disponible: consultar esta herramienta e informar que es un pronóstico
    para CABA, junto con la fecha y hora exactas que devuelve.
    Si el mensaje o el contexto especifican otra ciudad, no es aplicable.

    ARGUMENTOS
    No recibe argumentos. La ubicación está fijada en la Ciudad de Buenos
    Aires, Argentina (latitud -34.6131, longitud -58.3772). No permite elegir
    otra localidad, una fecha ni un horario.

    RESULTADO
    Devuelve un diccionario con estado='Ok' y respuesta en el formato
    'AAAA-MM-DD HH:MM, TEMPERATURA °C'. La fecha y hora están convertidas
    de GMT a GMT-3 y la temperatura está expresada en grados Celsius.
    Ejemplo ilustrativo: {'estado': 'Ok', 'respuesta': '2026-10-18 20:00, 21.5 °C'}.
    Si la consulta falla, devuelve estado='Error', respuesta='Error interno'
    y status_code=500. En ese caso no hay una temperatura utilizable.

    EJEMPLOS DE CONSULTAS APLICABLES
    - 'que clima hace'
    - 'como esta el tiempo'
    - 'decime la temperatura'
    - '¿Cuál es la última temperatura pronosticada para Buenos Aires?'
    - 'Dame el último dato del pronóstico de temperatura en CABA.'
    - '¿Qué temperatura y a qué hora informa el pronóstico de Capital Federal?'
    - '¿Qué dice el pronóstico del tiempo en Buenos Aires?' (aporta temperatura).
    - 'que temperatura hace'
    - 'hace frio o calor'
    - 'me tengo que abrigar ahora?'
    - 'cuantos grados hace en buenos aires?'
    - 'como esta el tiempo en capital?'
    - 'que tal esta el clima en caba?'
    - 'esta fresco afuera?'
    - 'hace mucho calor?'
    - 'esta para salir con campera?'
    - 'me llevo un buzo?'
    - 'salgo en remera o me abrigo?'
    - 'necesito una campera para salir?'
    - 'esta para mangas cortas?'
    - 'que temperatura marca el pronostico?'

    Las preguntas coloquiales sin ciudad usan Buenos Aires por defecto,
    salvo que el contexto establezca otra localidad. Las consultas sobre frío,
    calor o abrigo pueden aprovechar
    la temperatura como información parcial, siempre indicando su fecha y hora.
    Si la pregunta se refiere a ahora, solo se puede responder sobre ese momento
    si el horario devuelto coincide con el solicitado; un dato futuro no permite
    afirmar qué temperatura hace ahora ni recomendar abrigo para salir ahora.

    ALCANCE Y LÍMITES
    Selecciona el último registro del pronóstico, que puede corresponder
    a una fecha futura. No devuelve necesariamente la temperatura actual,
    la de hoy, la de mañana ni la de una fecha solicitada. No resuelve esas
    consultas específicas con el dato que entrega. No informa lluvia,
    humedad, viento, sensación térmica, máximas, mínimas ni una serie horaria.
    Tampoco consulta otras ciudades o toda la provincia de Buenos Aires.
    No compara tipos de clima ni decide cuál es el mejor clima.
    """
    try:
        response = httpx.get(CLIMA_URL, timeout=30.0)
        response.raise_for_status()
        hourly = response.json()["hourly"]
        tiempos = hourly["time"]
        temperaturas = hourly["temperature_2m"]
        if (
            not isinstance(tiempos, list)
            or not isinstance(temperaturas, list)
            or not tiempos
            or len(tiempos) != len(temperaturas)
        ):
            raise ValueError("Series horarias vacías o inconsistentes")
        temperatura = temperaturas[-1]
        if isinstance(temperatura, bool) or not isinstance(temperatura, (int, float)) or not math.isfinite(temperatura):
            logging.error("Error en clima: La última temperatura no es un número válido")
            return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}
        # La URL solicitada devuelve fechas sin offset en GMT (UTC).
        fecha_gmt = datetime.fromisoformat(tiempos[-1]).replace(tzinfo=timezone.utc)
        fecha_local = fecha_gmt.astimezone(timezone(timedelta(hours=-3)))
        return {"estado": "Ok", "respuesta": f"{fecha_local:%Y-%m-%d %H:%M}, {temperatura} °C"}
    except Exception as error:
        logging.error("Error en clima: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}



@mcp.tool()
def get_precipitaciones() -> dict:
    """Consulta la probabilidad de precipitaciones pronosticada para Buenos Aires (CABA), Argentina.

    CAPACIDAD Y CUÁNDO USARLA
    Obtiene de Open-Meteo el último porcentaje de probabilidad de
    precipitaciones del pronóstico horario, junto con su fecha y hora
    en GMT-3. Es aplicable a preguntas sobre posibilidades de lluvia,
    probabilidad de precipitaciones o si conviene llevar un paraguas.
    Sin localidad explícita, usa Buenos Aires (CABA) por defecto y no
    requiere confirmar la ciudad. Si el contexto indica otra ciudad,
    no es aplicable. Una pregunta general como 'qué clima hace' corresponde
    a get_clima; esta herramienta se usa cuando se pregunta por lluvias.

    ARGUMENTOS Y RESULTADO
    No recibe argumentos. La ubicación está fijada en latitud -34.6131,
    longitud -58.3772. Devuelve estado='Ok' y respuesta con el formato
    'AAAA-MM-DD HH:MM, PROBABILIDAD % de lluvias'. El porcentaje representa
    una probabilidad, no cantidad ni intensidad de lluvia ni certeza de
    que lloverá. Ante un error devuelve estado='Error', respuesta='Error
    interno' y status_code=500.

    EJEMPLOS DE CONSULTAS APLICABLES
    - 'que probabilidad de lluvia hay?'
    - 'hay chances de lluvia en caba?'
    - 'que posibilidades hay de que llueva en buenos aires?'
    - 'decime el porcentaje de precipitaciones del pronostico'
    - 'me llevo un paraguas?' (aporta la probabilidad para el horario informado).

    ALCANCE Y LÍMITES
    Toma el último registro disponible del pronóstico, que puede ser futuro.
    Se debe informar siempre la fecha y hora del dato. No indica si está
    lloviendo ahora ni permite elegir hoy, mañana u otro horario específico.
    No informa milímetros de lluvia, intensidad, duración, temperatura ni
    presión atmosférica. No permite consultar otras localidades.
    """
    try:
        response = httpx.get(PRECIPITACIONES_URL, timeout=30.0)
        response.raise_for_status()
        hourly = response.json()["hourly"]
        tiempos = hourly["time"]
        probabilidades = hourly["precipitation_probability"]
        if (
            not isinstance(tiempos, list)
            or not isinstance(probabilidades, list)
            or not tiempos
            or len(tiempos) != len(probabilidades)
        ):
            raise ValueError("Series horarias vacías o inconsistentes")
        precipitaciones = probabilidades[-1]
        if (
            isinstance(precipitaciones, bool)
            or not isinstance(precipitaciones, (int, float))
            or not math.isfinite(precipitaciones)
            or not 0 <= precipitaciones <= 100
        ):
            logging.error("Error en get_precipitaciones: La última probabilidad no es un porcentaje válido")
            return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}
        # La URL solicitada devuelve fechas sin offset en GMT (UTC).
        fecha_gmt = datetime.fromisoformat(tiempos[-1]).replace(tzinfo=timezone.utc)
        fecha_local = fecha_gmt.astimezone(timezone(timedelta(hours=-3)))
        return {"estado": "Ok", "respuesta": f"{fecha_local:%Y-%m-%d %H:%M}, {precipitaciones} % de lluvias"}
    except Exception as error:
        logging.error("Error en get_precipitaciones: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
