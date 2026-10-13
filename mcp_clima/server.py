import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path

from dotenv import load_dotenv

from funciones import combinar_pronostico, obtener_datos_horarios

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings


logging.basicConfig(level=logging.INFO)

load_dotenv(Path(__file__).resolve().parent / ".env")

# Evita la carga automática de archivos .env por FastMCP.
Settings.model_config["env_file"] = None

mcp = FastMCP("mcp_clima", host="127.0.0.1", port=8005, json_response=True)

TEMPERATURA_URL = os.getenv("TEMPERATURA_URL", "").strip()
PRECIPITACIONES_URL = os.getenv("PRECIPITACIONES_URL", "").strip()
SENSACION_TERMICA_URL = os.getenv("SENSACION_TERMICA_URL", "").strip()
PRESION_URL = os.getenv("PRESION_URL", "").strip()

_urls_faltantes = [
    nombre
    for nombre, valor in (
        ("TEMPERATURA_URL", TEMPERATURA_URL),
        ("PRECIPITACIONES_URL", PRECIPITACIONES_URL),
        ("SENSACION_TERMICA_URL", SENSACION_TERMICA_URL),
        ("PRESION_URL", PRESION_URL),
    )
    if not valor
]
if _urls_faltantes:
    raise RuntimeError("Falta configurar: " + ", ".join(_urls_faltantes))


