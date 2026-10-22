# API de JEVraulio

Servicio FastAPI que recibe las consultas del chat, pide a Jeveador que evalúe los MCP habilitados y coordina la ejecución. Usa OpenAI para preparar argumentos, pedir aclaraciones y redactar respuestas. También publica la administración de SQLite que consume la página.

Jeveador recomienda; esta API autoriza y ejecuta. La recomendación del modelo no concede permisos.

## Arranque

Desde `api/`, con Python 3.10 o superior, en PowerShell:

~~~powershell
# Crear el entorno solo la primera vez.
python -m venv api
.\api\Scripts\python.exe -m pip install -r reqs.txt
.\api\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload --log-config logging.json
~~~

Con el entorno activado se puede usar directamente `uvicorn main:app --host 127.0.0.1 --port 8001 --reload --log-config logging.json`.

- Servicio: http://127.0.0.1:8001.
- Swagger: http://127.0.0.1:8001/docs.
- El chat necesita Jeveador, los MCP habilitados y los proveedores utilizados por cada consulta.
- La administración SQL necesita la base existente, sin llamadas a los modelos.

## Configuración

La configuración local se carga automáticamente con python-dotenv; no se indica su ruta en el comando de arranque. Preparar localmente estas variables, sin publicar sus valores:

| Variable | Responsabilidad |
| --- | --- |
| API_KEY | Credencial de OpenAI. |
| MODELO_OPENAI | Modelo para preparación y redacción; fallback gpt-4.1-mini. |
| JEV_URL | URL **local de Jeveador**, base o endpoint completo /evaluar. |
| CADENA | Ruta de la base SQLite compartida. Usar la misma ruta absoluta en API y Jeveador. |
| MAX_CONTEXTO | Máximo de mensajes de contexto, 20 por defecto. Mantenerlo igual en Página y Jeveador. |

Las rutas relativas de SQLite se interpretan desde el componente. La estructura e inicialización están en [sqlserver](../sqlserver/README.md). La administración abre una base existente: no crea una base vacía para reemplazar una ruta incorrecta. Reiniciar el servicio después de cambiar variables de configuración.

Además, [politica_mcp.json](politica_mcp.json) define los destinos y herramientas autorizados. Es configuración local sin credenciales y se relee en cada comprobación.

## Chat: POST /chat/jev

~~~json
{
  "mensaje": "Convertí 100 USD a EUR",
  "contexto": []
}
~~~

El mensaje debe tener entre 1 y 10000 caracteres y no puede contener solo espacios. El contexto es opcional: lista de mensajes no vacíos de hasta 10000 caracteres cada uno, limitada por MAX_CONTEXTO. El campo opcional mcp permite indicar la selección cuando hay varias coincidencias; no evita la evaluación ni las comprobaciones de permisos.

El flujo es:

1. Consultar POST /evaluar de Jeveador con mensaje y contexto.
2. Si se preguntan capacidades, describir el catálogo actual sin ejecutar herramientas.
3. Para una consulta concreta, comprobar la recomendación y las herramientas aceptadas. Pedir aclaración o selección si corresponde.
4. Volver a descubrir el catálogo, comprobar permisos y preparar argumentos. Validarlos contra el JSON Schema de la herramienta.
5. Comprobar nuevamente la autorización justo antes de ejecutar **como máximo una herramienta**.
6. Validar el resultado y redactar la respuesta final con el modelo sin herramientas disponibles.

La respuesta pública conserva este contrato:

~~~json
{
  "estado": "Ok",
  "respuesta": "Texto de respuesta; puede contener Markdown.",
  "herramientas": ["convertir_divisas"]
}
~~~

Una aclaración, una descripción de capacidades o un pedido fuera de alcance devuelve HTTP 200 y herramientas vacías. Cuando no hay herramientas se informa: «No tengo las herramientas necesarias para responder tu pregunta». La falta de capacidades es un resultado válido.

Los estados de coordinación internos no se publican como estados adicionales del chat. Si un MCP informa un error de negocio, se conserva HTTP 200 y estado Ok, con el texto precedido por «La herramienta informó un error: ».

## Administración SQL

