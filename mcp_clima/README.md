# MCP Clima

Servidor FastMCP inspirado en `mcp_cocina`, con cinco herramientas meteorológicas para Buenos Aires (CABA). Todas usan el último registro del pronóstico horario de Open-Meteo y expresan la fecha y hora en GMT-3. El dato puede ser futuro: debe presentarse como pronóstico, no como condición actual.

## Arranque y configuración

Desde esta carpeta, en PowerShell:

```powershell
.\clima\Scripts\python.exe -m pip install -r requirements.txt
.\clima\Scripts\python.exe server.py
```

Si necesitás crear el entorno: `python -m venv clima`. El comando `server.py` inicia el servidor; no ejecuta una prueba individual.

Endpoint MCP: `http://127.0.0.1:8005/mcp` (Streamable HTTP). Para que Jeveador lo consulte, registrá la URL completa en `mcps` con el nombre `mcp_clima` y `habilitado = 1`. Habilitado significa que debe consultarse; el servidor también debe estar encendido.

`server.py` carga explícitamente el `.env` ubicado junto al script mediante `python-dotenv`. Requiere estas cuatro variables, con el formato `NOMBRE=URL`, una por línea:

| Variable | Campo horario del endpoint | Unidad |
| --- | --- | --- |
| `TEMPERATURA_URL` | `temperature_2m` | °C |
| `PRECIPITACIONES_URL` | `precipitation_probability` | % de probabilidad |
| `SENSACION_TERMICA_URL` | `apparent_temperature` | °C |
| `PRESION_URL` | `surface_pressure` | hPa (hectopascales) |

Las URLs deben consultar las coordenadas de CABA (`latitude=-34.6131`, `longitude=-58.3772`) y devolver `hourly.time` en GMT, como los endpoints definidos para este componente. La conversión a GMT-3 se realiza en las herramientas; no configurar el endpoint para devolver horas locales ya convertidas.

Las variables existentes en el proceso tienen prioridad. Si alguna URL falta o está vacía, el arranque informa su nombre sin mostrar valores. La carga automática adicional de `.env` por FastMCP está desactivada. Reiniciá el MCP después de cambiar URLs o descripciones. No hace falta una clave de OpenAI u OpenRouter para ejecutar estas funciones.

## Herramientas y selección

Todas las herramientas carecen de argumentos. Sin localidad explícita, usan CABA por defecto; no son aplicables si el mensaje o contexto indica otra ciudad.

| Herramienta | Consultas que le corresponden |
| --- | --- |
| `get_pronostico()` | Clima o tiempo general, pronóstico completo y pedidos de dos o más variables. |
| `get_temperatura()` | Solo temperatura del aire, grados, frío/calor o abrigo por temperatura. |
| `get_precipitaciones()` | Solo probabilidad de lluvias o paraguas según esa probabilidad. |
| `get_sensacion_termica()` | Solo sensación térmica o temperatura aparente. |
| `get_presion()` | Solo presión atmosférica en superficie o presión barométrica. |

Ejemplos: «qué clima hace», «cómo está el tiempo», «dame el pronóstico», «temperatura y lluvia» y «me llevo campera y paraguas» corresponden a `get_pronostico`. «Cuántos grados hace» corresponde a temperatura; «me llevo un paraguas» a precipitaciones; «cuál es la sensación térmica» a sensación térmica; «cuál es la presión atmosférica» a presión.

Las descripciones excluyen los pedidos generales y combinados de las herramientas individuales, y los pedidos de una sola variable de `get_pronostico`. Estas reglas se publican en los docstrings para orientar a Jev; su selección real debe verificarse con consultas de integración. Los nombres actuales reemplazan las versiones anteriores `clima`, `get_clima` y `mejor_clima`, que no están en el catálogo.

## Consultas individuales

Cada herramienta usa `obtener_datos_horarios(url)` de `funciones.py`, que hace GET con timeout de 30 segundos, valida el estado HTTP y devuelve `hourly`. La herramienta valida las series, toma los últimos elementos de `time` y de su variable, convierte GMT a GMT-3 y devuelve `estado` y `respuesta`.

