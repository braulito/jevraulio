# Jeveador

Servicio FastAPI que compara un mensaje con las herramientas de los MCP habilitados. Lee el catálogo SQLite, descubre las capacidades publicadas y solicita la clasificación a Jev mediante OpenRouter. Devuelve una evaluación para que la [API](../api/README.md) coordine el chat.

**Jeveador recomienda y describe capacidades; no ejecuta herramientas MCP.**

## Arranque

Desde jeveador/, con Python 3.10 o superior, en PowerShell:

~~~powershell
# Crear el entorno solo la primera vez.
python -m venv jeveador
.\jeveador\Scripts\python.exe -m pip install -r reqs.txt
.\jeveador\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002 --reload
~~~

Con el entorno activado:

~~~powershell
uvicorn main:app --port 8002 --reload
~~~

Swagger: http://127.0.0.1:8002/docs. Endpoint: POST http://127.0.0.1:8002/evaluar.

La base debe estar inicializada y los MCP habilitados deben estar encendidos. Se puede probar Jeveador directamente desde Swagger sin levantar la API; la evaluación utiliza OpenRouter y registra consumo real.

## Configuración

funciones/entorno.py carga automáticamente la configuración local antes de importar los routers. No se indica su ruta al arrancar. Las variables existentes en el proceso tienen prioridad.

| Variable | Responsabilidad |
| --- | --- |
| JEV_KEY | Credencial de OpenRouter. |
| JEV_URL | Endpoint **externo de decisiones** de OpenRouter; no es la dirección local de Jeveador que configura la API. |
| JEV_MODELO | Identificador del modelo de decisiones. |
| CADENA | Ruta SQLite compartida con la API. Las relativas se resuelven desde jeveador/. |
| UMBRAL_DEFECTO | Respaldo si no se puede obtener config_umbral. Si falta o falla su conversión a float, se usa 0.5. |
| MAX_CONTEXTO | Máximo de mensajes de contexto, entero positivo; 20 por defecto. Igual en Página y API. |

Usar la misma ruta absoluta de CADENA en API y Jeveador. La inicialización compartida está en [sqlserver](../sqlserver/README.md). Reiniciar después de cambiar variables.

[destinos_mcp.json](destinos_mcp.json) contiene los endpoints autorizados para descubrimiento. Se relee antes de conectar; habilitar un registro en SQLite no sustituye esta autorización.

## Interfaz: POST /evaluar

~~~json
{
  "mensaje": "¿Cuántos euros son 100 dólares estadounidenses?",
  "contexto": []
}
~~~

El mensaje debe tener entre 1 y 10000 caracteres y no contener solo espacios. El contexto es opcional: lista limitada por MAX_CONTEXTO, con mensajes no vacíos de hasta 10000 caracteres cada uno. Se rechazan campos adicionales.

Cada petición lee los registros actuales y descubre las herramientas de los habilitados. No hay una lista de capacidades fijada en el código ni caché de catálogos. Los deshabilitados no se conectan ni se envían al modelo.

### Resolver una consulta

Ejemplo ilustrativo de respuesta; la selección concreta depende del modelo y del umbral:

~~~json
{
  "intencion": "resolver_consulta",
  "mcp_recomendado": "mcp_finanzas",
  "evaluaciones": [
    {
      "estado": "sirve",
      "mcp_evaluado": "mcp_finanzas",
      "motivo": "Las herramientas del MCP cubren el pedido.",
      "herramientas_aplicables": ["convertir_divisas"],
      "requiere_aclaracion": false
    }
  ],
  "capacidades": []
}
~~~

Se devuelve una evaluación por MCP descubierto. Los estados son:

| Estado | Interpretación |
| --- | --- |
| sirve | Las herramientas cubren todo el pedido. |
| sirve_parcialmente | Solo una parte del pedido puede resolverse. |
| falta_informacion | Hay herramientas pertinentes, pero hace falta aclarar o aportar datos. |
| no_sirve | No hay herramientas aceptadas para el pedido. |

Para aceptar una herramienta, **primero** su decisión debe ser aplicable y **después** su confidence debe superar estrictamente el umbral. Igualar el umbral, quedar por debajo o no informar confianza implica descartarla. probabilities no reemplaza confidence en ese filtro.

El umbral se consulta al procesar decisiones de herramientas. Una recomendación sin herramientas aceptadas se descarta. Las contradicciones interpretables se registran y normalizan; si el filtro deja solo parte de las herramientas de una cobertura completa, esta pasa a parcial. Una recomendación null puede coexistir con evaluaciones pertinentes cuando hay ambigüedad; la API decide si necesita aclaración.

