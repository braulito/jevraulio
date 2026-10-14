# Página de Jevraulio

Aplicación Flask con el chat y las pantallas de Costos, Umbral y MCPs. El navegador conserva el contexto del chat en la pestaña; Flask se comunica con la API por HTTP. La administración actual usa los endpoints SQL de la API.

## Arranque

Desde esta carpeta, en PowerShell:

```powershell
# Solo si todavía no existe el entorno.
python -m venv pagina
.\pagina\Scripts\python.exe -m pip install -r requirements.txt
.\pagina\Scripts\python.exe app.py
```

Abrí http://127.0.0.1:8000/. Para usar el chat con selección de herramientas, arrancá también API, Jeveador y los MCP habilitados. Costos, Umbral y MCPs requieren la API y sus tablas SQLite.

## Configuración

crear_app() carga la configuración local junto a app.py; no se envían credenciales al navegador. Los clientes administrativos leen sus URLs al importar funciones.py: reiniciá Flask después de cambiarlas.

| Variable | Uso y ejemplo local |
| --- | --- |
| API_URL | URL completa del chat; http://127.0.0.1:8001/chat/jev. |
| API_COSTOS_URL | http://127.0.0.1:8001/consultas_sql/costos. |
| API_MCPS_URL | http://127.0.0.1:8001/consultas_sql/mcps. |
| API_MCP_URL | http://127.0.0.1:8001/consultas_sql/mcps/{id_mcp}; conservar el marcador. |
| API_UMBRAL_URL | http://127.0.0.1:8001/consultas_sql/umbral. |
| MAX_CONTEXTO | Entero positivo; 20 por defecto. Igual en API y Jeveador. |
| PAGINA_SIZE | Registros por página; 50 si falta o es inválido. |

CADENA se conserva para el módulo anterior bases.py, que las páginas administrativas actuales no utilizan. JEV_ADMIN_URL, JEV_ADMIN_TOKENS y JEV_ADMIN_KEY pertenecen a clientes auxiliares en funciones.py: Costos no los consulta automáticamente.

## Pantallas y comportamiento

| Ruta | Uso |
| --- | --- |
| GET / y /index.html | Chat y contexto de pestaña. |
| POST /chat | Envía mensaje y contexto al endpoint API_URL. |
| GET /costos y /costos.html | Consumos paginados, filtros y totales por grupo. |
| GET/POST /umbral y /umbral.html | Consulta y edición del umbral como porcentaje. |
| GET/POST /mcps y /mcps.html | Catálogo e interruptores de habilitación. |
| POST /mcps/agregar | Alta de nombre y URL, siempre deshabilitado. |
| GET/POST /mcps/<id_mcp>/borrar | Confirmación y borrado mediante POST. |

El `/chat` de Flask es la ruta interna del formulario del navegador; el endpoint de chat de la API es exclusivamente `/chat/jev`. Si API_URL conserva `/chat`, el cliente lo transforma en `/chat/jev`; también acepta una URL base.

El chat acepta respuestas de la API con HTTP 200, estado Ok y texto en respuesta. cliente_api.py espera hasta 200 segundos. El historial se pierde al recargar y no persiste en el servidor.

Costos muestra fechas en GMT-3, importes en USD y totales separados para Jev y OpenAI. Los totales corresponden al grupo completo, independientemente de la página. Umbral convierte el porcentaje visible a decimal: 85 equivale a 0.85. Los formularios administrativos usan tokens CSRF y el borrado requiere confirmación.

Los clientes de operaciones devuelven (resultado, salida) y comprueban el contrato {"resultado": bool, "salida": datos} de la API. Los fallos administrativos muestran el modal compartido. Un 404 en los listados de Costos o MCPs muestra ausencia de información en el lugar de la tabla, sin modal; en escrituras, consultas individuales y Umbral sigue siendo un error.

## Organización

| Ubicación | Contenido |
| --- | --- |
| app.py | Factoría crear_app, rutas, formularios y renderizado. |
| cliente_api.py | Cliente HTTP del chat. |
| funciones.py | Clientes administrativos de la API y auxiliares de Jev. |
| bases.py | Acceso SQLite anterior, conservado sin uso en la administración actual. |
| templates/ | Pantallas y parciales compartidos. |
| static/ | CSS, JavaScript y bibliotecas de presentación. |
| tests/ | Clientes y pantallas con respuestas simuladas. |

## Pruebas

Desde pagina:

```powershell
.\pagina\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Las pruebas crean la aplicación con crear_app(cargar_entorno=False), usan valores ficticios y simulan las respuestas HTTP. No cargan configuración local ni requieren servicios o una base real. Cubren chat, contexto, errores, formularios, CSRF, modal, paginación y la excepción de listados vacíos.
