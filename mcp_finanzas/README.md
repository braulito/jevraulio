# MCP Finanzas

Servidor FastMCP basado en la estructura de mcp_clima, que actúa como cliente de un MCP externo: [Frankfurter](https://frankfurter.dev/es/mcp/). No llama directamente a su API REST. La cadena es:

Chat con Jeveador → MCP Finanzas local → MCP Frankfurter → datos de tipos de referencia.

## Arranque

Desde esta carpeta, en PowerShell:

```powershell
python -m venv mcp_finanzas
.\mcp_finanzas\Scripts\python.exe -m pip install -r requirements.txt
.\mcp_finanzas\Scripts\python.exe server.py
```

Endpoint local: **http://127.0.0.1:8006/mcp**, con Streamable HTTP y respuestas JSON.
Endpoint externo: **https://mcp.frankfurter.dev/**. No requiere clave ni registro según su documentación. Este componente no carga archivos .env; la carga automática de FastMCP está desactivada.

En la pantalla MCPs de JEV, agregá nombre **mcp_finanzas** y URL **http://127.0.0.1:8006/mcp**. El alta queda deshabilitada: habilitala después de arrancar el servidor. API y Jeveador descubren las herramientas mediante el catálogo existente, sin agregar rutas de chat. No se registra automáticamente ni se modifica la base real.

## Herramientas

| Herramienta local | Herramienta remota | Uso |
| --- | --- | --- |
| convertir_divisas | convert | Importe positivo, monedas de origen/destino, fecha y proveedor opcionales. |
| get_tipos_cambio | get_rates | Moneda base, destinos separados por comas, fecha y proveedor opcionales. |
| get_monedas | list_currencies | Códigos ISO y nombres admitidos, sin argumentos. |
| get_proveedores | list_providers | Instituciones, claves y cobertura disponibles, sin argumentos. |

Ejemplos de preguntas para el chat:

- «¿Cuántos euros son 100 dólares estadounidenses?»
- «Convertí 250 EUR a USD el 2024-06-03.»
- «Dame el tipo de cambio de EUR contra USD y GBP.»
- «¿Qué monedas podés convertir?»
- «¿Qué fuentes de tipos de cambio hay disponibles?»

Los códigos se normalizan a mayúsculas. Una fecha debe ser una fecha válida en formato YYYY-MM-DD. La compatibilidad de una moneda, fecha o institución la determina Frankfurter: no se supone que todo código de tres letras esté soportado. Si falta importe o moneda, el chat debe pedir aclaración; no asumir una moneda para la palabra «pesos».

Son tipos de referencia; el último disponible puede corresponder a un día anterior. Mantener la fecha efectiva de cada dato y las unidades devueltas. No ofrece dólar blue, MEP, tarjeta, acciones, criptomonedas, operaciones, pronósticos ni recomendaciones de inversión. No admite rangos históricos: el MCP externo permite una fecha por consulta. [Alcance del servidor oficial](https://github.com/lineofflight/frankfurter-mcp).

## Contratos y errores

Las operaciones de consultar_frankfurter devuelven (True, datos) o (False, {"status_code": código}). Cada llamada abre el transporte, inicializa ClientSession, ejecuta call_tool y cierra sesión y transporte; el servidor local puede arrancar aunque Frankfurter esté caído.

Las herramientas públicas mantienen el contrato que reconoce JEV:

```json
{"estado": "Ok", "respuesta": {"datos": "respuesta original del MCP externo"}, "fuente": "Frankfurter", "mcp_externo": "https://mcp.frankfurter.dev/"}
```

Este JSON es ilustrativo: respuesta conserva los datos originales, sin imponer un esquema de resultado no garantizado por el proveedor. Se prioriza structuredContent; si no existe, se decodifica el texto JSON o se conserva el texto. Se mantienen las fechas y el redondeo del servicio remoto.

Un fallo publica estado='Error', respuesta genérica y status_code. Argumentos locales inválidos: 400; fallo de herramienta MCP o respuesta vacía: 502; timeout: 504; fallo HTTP externo: su código HTTP; fallo interno de la herramienta local: 500. El campo status_code pertenece al JSON de negocio y no modifica el HTTP del protocolo MCP. Las validaciones del esquema MCP pueden rechazar argumentos antes de ejecutar la función, con isError. Los bloques except capturan la excepción como e y la incluyen en logger.error mediante %s, junto con el contexto del fallo. No se registran explícitamente argumentos ni cuerpos externos; los mensajes de excepción tampoco deben contener credenciales ni secretos.

El timeout total es 20 segundos, incluyendo inicialización y cierre. Cabe dentro de los 30 segundos del cliente de JEV. No hay reintentos ni llamadas adicionales a LLM.

## Organización

| Archivo o carpeta | Contenido |
| --- | --- |
| server.py | Servidor local y cuatro herramientas. |
| funciones.py | Cliente del MCP externo, validación y errores. |
| requirements.txt | Dependencias. |
| tests/ | Cliente remoto simulado y servidor MCP en memoria. |

## Pruebas

```powershell
.\mcp_finanzas\Scripts\python.exe -m unittest discover -s tests -t . -v
```

La suite simula transporte y sesión externos, sin red ni archivos .env. Comprueba inicialización y cierre, traducción de argumentos, JSON/texto/structuredContent, errores, timeout, entradas inválidas y descubrimiento/ejecución del servidor local con MCP en memoria. La selección de Jeveador y el servicio real requieren una comprobación de integración aparte.

Verificación realizada: las 12 pruebas de la suite pasaron. También se comprobaron dos llamadas reales al MCP público: catálogo de monedas y conversión histórica de USD a EUR. Ambas devolvieron estado Ok. En esa conversión, Frankfurter devolvió un objeto con amount y currency, sin fecha ni tipo de cambio explícitos: no se agregan datos que el proveedor no entrega. La integración con la selección de Jeveador todavía no se probó.