Si ningún MCP tiene herramientas aceptadas, se devuelve **HTTP 200**, recomendación null y las evaluaciones sin herramientas. Es un resultado válido. La API transforma ese resultado en el mensaje al usuario sobre falta de herramientas. Las decisiones desconocidas o las respuestas que no pueden interpretarse siguen siendo errores técnicos.

### Consultar capacidades

Ante preguntas como «¿Qué datos me podés ofrecer?», la intención consultar_capacidades devuelve:

- mcp_recomendado: null.
- evaluaciones: lista vacía.
- capacidades: catálogos actuales con nombre del MCP y herramientas (name, description e inputSchema).

La API redacta esa información en lenguaje natural, sin ejecutar herramientas. La respuesta cambia al habilitar, deshabilitar o agregar servidores **autorizados**; no usa una descripción histórica. Esta intención también se clasifica mediante Jev y puede generar consumo.

## SQLite y consumo

| Tabla | Uso |
| --- | --- |
| mcps | id, nombre, url, habilitado. obtener_mcps() lee todos los registros en cada evaluación; el servicio filtra los habilitados. |
| config_umbral | Registro id=1 con valor decimal. |
| billing | Tokens y costo de las llamadas a Jev. |

obtener_umbral() devuelve el valor guardado. Si falta el registro o falla la lectura/conversión, registra lo ocurrido y usa UMBRAL_DEFECTO. Ese respaldo no corrige ni crea la tabla. La edición administrativa de la API valida valores finitos entre 0 y 1.

Las funciones de creación son opcionales y no se ejecutan automáticamente al arrancar:

- crear_tabla_billing(): crea la tabla si falta.
- crear_tabla_config_umbral(): crea la tabla con id=1 y valor 0.85 **solo si la tabla no existe**.
- crear_tabla_mcps(): crea la tabla con mcp_finanzas en http://127.0.0.1:8006/mcp y mcp_clima en http://localhost:8005/mcp, ambos habilitados, **solo si la tabla no existe**.

No se repueblan tablas existentes. El esquema compartido de sqlserver es otra vía de inicialización y deja mcps vacío. Crear registros no arranca los servidores.

El consumo se guarda al recibir el JSON del proveedor, antes de validar la decisión; una respuesta luego rechazada puede igualmente tener consumo registrado. Los datos se aplanan en input_tokens, cached_tokens, cache_write_tokens, output_tokens, reasoning_tokens, total_tokens y costo_estimado_usd. Los ausentes se guardan como 0; si falta el total, se calcula entrada + salida, sin sumar nuevamente caché ni razonamiento. El costo proviene de usage.cost y metodo/herramientas son siempre JEV.

No se guarda el JSON completo de decisiones en billing ni se imprime el JSON de consumo. El estado actual tampoco emite el resumen INFO por herramienta de decisión/confianza; sí registra inconsistencias, rechazos y fallos. Un fallo de guardado de billing puede devolver HTTP 500.

## Instrucciones y datos externos

Las preguntas referencian índices de state.mcps y las recomendaciones usan claves como mcp_0:

~~~text
Cobertura: Aplicá state.reglas. Evaluá solo state.mcps[0].
Recomendación mcp_0: El MCP de state.mcps[0] es el más adecuado.
Herramienta: state.mcps[0].herramientas[0]
~~~

Los nombres, descripciones y esquemas permanecen en state.mcps; no se interpolan dentro de instrucciones o criterios. La selección por índice se traduce al nombre real al construir la respuesta pública.

Esto reduce la mezcla entre reglas y datos, pero el modelo sigue viendo el contenido externo. No hay un filtro semántico que garantice detectar toda instrucción maliciosa. La confianza de la clasificación tampoco concede permisos: la API aplica su propia política antes de ejecutar.

## Destinos de descubrimiento

La política local autoriza inicialmente http://127.0.0.1:8005/mcp y http://127.0.0.1:8006/mcp. Antes de abrir una sesión se exige un destino permitido; un destino no autorizado o una política ausente/inválida devuelve 503.

Solo se permiten endpoints HTTP loopback con puerto explícito: localhost, 127.0.0.1 o ::1. Las variantes de ruta vacía, /, /mcp y /mcp/ se normalizan a /mcp. localhost se convierte en 127.0.0.1 antes de conectar, sin resolver DNS; IPv6 requiere su propia entrada. No se admiten credenciales, consultas, fragmentos, otros hosts ni redirecciones MCP.

Para incorporar un MCP, revisar y autorizar su destino aquí, aprobar su nombre/destino/herramientas en [la política de API](../api/politica_mcp.json), registrarlo en SQLite y habilitarlo cuando esté disponible. Un registro nuevo no adquiere permisos automáticamente. Las políticas se releen en cada comprobación. La autenticación administrativa queda fuera del alcance de estos cambios.

## Validación del catálogo

