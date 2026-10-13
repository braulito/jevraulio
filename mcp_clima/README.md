# MCP Clima

Servidor inspirado en `mcp_cocina`, construido con FastMCP del SDK oficial de MCP.

Desde esta carpeta, en PowerShell:

```powershell
.\clima\Scripts\python.exe -m pip install -r requirements.txt
.\clima\Scripts\python.exe server.py --servidor
```

Si necesitás crear el entorno: `python -m venv clima`.

Endpoint MCP: `http://127.0.0.1:8005/mcp` (Streamable HTTP).
No necesita claves ni archivos `.env`; se desactiva su carga automática en FastMCP.

- `clima()`: hace GET a `https://api.open-meteo.com/v1/forecast?latitude=-34.6131&longitude=-58.3772&hourly=temperature_2m`, toma los últimos elementos de `hourly.time` y `hourly.temperature_2m`, convierte la fecha de GMT a GMT-3 y devuelve, por ejemplo, `{"estado": "Ok", "respuesta": "2026-10-18 20:00, 21.5 °C"}`.
- `mejor_clima()`: conserva la preferencia fija de demostración: `{"estado": "Ok", "respuesta": "Templado"}`.

Las herramientas no requieren argumentos. `clima()` devuelve el último dato del pronóstico, no necesariamente el tiempo actual. La consulta tiene un timeout de 30 segundos. Los errores HTTP, de conexión o de datos devuelven `estado: Error`, `respuesta: Error interno` y `status_code: 500`; ese campo no modifica el estado HTTP de MCP.

Para probar `get_clima()` directamente, sin iniciar el servidor:

```powershell
.\clima\Scripts\python.exe server.py
```

Este comando hace una consulta real y muestra el JSON. Sale con código 1 si falla.

Los nombres, descripciones y esquemas se publican mediante `@mcp.tool()`. Reiniciá el servidor después de modificar las herramientas.
Para que Jeveador lo descubra, registrá en la tabla `mcps` de tu base configurada el nombre `mcp_clima`, la URL `http://127.0.0.1:8005/mcp` y `habilitado = 1`.

Pruebas de conversión de fecha, errores y ejecución MCP en memoria, con respuestas HTTP simuladas:

```powershell
.\clima\Scripts\python.exe -m unittest test_list_tools -v
```

Referencia de fechas GMT y temperatura Celsius: [documentación de Open-Meteo](https://open-meteo.com/en/docs).