Todas estas rutas usan el sobre {"resultado": true, "salida": datos}. Ante un fallo conservan el HTTP correspondiente y devuelven {"resultado": false, "salida": {"status_code": codigo}}, incluida la validación HTTP 422.

| Método y ruta | Entrada / comportamiento |
| --- | --- |
| GET /consultas_sql/costos | pagina=1, pagina_size=50, mostrar_jev=true, mostrar_openai=true. Registros, paginación y totales. |
| GET /consultas_sql/mcps | Todos los MCP, habilitados y deshabilitados. |
| POST /consultas_sql/mcps | {"nombre":"mcp_ejemplo","url":"http://127.0.0.1:8010/mcp"}. Crea **deshabilitado**, HTTP 201. |
| GET /consultas_sql/mcps/{id_mcp} | Consulta por ID positivo. |
| PATCH /consultas_sql/mcps/{id_mcp} | {"habilitado":1} o {"habilitado":0}. |
| DELETE /consultas_sql/mcps/{id_mcp} | Borra el registro. |
| GET /consultas_sql/umbral | Lee id=1 de config_umbral. |
| PUT /consultas_sql/umbral | {"valor":0.85}. Actualiza el registro existente; número finito entre 0 y 1. |

Costos devuelve registros, pagina, total_paginas, total_registros, desde, hasta, filtros y totales costo_jev, costo_openai, tokens_jev y tokens_openai. Los filtros afectan los registros paginados; los totales por grupo se calculan sobre la tabla completa. Una lista vacía puede ser una respuesta exitosa.

Los errores distinguen datos inválidos (400), registro inexistente (404), conflicto (409), validación (422), base o tabla no disponible (503) y fallo interno (500). En la página, un 404 de **listados** de Costos o MCPs representa ausencia de información y se muestra junto a la tabla; los demás errores, incluidas escrituras y Umbral, abren el modal.

## Permisos y destinos

La política local vincula **nombre de MCP + URL + herramientas**. Actualmente autoriza:

| MCP | Destino | Herramientas |
| --- | --- | --- |
| mcp_clima | http://127.0.0.1:8005/mcp | get_temperatura, get_precipitaciones, get_sensacion_termica, get_presion, get_pronostico |
| mcp_finanzas | http://127.0.0.1:8006/mcp | convertir_divisas, get_tipos_cambio, get_monedas, get_proveedores |

El coordinador comprueba ese vínculo al preparar la selección y nuevamente antes de ejecutar; el cliente MCP también exige autorización de herramienta y destino. Una revocación no queda en caché. Un permiso ausente devuelve 403; una política ausente o inválida, 503. Los permisos son globales y se administran en el JSON local, sin una tabla o endpoint adicional de permisos.

Solo se admiten destinos MCP HTTP loopback con puerto explícito: localhost, 127.0.0.1 o ::1. Las rutas vacía, /, /mcp y /mcp/ se normalizan a /mcp. Se rechazan credenciales, parámetros, fragmentos, espacios, otros hosts y variantes numéricas alternativas. localhost se convierte en 127.0.0.1 antes de conectar, sin resolver DNS; IPv6 requiere su propia autorización. El cliente no sigue redirecciones. Estos controles no restringen las consultas externas que un MCP realiza internamente a su proveedor.

Para agregar o cambiar un MCP:

1. Revisar el servidor, su destino y las herramientas que se permitirán ejecutar.
2. Autorizar el destino en [destinos_mcp.json de Jeveador](../jeveador/destinos_mcp.json).
3. Agregar nombre, destino y herramientas aprobadas a [politica_mcp.json](politica_mcp.json).
4. Registrar el MCP mediante la administración SQL y habilitarlo cuando esté disponible.

Estar habilitado en SQLite o aparecer en el catálogo no concede permisos. Las capacidades se descubren en cada evaluación; sus descripciones no se mantienen en la base. Una herramienta nueva también necesita aprobación en la política de ejecución.

## Validación de catálogos y resultados

El catálogo redescubierto admite hasta 64 herramientas y 64 páginas, descripciones de hasta 8192 caracteres, esquemas de hasta 64 KiB y catálogo de hasta 512 KiB. Los esquemas deben ser objetos válidos, sin referencias externas, con hasta 32 niveles y 10000 nodos.

