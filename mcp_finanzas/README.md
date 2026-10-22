# MCP Finanzas

Servidor FastMCP local que actúa como cliente del MCP externo de Frankfurter. No consulta directamente su API REST. Publica cuatro herramientas de divisas y conserva los datos del proveedor.

Flujo: Página → API → MCP Finanzas local → MCP Frankfurter. Jeveador evalúa previamente si sus capacidades corresponden al pedido; la API autoriza y ejecuta.

## Arranque y configuración

Desde mcp_finanzas/, con Python 3.10 o superior, en PowerShell:

~~~powershell
# Crear el entorno solo la primera vez.
python -m venv mcp_finanzas
.\mcp_finanzas\Scripts\python.exe -m pip install -r requirements.txt
.\mcp_finanzas\Scripts\python.exe server.py
~~~

| Dirección | Uso |
| --- | --- |
| http://127.0.0.1:8006/mcp | Servidor local, Streamable HTTP con respuestas JSON. |
| https://mcp.frankfurter.dev/ | MCP externo consultado por este componente. |

El componente no carga archivos de entorno ni requiere una clave de OpenAI/OpenRouter. La carga automática de FastMCP está desactivada. El destino externo está definido en funciones.py. Las llamadas necesitan conectividad con Frankfurter; el servidor local puede arrancar aunque el proveedor esté indisponible.

## Incorporación a JEVraulio

1. Revisar las herramientas y arrancar el servidor.
2. Comprobar que [destinos_mcp.json de Jeveador](../jeveador/destinos_mcp.json) autorice http://127.0.0.1:8006/mcp.
3. Comprobar que [politica_mcp.json de API](../api/politica_mcp.json) autorice el nombre mcp_finanzas, ese destino y las herramientas aprobadas.
4. Desde la pantalla MCPs o la administración SQL de la API, agregar el nombre mcp_finanzas y la URL completa, si no existen. Un alta administrativa queda deshabilitada; habilitarla con el servidor disponible.

Las políticas actuales incluyen este MCP y sus cuatro herramientas. No se registra automáticamente al arrancar, ni modifica la base compartida. API y Jeveador descubren el catálogo sin agregar rutas de chat. Una herramienta futura requiere aprobación explícita en la política de la API, aunque ya aparezca en el catálogo.

## Herramientas

| Herramienta local | Herramienta remota | Argumentos |
| --- | --- | --- |
| convertir_divisas | convert | importe positivo, moneda_origen y moneda_destino; fecha y proveedor opcionales. |
| get_tipos_cambio | get_rates | moneda_base; monedas_destino separadas por comas, fecha y proveedor opcionales. Omitir destinos consulta todos los disponibles. |
| get_monedas | list_currencies | Sin argumentos. |
| get_proveedores | list_providers | Sin argumentos. |

Ejemplos para el chat:

- «¿Cuántos euros son 100 dólares estadounidenses?»
- «Convertí 250 EUR a USD el 2024-06-03.»
- «Dame el tipo de cambio de EUR contra USD y GBP.»
- «¿Qué monedas podés convertir?»
- «¿Qué fuentes de tipos de cambio hay disponibles?»

Los códigos de moneda se normalizan a mayúsculas y deben tener tres letras. Esto valida el formato; Frankfurter determina qué monedas soporta. La fecha debe ser válida y tener formato YYYY-MM-DD. El proveedor opcional usa la clave de institución devuelta por get_proveedores.

Si faltan datos, la API debe pedir aclaración antes de ejecutar. No asumir una moneda concreta para «pesos». Para consultar solo un tipo corresponde get_tipos_cambio; para convertir un importe, convertir_divisas.

## Contratos y errores

consultar_frankfurter devuelve (True, datos) o (False, {"status_code": codigo}). Cada llamada abre transporte, inicializa ClientSession, ejecuta call_tool y cierra los recursos.

Las herramientas adaptan ese retorno a un JSON de negocio. Ejemplo ilustrativo:

~~~json
{
  "estado": "Ok",
  "respuesta": {"datos": "respuesta original del MCP externo"},
  "fuente": "Frankfurter",
  "mcp_externo": "https://mcp.frankfurter.dev/"
}
~~~

respuesta conserva la estructura del proveedor: se prioriza structuredContent; si falta, se intenta decodificar el texto JSON o se conserva el texto. No se agregan fechas, tipos de cambio ni campos que el proveedor no haya entregado.

Ejemplo de fallo:

~~~json
{
  "estado": "Error",
  "respuesta": "No se pudo completar la consulta financiera",
  "status_code": 504
}
~~~

| Código de negocio | Situación |
| --- | --- |
| 400 | Argumentos inválidos. |
| 502 | Fallo de comunicación/herramienta o respuesta vacía. |
| 504 | Tiempo de espera agotado. |
| Código HTTP externo | Rechazo HTTP del proveedor, conservando su código. |
| 500 | Fallo interno de la herramienta local. |

status_code pertenece al JSON de negocio y no modifica por sí solo el HTTP del protocolo MCP. El esquema MCP también puede rechazar argumentos antes de ejecutar la función mediante isError. La API reconoce los errores de negocio y conserva su contrato público de chat.

Los fallos se registran con contexto y detalle de excepción; no se vuelcan explícitamente argumentos ni cuerpos externos.

## Límites

- Ofrece tipos de referencia, no precios de compraventa en tiempo real. El último dato puede corresponder a un día anterior.
- Conservar las monedas, unidades, fecha efectiva y redondeo que informe la fuente.
- No realiza transferencias, no incluye comisiones y no consulta dólar blue, MEP, tarjeta, acciones o criptomonedas.
- No predice ni recomienda inversiones. Las consultas históricas admiten una fecha por llamada, sin rangos.
- La disponibilidad de moneda, fecha e institución depende del proveedor.
- El plazo total es de 20 segundos, incluyendo inicialización y cierre; la API permite 30 segundos para estas herramientas. No hay reintentos, caché ni llamadas propias a LLM.

Los permisos locales de API/Jeveador controlan el acceso a este servidor; no restringen su consulta interna a Frankfurter ni equivalen a autenticación propia del MCP. Los resultados externos quedan sujetos a los controles de estructura y tamaño de la API antes de la redacción.

## Organización

| Ubicación | Responsabilidad |
| --- | --- |
| server.py | FastMCP local y cuatro herramientas. |
| funciones.py | Cliente remoto, normalización, validación y errores. |
| requirements.txt | Dependencias. |
| tests/test_finanzas.py | Cliente simulado y servidor MCP en memoria. |

## Pruebas

Desde mcp_finanzas/:

~~~powershell
.\mcp_finanzas\Scripts\python.exe -m unittest discover -s tests -t . -v
~~~

La suite simula transporte y sesión externos, sin red ni archivos de entorno. Comprueba inicialización/cierre, traducción de argumentos, JSON/texto/structuredContent, errores, timeout, entradas inválidas y descubrimiento/ejecución en memoria.

La verificación previa documentada de esta suite fue de 12 pruebas aprobadas. Los [informes de integración](../resultados_pruebas/index.html) registran además una conversión real de 100 USD a EUR a través de API y Jeveador, aprobada. Esa prueba no verifica todos los pares, fechas ni herramientas del proveedor. Esta actualización documental no volvió a ejecutar pruebas ni consultas externas.

Volver al [README general](../README.md).
