# **JEV**_raulio_

Chat modular con selección de herramientas MCP. **Jeveador evalúa qué capacidades sirven para el pedido; la API comprueba permisos y ejecuta; la página presenta la respuesta.** Los MCP incluidos son Clima y Finanzas.

Actualizado el 21 de octubre de 2026 a partir del código y de los README de los componentes. Esta actualización es documental: no ejecuta servicios, no consulta bases reales ni accede a archivos de entorno.

El proyecto se desarrolló mediante **vibe coding**, con asistencia de inteligencia artificial y verificación manual de su autor. Las pruebas automatizadas complementan esa revisión.

## Documentación

| Componente | Responsabilidad | README |
| --- | --- | --- |
| API | Coordinación del chat, autorización, ejecución MCP y administración SQL. | [API](api/README.md) |
| Jeveador | Descubrimiento de capacidades y evaluación con Jev/OpenRouter. | [Jeveador](jeveador/README.md) |
| MCP Clima | Pronóstico horario de CABA mediante Open-Meteo. | [Clima](mcp_clima/README.md) |
| MCP Finanzas | Puente al MCP externo de Frankfurter. | [Finanzas](mcp_finanzas/README.md) |
| Página | Interfaz Flask: chat, Costos, Umbral y MCPs. | [Página](pagina/README.md) |
| SQLite | Esquema e inicialización de la base compartida. | [Persistencia](sqlserver/README.md) |
| Resultados de pruebas | Evidencia individual, alcance y regeneración de informes HTML. | [Informes](resultados_pruebas/index.html) · [Generación](resultados_pruebas/README.md) |

## Arquitectura

~~~mermaid
flowchart LR
    U[Usuario] --> P[Página Flask :8000]
    P --> A[API FastAPI :8001]
    A --> J[Jeveador FastAPI :8002]
    J --> V[Jev / OpenRouter]
    J -->|Descubrir capacidades| C[MCP Clima :8005]
    J -->|Descubrir capacidades| F[MCP Finanzas :8006]
    A --> L[OpenAI: argumentos y redacción]
    A -->|Autorizar y ejecutar| C
    A -->|Autorizar y ejecutar| F
    C --> O[Open-Meteo]
    F --> R[MCP Frankfurter]
    A --> D[(SQLite compartido)]
    J --> D
~~~

El navegador se comunica con Flask; Flask llama a la API y esta llama a Jeveador. Jeveador no ejecuta herramientas. La API consulta nuevamente el catálogo del MCP seleccionado, prepara y valida argumentos, aplica su política local y ejecuta como máximo una herramienta por petición.

La carpeta sqlserver contiene SQLite: no hace falta Microsoft SQL Server ni un backend Node.js.

| Servicio | Dirección de desarrollo |
| --- | --- |
| Página | http://127.0.0.1:8000/ |
| API | http://127.0.0.1:8001/docs |
| Jeveador | http://127.0.0.1:8002/docs |
| MCP Clima | http://127.0.0.1:8005/mcp |
| MCP Finanzas | http://127.0.0.1:8006/mcp |

Los puertos de API y Jeveador se indican al iniciar Uvicorn. Los MCP usan los definidos en sus servidores.

## Puesta en marcha

Requiere Python 3.10 o superior y un entorno virtual por componente. Instalar dependencias desde cada carpeta siguiendo su README:

| Carpeta | Dependencias | Entorno usado en los comandos documentados |
| --- | --- | --- |
| api | reqs.txt | api |
| jeveador | reqs.txt | jeveador |
| pagina | requirements.txt | pagina |
| mcp_clima | requirements.txt | clima |
| mcp_finanzas | requirements.txt | mcp_finanzas |