Los resultados solo admiten bloques de texto y/o un objeto structuredContent: hasta 32 bloques, 64 KiB UTF-8 por bloque, 128 KiB totales, 16 niveles y 10000 nodos. Se rechazan números JSON no finitos, imágenes, audio y recursos. Solo se trasladan content textual, structuredContent e isError; se eliminan metadatos y campos desconocidos. Un resultado inválido devuelve 502 antes de la redacción. Los límites se aplican después de recibir y decodificar la respuesta, no como límite del transporte HTTP.

El texto externo sigue siendo contenido no confiable. Estas barreras controlan destinos, permisos y estructura; no garantizan veracidad ni inmunidad del modelo ante toda manipulación. El umbral de Jeveador mide aceptación de una clasificación, no autorización de ejecución. La autenticación administrativa queda fuera del alcance de estos cambios.

## Errores y consumo

El chat devuelve {"detail":"..."} para errores técnicos. Conserva códigos y cabeceras de excepciones HTTP conocidas: 403 por permisos, 502 por servicios o respuestas inválidas, 503 por configuración o catálogo, 504 por timeout. La entrada inválida responde 422 y un fallo inesperado responde 500 con detalle genérico. El router registra la excepción y cubre también la construcción de la respuesta pública.

Las llamadas a OpenAI registran tokens y costo estimado en billing. La estimación usa las tarifas definidas en el código; no representa una factura del proveedor. El consumo de Jev lo registra Jeveador en la misma base. Un fallo de persistencia puede interrumpir la consulta. El contexto de conversación no persiste en la API.

## Organización

| Ubicación | Responsabilidad |
| --- | --- |
| main.py | Crea FastAPI y registra routers. |
| routers/chat_jev.py, routers/consultas_sql.py | Contratos HTTP. |
| schemas/ | Entradas, salidas y validación. |
| funciones/chat_jev_funciones.py | Coordinación, preparación y ejecución. |
| funciones/respuesta_jev_funciones.py | Aclaraciones, capacidades y redacción. |
| funciones/mcp_funciones.py, funciones/openai_funciones.py | Clientes MCP y OpenAI. |
| funciones/seguridad_mcp.py, politica_mcp.json | Permisos, destinos y validación de catálogo y resultados. |
| funciones/base_sqlite.py, funciones/consultas_sql_funciones.py | Persistencia y administración. |
| funciones/billing.py | Estimación y registro del consumo. |
| logging.json | Configuración de consola. |
| tests/ | Pruebas aisladas e integración optativa. |

Las operaciones SQL y los controles de seguridad devuelven (resultado, salida): (True, datos) o (False, {"status_code": codigo}). Los routers adaptan esos retornos al contrato público correspondiente. El chat mantiene sus modelos y excepciones HTTP internas.

## Pruebas

Desde api/:

~~~powershell
.\api\Scripts\python.exe -m unittest discover -s tests -t . -v
~~~

La suite aislada simula servicios externos, utiliza bases temporales y bloquea la carga de configuración local antes de importar los módulos. Cubre coordinación, contexto, contratos HTTP, administración, consumo, permisos, revocaciones, destinos y catálogos/resultados adversariales.

Las pruebas contra servicios encendidos son optativas y no forman parte del descubrimiento anterior:

~~~powershell
.\api\Scripts\python.exe tests\pruebas_integracion_viva.py
~~~

Este segundo comando requiere los componentes y proveedores disponibles y puede generar consumo real y registros de billing. Escribe evidencia de integración en resultados_pruebas/.evidencias/.

La ejecución registrada completó **96 pruebas aisladas de API** y **9 pruebas HTTP de integración**, todas aprobadas. Los [informes individuales](../resultados_pruebas/index.html) distinguen simulaciones y solicitudes reales; incluyen también 68 pruebas de Jeveador. Son evidencia de esa ejecución, no garantía para futuras respuestas de modelos o proveedores. Esta actualización documental no volvió a ejecutar las pruebas.

Volver al [README general](../README.md).