Ejemplos ficticios:

```json
{"estado": "Ok", "respuesta": "2026-10-18 20:00, 13.2 °C"}
{"estado": "Ok", "respuesta": "2026-10-18 20:00, 80 % de lluvias"}
{"estado": "Ok", "respuesta": "2026-10-18 20:00, 10.5 °C"}
{"estado": "Ok", "respuesta": "2026-10-18 20:00, 1013.2 hPa"}
```

El porcentaje indica probabilidad de precipitaciones, no milímetros, intensidad ni certeza de lluvia. La sensación térmica es temperatura aparente. La presión es en superficie y no está reducida al nivel del mar. Las herramientas no permiten elegir fecha u horario ni informan el día completo, máximas o tendencias.

Los fallos HTTP, de conexión o de datos devuelven `{"estado": "Error", "respuesta": "Error interno", "status_code": 500}`. Ese campo es parte del JSON de negocio y no cambia por sí solo el estado HTTP del protocolo MCP.

## Pronóstico conjunto

`get_pronostico()` llama a las cuatro funciones individuales mediante `combinar_pronostico()` de `funciones.py`. Las consultas se ejecutan en paralelo, manteniendo el manejo de errores por variable. La API realiza una sola llamada MCP y permite hasta 60 segundos para esta herramienta; las consultas individuales conservan su timeout HTTP de 30 segundos.

Devuelve `estado: Ok` si al menos una variable tiene datos válidos. Una variable que falla indica `estado: sin_datos` y `No hay datos para ...`, sin descartar las demás.

Ejemplo ficticio de respuesta parcial:

```json
{
  "estado": "Ok",
  "respuesta": {
    "ubicacion": "Buenos Aires (CABA)",
    "zona_horaria": "GMT-3",
    "fecha_local": "2026-10-18 20:00",
    "fechas_coinciden": true,
    "datos": {
      "temperatura": {"estado": "Ok", "fecha_local": "2026-10-18 20:00", "valor": "13.2 °C"},
      "precipitaciones": {"estado": "Ok", "fecha_local": "2026-10-18 20:00", "valor": "80 % de lluvias"},
      "sensacion_termica": {"estado": "sin_datos", "respuesta": "No hay datos para sensacion_termica"},
      "presion": {"estado": "Ok", "fecha_local": "2026-10-18 20:00", "valor": "1013.2 hPa"}
    }
  }
}
```

Compara las fechas y horas de los datos válidos. Si coinciden, incluye una fecha común. Si difieren, `fecha_local` es `null`, `fechas_coinciden` es `false` y agrega una advertencia; cada variable conserva su propio horario. No se presentan datos de horarios diferentes como simultáneos.

Si las cuatro consultas fallan o sus respuestas no contienen datos utilizables, devuelve `estado: Error`, `respuesta: No hay datos para ninguna variable del pronóstico`, `status_code: 500` y `datos` con los faltantes. La API reconoce el error de negocio como `error_mcp` y redacta el fallo. Una respuesta parcial con estado general `Ok` conserva el éxito.

La redacción del pronóstico conjunto debe incluir las fechas, horas, unidades y zona GMT-3, informar las variables faltantes y respetar horarios diferentes. No debe presentar el último registro como temperatura o condiciones actuales.

## Verificación

Pruebas del agregador con funciones simuladas, sin importar el servidor ni cargar `.env`:

```powershell
.\clima\Scripts\python.exe -m unittest test_pronostico -v
```

Cubren las 16 combinaciones de éxito/fallo, fechas diferentes, excepciones, respuestas malformadas y llamada a las cuatro funciones. La implementación completó estas 4 pruebas y 42 pruebas de coordinación/redacción de la API con dependencias simuladas. La revisión posterior de descripciones verificó su sintaxis y alcance. Estos resultados no garantizan las decisiones de Jev ni el texto exacto de los modelos en producción.

Las pruebas que importan `server.py` cargan su configuración: ejecutalas localmente fuera de las herramientas del agente cuando requieran el `.env` real.
