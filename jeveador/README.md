# Jeveador

Servicio FastAPI que evalúa qué MCP y herramientas pueden resolver un pedido. Lee el catálogo SQLite, descubre las herramientas de los MCP habilitados y envía mensaje, contexto y capacidades a Jev mediante OpenRouter. Devuelve una evaluación para que la API coordine el chat; no ejecuta las herramientas.

## Arranque

Desde esta carpeta, en PowerShell, con Python 3.10 o superior:

```powershell
# Solo si todavía no existe el entorno.
python -m venv jeveador
.\jeveador\Scripts\python.exe -m pip install -r reqs.txt
.\jeveador\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002 --reload
```

Swagger: http://127.0.0.1:8002/docs. Endpoint: POST http://127.0.0.1:8002/evaluar.
La base debe estar inicializada y todos los MCP habilitados deben estar encendidos. La [API](../api/README.md) consume esta evaluación y ejecuta las herramientas por separado.

## Configuración

funciones/entorno.py carga la configuración local junto al componente. Las variables existentes en el proceso tienen prioridad.

| Variable | Uso |
| --- | --- |
| JEV_KEY | Credencial de OpenRouter. |
| JEV_URL | Endpoint externo de decisiones; no es la URL local de este servicio. |
| JEV_MODELO | Identificador del modelo de decisiones. |
| CADENA | Archivo SQLite compartido con la API; rutas relativas desde jeveador. |
| UMBRAL_DEFECTO | Respaldo decimal si falla config_umbral; 0.5 si falta o no se puede convertir. |
| MAX_CONTEXTO | Entero positivo; 20 por defecto. Igual en Página y API. |

Usá la misma ruta absoluta de CADENA que la API. Para inicializar tablas, consultá [sqlserver](../sqlserver/README.md). Reiniciá Jeveador después de cambiar configuración.

La inicialización opcional `crear_tabla_mcps()` crea el catálogo con dos registros: `mcp_finanzas`, URL `http://127.0.0.1:8006/mcp`, y `mcp_clima`, URL `http://localhost:8005/mcp`, ambos con `habilitado = 1`. Solo los inserta si la tabla no existe; no modifica ni repuebla catálogos existentes. El esquema SQL compartido es otro camino de inicialización y deja el catálogo vacío. Esta función no arranca los servidores MCP.

## Evaluación y selección

Ejemplo de entrada:

```json
{"mensaje": "¿Cuántos euros son 100 dólares estadounidenses?", "contexto": []}
```

contexto es opcional. La respuesta incluye intencion, mcp_recomendado, evaluaciones y capacidades. Las evaluaciones identifican MCP, cobertura, motivo, herramientas aplicables y necesidad de aclaración. La cobertura puede ser sirve, sirve_parcialmente, no_sirve o falta_informacion.

Cuando la intención es consultar_capacidades, devuelve los catálogos disponibles y deja evaluaciones vacías y recomendación null. La API redacta esa información para el usuario. En una consulta concreta, aplica el umbral antes de entregar las herramientas aceptadas: la decisión debe ser aplicable y confidence debe superar estrictamente el umbral. Una confianza igual al umbral, ausente o menor se descarta.

El catálogo y el umbral se consultan en cada petición. Una recomendación sin herramientas aceptadas se descarta. Si hay ambigüedad, puede devolver recomendación null conservando las evaluaciones; la API utiliza esos datos para pedir aclaración.

## Organización y consumo

| Ubicación | Contenido |
| --- | --- |
| main.py y routers/jev.py | Aplicación y POST /evaluar. |
| schemas/jev.py | Entrada y respuesta. |
| funciones/entorno.py y contexto_config.py | Configuración y límite de contexto. |
| funciones/mcp_funciones.py | Transporte y descubrimiento MCP, incluida paginación. |
| funciones/jev_funciones.py | Solicitud a Jev, validación y filtro de decisiones. |
| funciones/bases_sqlite.py | Catálogo, umbral y persistencia. |
| funciones/billing.py | Registro del consumo de Jev. |
| tests/ | Pruebas del servicio y SQLite. |

Jev registra su uso en billing con metodo y herramientas iguales a JEV. El costo proviene de usage.cost; no aplica las tarifas locales de OpenAI. Los resultados de herramientas y el JSON de decisiones no se guardan en esa tabla. No se emite el log INFO por herramienta con MCP, decisión, confianza y probabilidades. El cálculo de selección, el filtro de umbral y el guardado del consumo continúan funcionando.

## Pruebas

Desde jeveador:

```powershell
.\jeveador\Scripts\python.exe -m unittest discover -s tests -t . -v
```

La suite sustituye la carga de configuración y simula HTTP, catálogos, decisiones y billing. Las operaciones SQLite usan archivos temporales. Cubre descubrimiento, paginación, selección, capacidades, umbral, errores y persistencia sin servicios ni bases reales.

## Límites

Un MCP habilitado que falla al publicar su catálogo interrumpe la evaluación, aunque la pregunta pudiera responderla otro. Deshabilitá o eliminá del catálogo los servidores que retires. No hay memoria persistente de conversaciones ni caché local de catálogos. La disponibilidad real de MCP y proveedor, y la selección del modelo, requieren verificación de integración.