1. Preparar la configuración local de Página, API, Jeveador y Clima. Finanzas no carga archivos de entorno.
2. Inicializar SQLite con [el esquema compartido](sqlserver/README.md#inicialización-local). API y Jeveador deben apuntar al mismo archivo.
3. Revisar las políticas locales de descubrimiento y ejecución descritas más abajo.
4. Iniciar los MCP que se habilitarán.
5. Iniciar Jeveador, API y Página, cada uno en su consola y carpeta.
6. Desde MCPs, agregar los registros si faltan y habilitarlos con sus servidores disponibles.
7. Probar «¿Qué datos me podés ofrecer?», una conversión de divisas o el último pronóstico disponible para CABA.

Con el entorno correspondiente activado, los comandos son:

~~~powershell
# Desde mcp_clima/, en su consola:
python server.py

# Desde mcp_finanzas/, en otra consola:
python server.py

# Desde jeveador/:
uvicorn main:app --host 127.0.0.1 --port 8002 --reload

# Desde api/:
uvicorn main:app --host 127.0.0.1 --port 8001 --reload --log-config logging.json

# Desde pagina/:
python app.py
~~~

Las altas administrativas quedan deshabilitadas. Registrar una URL no inicia el servidor. Un MCP habilitado que no puede publicar su catálogo interrumpe la evaluación; deshabilitar los servidores retirados o temporalmente indisponibles.

## Configuración local

La carga es automática: no se pasa la ruta de configuración al comando de arranque. Las variables existentes en el proceso tienen prioridad. Guardar las credenciales solo localmente; los siguientes nombres y ejemplos no provienen de archivos reales.

| Componente | Variable | Uso |
| --- | --- | --- |
| API | `API_KEY` | Credencial de OpenAI para preparar y redactar. |
| API | `MODELO_OPENAI` | Modelo; fallback gpt-4.1-mini. |
| API | `JEV_URL` | Servicio Jeveador local, por ejemplo http://127.0.0.1:8002/evaluar. |
| API y Jeveador | `CADENA` | Mismo archivo SQLite, preferentemente ruta absoluta. |
| Jeveador | `JEV_KEY` | Credencial de OpenRouter para Jev. |
| Jeveador | `JEV_URL` | Endpoint externo de decisiones de OpenRouter. |
| Jeveador | `JEV_MODELO` | Modelo de decisiones. |
| Jeveador | `UMBRAL_DEFECTO` | Respaldo del umbral; 0.5 si falta o no se convierte a float. |
| Página, API y Jeveador | `MAX_CONTEXTO` | Máximo de mensajes anteriores; 20 por defecto. Debe coincidir. |
| Página | `API_URL` | http://127.0.0.1:8001/chat/jev. |
| Página | `API_COSTOS_URL` | http://127.0.0.1:8001/consultas_sql/costos. |
| Página | `API_MCPS_URL` | http://127.0.0.1:8001/consultas_sql/mcps. |
| Página | `API_MCP_URL` | http://127.0.0.1:8001/consultas_sql/mcps/{id_mcp}; conservar el marcador. |
| Página | `API_UMBRAL_URL` | http://127.0.0.1:8001/consultas_sql/umbral. |
| Página | `PAGINA_SIZE` | Registros por página; 50 si falta o es inválido. |
| Clima | `TEMPERATURA_URL` | Endpoint horario con temperature_2m. |
| Clima | `PRECIPITACIONES_URL` | Endpoint horario con precipitation_probability. |
| Clima | `SENSACION_TERMICA_URL` | Endpoint horario con apparent_temperature. |
| Clima | `PRESION_URL` | Endpoint horario con surface_pressure. |

**JEV_URL tiene dos significados distintos:** en API apunta a Jeveador local; en Jeveador apunta al proveedor externo. Las credenciales API_KEY y JEV_KEY también pertenecen a proveedores diferentes y no se intercambian.

Las cuatro URLs de Clima deben corresponder a CABA y devolver fechas horarias en GMT; el componente convierte a GMT-3. Su [README](mcp_clima/README.md) detalla campos y límites. Finanzas utiliza el destino externo definido en su cliente y no necesita claves de los modelos.

API y Jeveador resuelven CADENA relativa desde sus propias carpetas. Con esta estructura, ../sqlserver/base.db desde ambas apunta al mismo archivo. La página administrativa actual consume HTTP y no necesita acceso SQLite directo.

Los clientes auxiliares de administración de Jev conservados en Página usan JEV_ADMIN_URL, JEV_ADMIN_TOKENS y JEV_ADMIN_KEY; no se llaman automáticamente desde Costos. El módulo SQLite anterior de Página tampoco participa en las rutas administrativas actuales.

Reiniciar el componente después de modificar variables; tras cambiar MAX_CONTEXTO, recargar también la página. Las políticas JSON se releen en cada comprobación y los cambios de registros/umbral se consultan en las siguientes peticiones.

## Flujo del chat y contratos

### Consulta concreta

1. La página envía mensaje y contexto a `POST /chat/jev` de la API.
2. La API llama a `POST /evaluar` de Jeveador.
3. Jeveador lee los MCP actuales, filtra los habilitados, autoriza destinos y descubre herramientas mediante list_tools.
4. Jev evalúa intención, cobertura, aplicabilidad por herramienta y recomendación.
5. Jeveador registra consumo y filtra las decisiones. Para aceptar una herramienta, la decisión debe ser **aplicable** y su **confidence debe superar estrictamente el umbral**.
6. La API comprueba la evaluación. Si hace falta un dato, hay cobertura parcial o existen varias interpretaciones, pide aclaración sin ejecutar.
7. Para ejecutar, la API busca el MCP habilitado en SQLite, redescubre su catálogo y limita las opciones a las herramientas aceptadas por Jeveador.
8. Comprueba permisos locales, solicita argumentos a OpenAI y los valida contra JSON Schema.
9. Vuelve a comprobar permisos antes de ejecutar una herramienta.
10. Valida el resultado y solicita la redacción final a OpenAI **sin herramientas disponibles**.
11. Devuelve el contrato público; Flask extrae el texto y el navegador muestra Markdown sanitizado.

Entrada de la API:

~~~json
{
  "mensaje": "Convertí 100 USD a EUR",
  "contexto": []
}
~~~

contexto es opcional. El campo opcional mcp de la API sirve para resolver una selección entre candidatos; no permite elegir un servidor ajeno a las evaluaciones ni eludir permisos. Jeveador solo recibe mensaje y contexto.

Respuesta pública del chat:

~~~json
{
  "estado": "Ok",
  "respuesta": "Texto para el usuario.",
  "herramientas": ["convertir_divisas"]
}
~~~

Las aclaraciones y respuestas sin ejecución conservan estado Ok con herramientas vacías. Los estados internos de coordinación y el resultado MCP completo no se exponen mediante ese contrato.

Jeveador devuelve intencion, mcp_recomendado, evaluaciones y capacidades. Cada evaluación contiene estado, mcp_evaluado, motivo, herramientas_aplicables y requiere_aclaracion. Sus estados posibles son sirve, sirve_parcialmente, no_sirve y falta_informacion. El [README de Jeveador](jeveador/README.md) detalla el filtro y la normalización de inconsistencias.

### Capacidades actuales

«¿Qué datos me podés ofrecer?» se clasifica como consultar_capacidades. Jeveador devuelve los catálogos actuales, recomendación null y evaluaciones vacías. La API los explica sin ejecutar herramientas.

La respuesta cambia al habilitar, deshabilitar o incorporar MCP autorizados. El catálogo no se fija en una respuesta histórica ni incluye los deshabilitados. Si no hay herramientas publicadas, la API informa su ausencia sin pedir una redacción a OpenAI. La detección de intención sigue usando Jev.

El catálogo describe capacidades; los permisos de ejecución de la API siguen comprobándose por separado al resolver una consulta.

### Pedido fuera de alcance

Si no existen herramientas aceptadas, Jeveador devuelve HTTP 200 con recomendación null. Una recomendación contradictoria sin herramientas aceptables se registra y descarta; la falta de capacidades no provoca un 502.

Cuando no hay candidatos ni datos pendientes, la API devuelve:

~~~json
{
  "estado": "Ok",
  "respuesta": "No tengo las herramientas necesarias para responder tu pregunta.",
  "herramientas": []
}
~~~

Esta salida no ejecuta MCP ni llama a OpenAI para redactar: el consumo de modelo del turno corresponde a la evaluación de Jev.

### Contexto y presentación

El historial se mantiene en memoria de la pestaña, con mensajes de usuario y asistente. MAX_CONTEXTO cuenta mensajes anteriores, no tokens ni pares de turnos. Cada mensaje admite hasta 10000 caracteres; el mensaje actual se envía aparte.

El historial se recorta y se pierde al recargar. No hay identidad de usuario, conversación persistida ni tareas pendientes durables. Cada turno vuelve a evaluar. La sesión de Flask se utiliza en formularios administrativos, no para guardar el historial.

Las respuestas del asistente admiten Markdown mediante Marked y DOMPurify locales, con sanitización antes de insertar HTML. Los mensajes de usuario se presentan como texto. Historial y botón de copiar conservan el texto original. Ver [bibliotecas locales](pagina/static/vendor/README.md).

## MCP incluidos

| MCP | Herramientas |
| --- | --- |
| Clima | get_temperatura, get_precipitaciones, get_sensacion_termica, get_presion, get_pronostico. |
| Finanzas | convertir_divisas, get_tipos_cambio, get_monedas, get_proveedores. |

**Clima:** todas las herramientas son sin argumentos y están limitadas a CABA. Las individuales resuelven una variable; las preguntas generales o combinadas corresponden a get_pronostico. Se toma el último registro horario, que puede ser futuro: no se presenta como condición actual ni como dato de una fecha solicitada que no coincide.

El pronóstico conjunto consulta las cuatro variables en paralelo. Conserva datos parciales y horarios propios; devuelve estado Ok si al menos una variable es válida y Error si ninguna lo es. La probabilidad de lluvia no es cantidad ni certeza; la presión es en superficie, no reducida al nivel del mar.

**Finanzas:** convertir_divisas y get_tipos_cambio llaman respectivamente a convert y get_rates del MCP Frankfurter; los listados llaman a list_currencies y list_providers. Usa Streamable HTTP hacia https://mcp.frankfurter.dev/, no su API REST. Cada consulta abre y cierra su sesión.

Son tipos de referencia, no precios de negociación en tiempo real. No hay transferencias, dólar blue/MEP/tarjeta, acciones, criptomonedas ni recomendaciones de inversión. No se inventan moneda, comisiones, fecha efectiva ni tipo de cambio si el resultado no los aporta.

Autos y Cocina no son componentes activos del repositorio. Algunos tests usan esos nombres como datos ficticios.

## Habilitación y permisos de MCP

Hay tres controles distintos:

| Control | Dónde | Qué decide |
| --- | --- | --- |
| Habilitación | Tabla SQLite mcps | Qué servidores participan en la evaluación. |
| Descubrimiento permitido | [jeveador/destinos_mcp.json](jeveador/destinos_mcp.json) | A qué endpoints puede conectarse Jeveador. |
| Ejecución autorizada | [api/politica_mcp.json](api/politica_mcp.json) | Qué herramientas puede ejecutar la API para cada nombre y destino. |

**Habilitar un MCP o recibir una recomendación de Jev no concede permisos de ejecución.** Las políticas actuales autorizan los destinos locales de Clima (8005) y Finanzas (8006), y la API autoriza sus herramientas publicadas.

Para incorporar otro MCP:

1. Revisar su implementación, capacidades, destino y herramientas que se aceptarán.
2. Autorizar el destino en Jeveador.
3. Agregar nombre, URL y herramientas aprobadas a la política de la API.
4. Arrancar el servidor, registrarlo desde la administración y habilitarlo.

Los nombres de MCP y herramientas deben cumplir el identificador validado: letras ASCII, dígitos, guion o guion bajo, entre 1 y 64 caracteres. Agregar una herramienta al servidor requiere aprobarla también en la política de ejecución.

Las políticas se releen en cada comprobación, sin caché de permisos. La API comprueba la autorización al preparar la selección y justo antes de ejecutar; su cliente MCP también la exige. Una política de ejecución ausente/inválida devuelve 503; un permiso denegado, 403. Jeveador devuelve 503 si el destino de descubrimiento no está permitido o su política falla.

Actualmente se permiten solo endpoints MCP **HTTP loopback con puerto explícito**. localhost se conecta como 127.0.0.1 sin resolver DNS; ::1 requiere su entrada explícita. Las variantes de ruta vacía, /, /mcp y /mcp/ se normalizan a /mcp. Se rechazan credenciales, parámetros, fragmentos, otros hosts y redirecciones del transporte.

Esta restricción se aplica a las conexiones MCP de API y Jeveador. Los servidores Clima y Finanzas siguen necesitando sus consultas externas a los proveedores. Las políticas son globales; no hay autorización por usuario. La autenticación administrativa queda fuera del alcance de este trabajo.

## Controles de contenido externo

- **Instrucciones separadas:** las preguntas de Jev referencian índices de state.mcps y claves mcp_0, mcp_1, etc. Nombres, descripciones y esquemas quedan en los datos; la respuesta pública recupera los nombres reales.
- **Catálogo:** Jeveador admite hasta 32 MCP habilitados, 64 herramientas por MCP y 256 en total; 64 páginas por servidor, sin cursores repetidos. Descripciones de hasta 8192 caracteres; esquemas object válidos de hasta 64 KiB, 32 niveles y 10000 nodos, con referencias solo locales; catálogo total de hasta 512 KiB.
- **Segunda validación:** la API vuelve a descubrir y validar el catálogo antes de ejecutar y valida los argumentos contra el esquema. Un catálogo inválido se rechaza, sin ocultar herramientas o truncar descripciones silenciosamente.
- **Resultados:** la API admite texto y/o un objeto structuredContent, hasta 32 bloques, 64 KiB UTF-8 por bloque y 128 KiB totales, 16 niveles y 10000 nodos. Rechaza contenido no textual, recursos y números JSON no finitos; elimina metadatos/campos desconocidos antes de redactar.
- **Redacción:** el modelo final no dispone de herramientas.

Estos controles no garantizan la verdad del proveedor ni detectan semánticamente toda instrucción maliciosa. La confianza de Jev mide aceptación de la clasificación, no seguridad. Los límites de tamaño se aplican a datos ya recibidos y decodificados, no a bytes del transporte antes de recibirlos.

## API administrativa SQL

La administración está en el router consultas_sql de la API. main.py registra los routers; las operaciones y clientes permanecen modularizados.

Las funciones SQL devuelven (True, datos) o (False, {"status_code": codigo}). Los endpoints los adaptan a:

~~~json
{"resultado": true, "salida": {"id": 1, "valor": 0.85}}
~~~

Un fallo conserva su HTTP y usa, por ejemplo:

~~~json
{"resultado": false, "salida": {"status_code": 404}}
~~~

| Método y ruta | Uso |
| --- | --- |
| GET /consultas_sql/costos | Registros paginados, filtros y totales por grupo. |
| GET /consultas_sql/mcps | Lista habilitados y deshabilitados. |
| POST /consultas_sql/mcps | Alta con nombre y URL, siempre deshabilitada; HTTP 201. |
| GET /consultas_sql/mcps/{id_mcp} | Consulta individual. |
| PATCH /consultas_sql/mcps/{id_mcp} | Cambia habilitado a 0 o 1. |
| DELETE /consultas_sql/mcps/{id_mcp} | Borra el registro. |
| GET /consultas_sql/umbral | Lee id=1 de config_umbral. |
| PUT /consultas_sql/umbral | Guarda un valor decimal finito entre 0 y 1. |

Códigos administrativos: 400 datos inválidos, 404 inexistencia, 409 conflicto, 422 validación, 503 base/tabla no disponible y 500 fallo interno. La validación también conserva el sobre resultado/salida.

Los listados vacíos actuales pueden responder 200. Si Costos o MCPs reciben un 404 **al listar**, la página muestra «No hay información disponible.» junto a la tabla, sin modal. Las escrituras, Umbral y consultas individuales mantienen el modal ante fallos.

### Pantallas administrativas

- **Costos:** fechas GMT-3, costos USD, paginación y filtros Jev/OpenAI. Los totales se calculan sobre todas las filas de cada grupo, independientemente de la página y de los filtros de registros. Se considera Jev metodo=JEV y OpenAI el resto.
- **Umbral:** muestra porcentaje y envía decimal: 85 equivale a 0.85. Actualiza el registro existente; no crea una fila ausente. Jeveador usa el nuevo valor en las siguientes evaluaciones de herramientas.
- **MCPs:** interruptores ON/OFF, altas deshabilitadas y borrado con confirmación. Borrar un registro no detiene el servidor ni borra billing. Los formularios de escritura usan protección CSRF.

El detalle de entradas, salidas y parámetros está en [API](api/README.md#administración-sql) y [Página](pagina/README.md).

## SQLite y consumo

[sqlserver/esquema.sql](sqlserver/esquema.sql) crea la estructura y datos mínimos en una transacción. Se puede repetir conservando valores y filas existentes; no realiza migraciones.

| Tabla | Responsabilidad |
| --- | --- |
| mcps | id, nombre único, url y habilitado (0/1). El esquema compartido deja el catálogo vacío. |
| config_umbral | Único registro id=1, valor REAL; inicial 0.85. |
| billing | Fecha UTC, tokens, costo estimado, método y herramientas. |
| errores | Catálogo histórico de descripciones HTTP, conservado por compatibilidad; no es un registro de eventos. |

La administración abre la base existente con mode=ro para lecturas y mode=rw para escrituras. No inicializa ni repuebla tablas. Las funciones opcionales de Jeveador son otra vía: crear_tabla_mcps() inserta Clima y Finanzas habilitados **solo al crear una tabla inexistente**; crear_tabla_config_umbral() crea 0.85 solo si la tabla no existe. No se llaman automáticamente al arrancar.

El umbral de Jeveador se consulta al procesar decisiones de herramientas. Si no puede obtenerse, registra lo ocurrido y usa UMBRAL_DEFECTO. La API administrativa informa el fallo al leer el umbral, sin inventar un valor para la pantalla. La confianza debe superar el umbral, no igualarlo.

Una fila de billing corresponde a una respuesta del proveedor, no a todo un turno. No almacena conversaciones, prompts ni resultados MCP. Tampoco incluye identificador de petición, usuario o modelo para agrupar todas las llamadas de un turno con certeza.

Jev guarda columnas aplanadas y metodo/herramientas iguales a JEV. Usa usage.cost; toma ausentes como cero y calcula entrada + salida si falta el total. Caché y razonamiento son detalles, no se suman otra vez. Se registra el consumo antes de validar la decisión, por lo que una respuesta luego descartada puede tener consumo.

La API estima costos de OpenAI con las tarifas locales del código; si desconoce modelo o consumo, puede guardar valores nulos. Las estimaciones no son facturas ni se concilian automáticamente. El guardado sigue activo aunque no se imprima el JSON o resumen de consumo. Un fallo de billing puede interrumpir el chat después de consumir tokens o ejecutar una herramienta.

## Errores y tiempos de espera

El chat de la API utiliza {"detail":"..."} para errores técnicos. Preserva códigos y cabeceras de errores HTTP conocidos; registra fallos inesperados y devuelve 500 con detalle genérico. La validación de entrada responde 422.

| Código | Uso en el chat de API |
| --- | --- |
| 200 | Respuesta, aclaración, capacidades o falta de herramientas. Un error de negocio MCP se explica con el prefijo «La herramienta informó un error: ». |
| 403 | Herramienta o destino sin permiso local. |
| 502 | Fallo de servicio o respuesta inválida. |
| 503 | Configuración o catálogo no disponible. |
| 504 | Tiempo de espera agotado. |
| 500 | Fallo interno o de persistencia. |

Un status_code dentro del JSON de una herramienta MCP no modifica automáticamente el HTTP del protocolo. La API distingue isError y estado Error dentro de structuredContent o texto JSON. Un pronóstico parcial con estado general Ok mantiene el éxito.

Flask valida el formulario y puede responder 400; los fallos del cliente de chat se presentan como 502 con «Ocurrió un error.». Las páginas administrativas usan su modal, con la excepción de 404 en listados.

| Operación | Espera configurada |
| --- | --- |
| Página → API de chat | 200 segundos. |
| Página → API administrativa | 30 segundos por llamada. |
| Flujo completo /chat/jev | 180 segundos. |
| API → Jeveador | 60 segundos HTTP. |
| API → OpenAI | 60 segundos HTTP por llamada. |
| Descubrimiento MCP | 30 segundos por servidor. |
| Ejecución MCP en API | 30 segundos; get_pronostico, 60. |
| Clima → cada endpoint horario | 30 segundos, en paralelo para el pronóstico conjunto. |
| Finanzas → MCP Frankfurter | 20 segundos totales, incluidos inicialización y cierre. |
| Jeveador → Jev | 30 segundos. |
| SQLite | 30 segundos de espera por bloqueo. |

El descubrimiento de Jeveador es secuencial y ocurre antes de consultar al modelo; los 30 segundos de Jev no limitan todo /evaluar. El total puede superar el plazo del cliente de API si crece el catálogo. No hay respuestas progresivas ni reintentos automáticos del flujo.

No hay caché local de catálogos, permisos o resultados. La redacción final no puede volver a ejecutar herramientas. Los logs registran diagnósticos, pero el detalle INFO por herramienta de confianza/probabilidades está desactivado; la confianza no se persiste en SQLite.

## Pruebas y evidencia

Las suites están en tests/ de cada componente. Ejecutarlas desde su carpeta y con su propio entorno para evitar colisiones entre módulos del mismo nombre:

~~~powershell
python -m unittest discover -s tests -t . -v
~~~

Las pruebas aisladas sustituyen la carga de configuración local, utilizan datos ficticios, simulan servicios y emplean SQLite temporal. No necesitan credenciales, servicios encendidos ni bases reales. Las instrucciones específicas están en los README de cada componente.

La batería publicada tiene **173 informes individuales**:

| Modalidad | Cantidad aprobada | Alcance |
| --- | ---: | --- |
| API aislada | 96 | Chat, SQL, contexto, consumo, permisos, revocaciones, destinos, catálogos y resultados adversariales. |
| Jeveador aislada | 68 | Solicitud por índices, decisiones, umbral, catálogo, paginación, destinos y persistencia. |
| Integración HTTP real | 9 | Contrato publicado, capacidades, pedido sin herramientas, entrada/contexto inválidos, conversión, pronóstico y herramienta inventada. |

Los [HTML por prueba y su índice](resultados_pruebas/index.html) incluyen objetivo, esperado, evidencia y límites. Un rechazo esperado puede ser una prueba aprobada; los informes distinguen simulación de servicios reales.

La integración registrada ejecutó convertir_divisas y get_pronostico a través de API y Jeveador. No cubre todas las herramientas, monedas, localidades rechazadas ni futuras respuestas del proveedor. Los README de Clima y Finanzas conservan sus verificaciones previas de suites propias (22 y 12 pruebas); no se suman a estos 173 informes.

La integración es optativa y puede generar consumo y billing. Desde api/:

~~~powershell
.\api\Scripts\python.exe tests\pruebas_integracion_viva.py
~~~

Para regenerar evidencia aislada e informes, seguir [resultados_pruebas/README.md](resultados_pruebas/README.md). Esta revisión documental no volvió a ejecutar suites ni llamadas reales.

## Límites y pendientes

- Ampliar integración real a las herramientas y casos aún no cubiertos; las verificaciones actuales no prueban inmunidad universal a prompt injection ni exactitud de todos los modelos/proveedores.
- Crear en la API un método y una tabla de eventos para centralizar errores de todos los componentes: origen, fecha/hora, tipo, mensaje y traceback, sin secretos. La tabla errores actual contiene descripciones y no cumple esa función.
- Registrar también pedidos sin herramientas, decisiones bajo el umbral y recomendaciones inconsistentes, conservándolos como resultados válidos HTTP 200. La clasificación del evento queda pendiente; hoy se diagnostican en consola.
- No hay contexto persistente, identidad de usuario, permisos por usuario ni tarea pendiente durable. Sí hay permisos globales por herramienta y destino.
- Un MCP habilitado indisponible aborta la evaluación; descubrir todos los catálogos en cada turno agrega latencia.
- SQLite no tiene migraciones automáticas, WAL configurado ni cola de escritura. Billing permanece dentro del camino de respuesta.
- La administración de autenticación queda fuera de este alcance.

Los secretos, entornos virtuales, bases y backups son archivos locales. Las exclusiones de Git no bloquean su lectura ni sustituyen permisos del sistema. Mantener las pruebas aisladas de esos archivos y no publicar credenciales.