funciones/catalogo_validaciones.py valida registros antes de conectar y herramientas antes de enviarlas a Jev, también para consultar capacidades. Durante la paginación se valida el catálogo acumulado.

| Control | Regla |
| --- | --- |
| Nombres de MCP y herramientas | De 1 a 64 caracteres: letras ASCII, dígitos, guion o guion bajo. |
| Duplicados | Sin nombres repetidos entre MCP habilitados ni dentro de las herramientas de un mismo MCP. Distintos MCP pueden compartir nombre de herramienta. |
| MCP habilitados | Hasta 32 por evaluación. |
| Herramientas | Hasta 64 por MCP y 256 en total. |
| Páginas | Hasta 64 por MCP; no se aceptan cursores repetidos. |
| Descripción | Hasta 8192 caracteres por herramienta. |
| inputSchema | Objeto JSON Schema válido, tipo object, hasta 64 KiB UTF-8, 32 niveles y 10000 nodos. |
| Referencias | Solo locales, empezando con #; sin resolución de documentos externos. |
| Catálogo completo | Hasta 512 KiB JSON UTF-8 normalizado. |

La validación sintáctica inicial admite URLs HTTP/HTTPS de hasta 2048 caracteres, sin credenciales, espacios ni controles; la **autorización de destinos posterior es más restrictiva** y solo permite los endpoints HTTP loopback aprobados.

Un catálogo inválido se rechaza completo, sin truncar descripciones ni omitir herramientas silenciosamente. Los catálogos vacíos son válidos. Los límites se aplican al contenido procesado, no al transporte HTTP antes de recibirlo. No agregan llamadas al modelo ni garantizan que una descripción sea verdadera.

Las operaciones de validación y destinos retornan (True, datos) o (False, {"status_code": codigo}); el servicio adapta los errores a HTTP. Las funciones SQLite existentes mantienen sus retornos propios, como la lista de obtener_mcps() y el float de obtener_umbral().

## Errores y límites operativos

| HTTP | Situación |
| --- | --- |
| 200 | Evaluación válida, consulta de capacidades o pedido sin herramientas aceptadas. |
| 422 | Entrada fuera del contrato. |
| 502 | Fallo de MCP/OpenRouter, catálogo publicado inválido o decisión no interpretable. |
| 503 | Configuración, acceso al catálogo SQLite, registros o política de destinos inválidos. |
| 504 | Tiempo agotado en descubrimiento MCP o consulta a Jev. |
| 500 | Fallo inesperado, de validación interna o de persistencia del consumo. |

Los errores técnicos usan el detalle público de FastAPI. El log aporta contexto del fallo sin volcar credenciales ni el catálogo completo.

El descubrimiento tiene un límite de 30 segundos por MCP y la solicitud a Jev, 30 segundos. Los MCP se consultan secuencialmente: el total puede crecer con el catálogo. Un MCP habilitado que falla al publicar sus herramientas interrumpe la evaluación; no se devuelve una lista parcial como si fuera completa. Deshabilitar los servidores retirados o temporalmente indisponibles. No hay memoria persistente de conversación.

## Organización

| Ubicación | Responsabilidad |
| --- | --- |
| main.py | Carga el entorno, crea FastAPI y registra el router. |
| routers/jev.py | POST /evaluar. |
| schemas/jev.py | Entrada, decisión del proveedor y evaluación pública. |
| funciones/entorno.py, funciones/contexto_config.py | Carga automática y límite de contexto. |
| funciones/jev_funciones.py | Construcción de preguntas, cliente Jev e interpretación. |
| funciones/mcp_funciones.py | Descubrimiento y paginación MCP. |
| funciones/catalogo_validaciones.py | Límites y validación del catálogo. |
| funciones/destinos_mcp.py, destinos_mcp.json | Autorización de destinos. |
| funciones/bases_sqlite.py | Catálogo, umbral y persistencia. |
| funciones/billing.py | Aplanado y registro de consumo. |
| tests/ | Pruebas aisladas. |

## Pruebas

Desde jeveador/:

~~~powershell
.\jeveador\Scripts\python.exe -m unittest discover -s tests -t . -v
~~~

La suite sustituye la carga de configuración y simula HTTP, catálogos, decisiones y billing. SQLite usa archivos temporales. Cubre selección por índices, separación de instrucciones/datos, capacidades, umbral, inconsistencias, destinos, paginación, límites, esquemas y persistencia.

La ejecución registrada completó **68 pruebas aisladas de Jeveador**, todas aprobadas. Los [informes individuales](../resultados_pruebas/index.html) incluyen además 96 pruebas aisladas de API y 9 solicitudes HTTP de integración. Las pruebas de construcción de solicitudes no demuestran por sí solas resistencia del modelo a todo ataque real. Esta actualización documental no volvió a ejecutar las suites.

Volver al [README general](../README.md).
