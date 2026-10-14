# API de Jevraulio

Servicio FastAPI que coordina el chat, descubre y ejecuta herramientas MCP, consulta Jeveador y usa OpenAI para preparar argumentos y redactar respuestas. También publica la administración SQL que consume la página. La evaluación de capacidades corresponde a Jeveador; la ejecución corresponde a esta API.

## Arranque

Desde esta carpeta, en PowerShell, con Python 3.10 o superior:

```powershell
# Solo si todavía no existe el entorno.
python -m venv api
.\api\Scripts\python.exe -m pip install -r reqs.txt
.\api\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload --log-config logging.json
```

API: http://127.0.0.1:8001. Swagger: http://127.0.0.1:8001/docs.
Para el chat con Jeveador, arrancá también Jeveador y los MCP habilitados. Las rutas administrativas requieren la base SQLite, pero no llamadas a OpenAI.

## Configuración

Los módulos cargan el archivo local de configuración junto al componente con python-dotenv. Configurá estos nombres localmente; las credenciales no se envían al navegador ni se publican en documentación.

| Variable | Uso |
| --- | --- |
| API_KEY | Credencial de OpenAI para los chats con LLM. |
| MODELO_OPENAI | Modelo; fallback gpt-4.1-mini. |
| JEV_URL | Dirección local de Jeveador, base o endpoint completo /evaluar. |
| CADENA | Ruta SQLite compartida con Jeveador; una ruta relativa se resuelve desde api. |
| MAX_CONTEXTO | Máximo de mensajes de contexto; 20 por defecto. Igual en API, Jeveador y Página. |

Usá la misma ruta absoluta de CADENA en API y Jeveador. La base debe tener las tablas de [sqlserver](../sqlserver/README.md). El arranque ya no consulta la tabla errores: las descripciones de /chat/jev se declaran en su router. Reiniciá el servicio después de cambiar configuración.

## Rutas y flujo

| Ruta | Responsabilidad |
| --- | --- |
| POST /chat/jev | Consulta Jeveador, selecciona MCP y herramienta, valida argumentos, ejecuta y redacta. |
| GET /consultas_sql/costos | Consumos paginados, filtros y totales. |
| GET/POST /consultas_sql/mcps | Listar o dar de alta MCP, siempre deshabilitado al crear. |
| GET/PATCH/DELETE /consultas_sql/mcps/{id_mcp} | Consultar, cambiar habilitación o borrar un registro. |
| GET/PUT /consultas_sql/umbral | Consultar o guardar el umbral decimal. |

Ejemplo de entrada de /chat/jev: {"mensaje": "Convertí 100 USD a EUR", "contexto": []}. El campo contexto es opcional. La respuesta pública contiene estado, respuesta en lenguaje natural y herramientas ejecutadas. Si faltan datos o hay ambigüedad, puede pedir aclaración sin ejecutar MCP. Las consultas de capacidades describen catálogos sin ejecutar herramientas.

## Respuestas y manejo de errores

Todo el procesamiento de `routers/chat_jev.py` está dentro del `try`: la llamada a `responder_chat_jev`, la lectura del resultado y la construcción de `RespuestaChat`.

| Resultado | Respuesta pública |
| --- | --- |
| Respuesta válida, aclaración o ausencia de herramientas | HTTP 200 con `estado`, `respuesta` y `herramientas`. |
| Resultado de negocio `error_mcp` | HTTP 200 con el texto precedido por «La herramienta informó un error: ». |
| `HTTPException as e` | Conserva `e.status_code`, `e.detail` y `e.headers` mediante `JSONResponse`. |
| `Exception as e` inesperada | HTTP 500 con un detalle público genérico. |
| Entrada inválida | FastAPI responde HTTP 422 antes de ejecutar el cuerpo del endpoint. |

Ambos bloques `except` capturan la excepción como `e`, la incluyen en `logger.error` y devuelven una respuesta sin `raise`. Los fallos HTTP conocidos conservan su código: normalmente 502 por servicios o respuestas inválidas, 503 por configuración o catálogo y 504 por timeout. Un fallo al construir la respuesta también queda capturado por el bloque genérico.

Ejemplo ilustrativo de un fallo HTTP 503:

```json
{"detail": "Configuración o catálogo no disponible."}
```

El detalle concreto proviene de la excepción. Ante un fallo inesperado se devuelve HTTP 500:

```json
{"detail": "Error interno al procesar la respuesta del chat."}
```

El detalle interno se registra en consola y no se agrega a ese cuerpo público. Esta respuesta de chat utiliza `detail`; la administración SQL conserva su contrato `resultado/salida`.

Los endpoints administrativos devuelven {"resultado": bool, "salida": datos} y conservan los códigos HTTP de error. Las operaciones SQL internas devuelven (resultado, salida). El detalle de rutas y contratos está en el [README general](../README.md#api-administrativa-sql).

## Organización

| Ubicación | Contenido |
| --- | --- |
| main.py y routers/ | Aplicación y rutas HTTP. |
| schemas/ | Contratos y validación. |
| funciones/chat_jev_funciones.py | Selección, preparación y ejecución con Jeveador. |
| funciones/respuesta_jev_funciones.py | Aclaraciones, capacidades y redacción. |
| funciones/mcp_funciones.py y openai_funciones.py | Cliente MCP compartido y cliente OpenAI. |
| funciones/base_sqlite.py y consultas_sql_funciones.py | Persistencia y administración SQL. |
| funciones/billing.py | Estimaciones y guardado de consumo. |
| logging.json | Configuración de consola. |
| tests/ | Suites de pruebas. |

## Pruebas

Desde api:

```powershell
.\api\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Las pruebas usan HTTP simulado y bases temporales. Bloquean la carga de configuración local antes de importar los módulos que la usan; no consultan proveedores reales. Cubren /chat/jev, ausencia de rutas retiradas, descubrimiento y ejecución MCP, cliente OpenAI, coordinación, redacción, contexto, billing y administración SQL.

La última ejecución de la suite completó **80 pruebas aprobadas**, incluidas la conservación de códigos y cabeceras HTTP, el log de la excepción y los fallos al construir la respuesta. Esta actualización documental no volvió a ejecutar la suite.

## Límites

/chat/jev ejecuta como máximo una herramienta por petición. El contexto lo envía el cliente y no persiste en el servidor. Las llamadas reales a proveedores registran consumo en billing; un fallo de persistencia puede interrumpir la respuesta. El éxito de las pruebas simuladas no garantiza la selección real de los modelos. Consultá el README general para timeouts y pendientes.