@mcp.tool()
def get_temperatura() -> dict:
    """Consulta el pronóstico de temperatura para la Ciudad de Buenos Aires (CABA), Argentina.

    CAPACIDAD Y CUÁNDO USARLA
    Obtiene de Open-Meteo la temperatura del último horario disponible
    en el pronóstico de Buenos Aires y su fecha y hora local (GMT-3).
    Es aplicable cuando el pedido se limita a temperatura del aire en °C,
    cuántos grados se pronostican, frío/calor o abrigo basado en temperatura.
    Sin localidad explícita usa Buenos Aires (CABA) por defecto, sin pedir
    confirmación. Informar siempre la fecha y hora del dato pronosticado.
    Una consulta general sobre clima, tiempo o pronóstico, sin una variable
    específica, corresponde exclusivamente a get_pronostico. Esta herramienta
    no es aplicable a 'qué clima hace', 'cómo está el tiempo', 'qué tal está
    el clima' o 'dame el pronóstico', aunque podría aportar parte de esos datos.
    Si el pedido combina temperatura con lluvia, sensación térmica o presión,
    corresponde exclusivamente a get_pronostico; no seleccionar esta tool
    para resolver solo una parte. Si pregunta únicamente por sensación
    térmica o temperatura aparente, corresponde a get_sensacion_termica.
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
    - 'decime la temperatura'
    - '¿Cuál es la última temperatura pronosticada para Buenos Aires?'
    - 'Dame el último dato del pronóstico de temperatura en CABA.'
    - '¿Qué temperatura y a qué hora informa el pronóstico de Capital Federal?'
    - 'que temperatura hace'
    - 'hace frio o calor'
    - 'me tengo que abrigar para la temperatura pronosticada?'
    - 'cuantos grados hace en buenos aires?'
    - 'esta fresco afuera?'
    - 'hace mucho calor?'
    - 'esta para salir con campera?'
    - 'me llevo un buzo?'
    - 'salgo en remera o me abrigo?'
    - 'necesito una campera por la temperatura?'
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
        hourly = obtener_datos_horarios(TEMPERATURA_URL)
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
    no es aplicable. Esta herramienta es aplicable solo si el pedido se
    limita a probabilidad de lluvia o paraguas según esa probabilidad.
    Una pregunta general como 'qué clima hace', 'cómo está el tiempo' o
    'dame el pronóstico' corresponde exclusivamente a get_pronostico.
    Si se combina lluvia con temperatura, sensación térmica o presión,
    corresponde exclusivamente a get_pronostico; esta tool no es aplicable
    para responder solo la parte de lluvia de un pedido combinado.

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
        hourly = obtener_datos_horarios(PRECIPITACIONES_URL)
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


@mcp.tool()
def get_sensacion_termica() -> dict:
    """Consulta la sensación térmica pronosticada para Buenos Aires (CABA), Argentina.

    CAPACIDAD Y CUÁNDO USARLA
    Obtiene de Open-Meteo la última temperatura aparente del pronóstico
    horario, junto con su fecha y hora local en GMT-3. Es aplicable cuando
    se pregunta específicamente por sensación térmica o temperatura aparente.
    Sin localidad explícita, usa Buenos Aires (CABA) por defecto, sin pedir
    confirmación. Si el contexto establece otra ciudad, no es aplicable.
    Es aplicable solo si el pedido se limita a sensación térmica o temperatura
    aparente. Para temperatura del aire sola corresponde get_temperatura.
    Para preguntas generales como 'qué clima hace', 'cómo está el tiempo'
    o 'dame el pronóstico', corresponde exclusivamente get_pronostico.
    Si combina sensación térmica con temperatura, lluvias o presión,
    corresponde exclusivamente a get_pronostico; esta tool no es aplicable
    para responder solo una parte del pedido combinado.

    ARGUMENTOS Y RESULTADO
    No recibe argumentos. La ubicación está fijada en latitud -34.6131,
    longitud -58.3772. Devuelve estado='Ok' y respuesta con el formato
    'AAAA-MM-DD HH:MM, SENSACION_TERMICA °C'. El valor está expresado en
    grados Celsius y representa la temperatura aparente, que puede diferir
    de la temperatura del aire. Ante un error devuelve estado='Error',
    respuesta='Error interno' y status_code=500.

    EJEMPLOS DE CONSULTAS APLICABLES
    - 'cual es la sensacion termica?'
    - 'que sensacion termica pronostican para caba?'
    - 'decime la temperatura aparente en buenos aires'
    - 'cuantos grados de sensacion termica hay en capital?'
    - 'dame el ultimo dato del pronostico de sensacion termica'

    ALCANCE Y LÍMITES
    Toma el último registro disponible del pronóstico, que puede ser futuro.
    Se debe informar siempre la fecha y hora del dato y presentarlo como
    sensación térmica pronosticada, no como una medición actual.
    No permite elegir hoy, mañana u otro horario específico. No devuelve
    temperatura del aire, probabilidad de lluvia, presión ni datos de otras
    localidades. No compara temperatura del aire y sensación térmica.
    """
    try:
        hourly = obtener_datos_horarios(SENSACION_TERMICA_URL)
        tiempos = hourly["time"]
        sensaciones = hourly["apparent_temperature"]
        if (
            not isinstance(tiempos, list)
            or not isinstance(sensaciones, list)
            or not tiempos
            or len(tiempos) != len(sensaciones)
        ):
            raise ValueError("Series horarias vacías o inconsistentes")
        sensacion_termica = sensaciones[-1]
        if (
            isinstance(sensacion_termica, bool)
            or not isinstance(sensacion_termica, (int, float))
            or not math.isfinite(sensacion_termica)
        ):
            logging.error("Error en get_sensacion_termica: La última sensación térmica no es un número válido")
            return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}
        # La URL solicitada devuelve fechas sin offset en GMT (UTC).
        fecha_gmt = datetime.fromisoformat(tiempos[-1]).replace(tzinfo=timezone.utc)
        fecha_local = fecha_gmt.astimezone(timezone(timedelta(hours=-3)))
        return {"estado": "Ok", "respuesta": f"{fecha_local:%Y-%m-%d %H:%M}, {sensacion_termica} °C"}
    except Exception as error:
        logging.error("Error en get_sensacion_termica: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}


@mcp.tool()
def get_presion() -> dict:
    """Consulta la presión atmosférica en superficie pronosticada para Buenos Aires (CABA), Argentina.

    CAPACIDAD Y CUÁNDO USARLA
    Obtiene de Open-Meteo la última presión atmosférica en superficie del
    pronóstico horario, junto con su fecha y hora local en GMT-3.
    Es aplicable a preguntas sobre presión atmosférica, presión barométrica
    o presión en superficie. Sin localidad explícita, usa Buenos Aires
    (CABA) por defecto, sin pedir confirmación. Si el contexto indica otra
    ciudad, no es aplicable. Esta herramienta es aplicable solo si el pedido
    se limita a presión atmosférica en superficie. Para preguntas generales
    como 'qué clima hace', 'cómo está el tiempo' o 'dame el pronóstico',
    corresponde exclusivamente get_pronostico. Si combina presión con
    temperatura, lluvias o sensación térmica, corresponde exclusivamente
    a get_pronostico; esta tool no es aplicable para resolver solo una parte.
    No consulta presión arterial ni de neumáticos.

    ARGUMENTOS Y RESULTADO
    No recibe argumentos. La ubicación está fijada en latitud -34.6131,
    longitud -58.3772. Devuelve estado='Ok' y respuesta con el formato
    'AAAA-MM-DD HH:MM, PRESION hPa'. El valor está expresado en hectopascales
    (hPa) y corresponde a la presión en superficie, no a la presión reducida
    al nivel del mar. Ante un error devuelve estado='Error',
    respuesta='Error interno' y status_code=500.

    EJEMPLOS DE CONSULTAS APLICABLES
    - 'cual es la presion atmosferica?'
    - 'que presion barometrica pronostican para caba?'
    - 'decime la presion en superficie en buenos aires'
    - 'cuantos hectopascales indica el pronostico en capital?'
    - 'dame el ultimo dato de presion atmosferica del pronostico'

    ALCANCE Y LÍMITES
    Toma el último registro disponible del pronóstico, que puede ser futuro.
    Se debe informar siempre la fecha y hora del dato y presentarlo como
    presión pronosticada, no como una medición actual. No permite elegir
    hoy, mañana u otro horario específico. No informa tendencias de presión,
    presión al nivel del mar, temperatura, lluvias ni datos de otras localidades.
    """
    try:
        hourly = obtener_datos_horarios(PRESION_URL)
        tiempos = hourly["time"]
        presiones = hourly["surface_pressure"]
        if (
            not isinstance(tiempos, list)
            or not isinstance(presiones, list)
            or not tiempos
            or len(tiempos) != len(presiones)
        ):
            raise ValueError("Series horarias vacías o inconsistentes")
        presion = presiones[-1]
        if (
            isinstance(presion, bool)
            or not isinstance(presion, (int, float))
            or not math.isfinite(presion)
            or presion <= 0
        ):
            logging.error("Error en get_presion: La última presión no es un número positivo válido")
            return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}
        # La URL solicitada devuelve fechas sin offset en GMT (UTC).
        fecha_gmt = datetime.fromisoformat(tiempos[-1]).replace(tzinfo=timezone.utc)
        fecha_local = fecha_gmt.astimezone(timezone(timedelta(hours=-3)))
        return {"estado": "Ok", "respuesta": f"{fecha_local:%Y-%m-%d %H:%M}, {presion} hPa"}
    except Exception as error:
        logging.error("Error en get_presion: %s", error, exc_info=True)
        return {"estado": "Error", "respuesta": "Error interno", "status_code": 500}


@mcp.tool()
def get_pronostico() -> dict:
    """Consulta un pronóstico conjunto de temperatura, lluvias, sensación térmica y presión para CABA.

    Llama a get_temperatura, get_precipitaciones, get_sensacion_termica y
    get_presion, y reúne sus últimos datos pronosticados en un único JSON.
    No recibe argumentos. Sin ciudad explícita usa Buenos Aires (CABA)
    por defecto. No es aplicable si el mensaje o contexto indica otra ciudad.
    Es la herramienta aplicable a preguntas generales sobre el clima, el
    tiempo o el pronóstico sin una variable específica, y a pedidos que
    combinen dos o más de las cuatro variables. No seleccionar las tools
    individuales para resolver fragmentos de esas consultas.

    EJEMPLOS DE CONSULTAS APLICABLES
    - 'que clima hace'
    - 'como esta el tiempo'
    - 'que tal esta el clima en caba?'
    - 'como esta el tiempo en capital?'
    - 'que dice el pronostico del tiempo en buenos aires?'
    - 'dame el pronostico'
    - 'dame todos los datos del tiempo en caba'
    - 'temperatura y lluvia'
    - 'que temperatura y sensacion termica pronostican?'
    - 'decime la presion y las probabilidades de lluvia'
    - 'me llevo campera y paraguas?' (combina temperatura y lluvias).

    CONSULTAS EXCLUIDAS
    No es aplicable cuando se pide una sola variable específica: temperatura
    del aire, sensación térmica, probabilidad de lluvia o presión atmosférica.
    En esos casos usar exclusivamente la herramienta individual correspondiente,
    aunque este pronóstico también contenga ese dato. 'Cuántos grados hace',
    'hace frío o calor' y abrigo por temperatura corresponden a get_temperatura;
    'me llevo un paraguas' corresponde a get_precipitaciones; 'sensación térmica'
    a get_sensacion_termica; 'presión atmosférica' a get_presion.

    Devuelve estado='Ok' si al menos una variable tiene datos válidos.
    respuesta contiene ubicación, zona_horaria='GMT-3', fecha_local común
    cuando existe, fechas_coinciden y datos por variable, con su fecha y
    valor con unidad (°C, % de lluvias o hPa). Las variables que fallan
    indican estado='sin_datos' y 'No hay datos para esa variable'; eso no
    invalida los datos disponibles. Si ninguna tiene datos válidos,
    devuelve estado='Error', status_code=500 y los datos faltantes.

    Compara las fechas y horas. Si difieren, la fecha común es null y
    se incluye una advertencia: informar cada dato con su propio horario.
    Siempre presentar los valores como pronósticos, nunca como condiciones
    actuales. Son los últimos registros disponibles y pueden ser futuros;
    no permite elegir una fecha ni informa todo el día, tendencias o máximas.
    La probabilidad de lluvia no es cantidad de lluvia ni certeza de lluvia.
    La presión es en superficie, no reducida al nivel del mar.
    """
    return combinar_pronostico({
        "temperatura": get_temperatura,
        "precipitaciones": get_precipitaciones,
        "sensacion_termica": get_sensacion_termica,
        "presion": get_presion,
    })


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
