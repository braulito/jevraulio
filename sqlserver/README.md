# Persistencia SQLite

Esta carpeta contiene el esquema de la base compartida por API y Jeveador. El nombre sqlserver es histórico: el proyecto usa SQLite y no requiere un servidor Microsoft SQL Server.

## Contenido y tablas

esquema.sql crea las tablas y datos mínimos con una transacción. Puede ejecutarse nuevamente: conserva tablas, valores y filas existentes; no realiza migraciones.

| Tabla | Responsabilidad |
| --- | --- |
| errores | Catálogo histórico de descripciones HTTP. Agrega 502, 503 y 504 faltantes; el chat actual declara sus errores en el router. |
| billing | Una fila por respuesta de proveedor: fecha UTC, tokens, costo, método y herramientas. |
| config_umbral | Un registro con id=1 y umbral decimal; valor inicial 0.85. |
| mcps | Catálogo de nombre, URL y habilitación de los servidores MCP. |

El esquema deja el catálogo MCP vacío. Agregá los servidores desde la pantalla MCPs y habilitalos cuando estén encendidos. Las altas de la API fijan habilitado=0. El catálogo vacío no repone MCPs que hayas eliminado.

## Inicialización local

Desde sqlserver, con Python disponible, ejecutá localmente:

```powershell
python -c "import sqlite3; from pathlib import Path; conexion = sqlite3.connect('base.db'); conexion.executescript(Path('esquema.sql').read_text(encoding='utf-8')); conexion.close()"
```

Ese comando crea o inicializa base.db en esta carpeta. Configurá CADENA en API y Jeveador para que ambos apunten al mismo archivo, preferentemente con ruta absoluta. Con la estructura actual, ../sqlserver/base.db desde ambas carpetas también resuelve la misma base. La carpeta contenedora debe existir antes de abrir la conexión.

La tabla errores se conserva por compatibilidad. Tras retirar el router /chat original, la API ya no consulta esa tabla al arrancar; /chat/jev declara sus respuestas HTTP en el router. Las páginas administrativas de Flask consultan la API y no necesitan una conexión directa a esta base.

## Contratos y límites

billing guarda columnas, no prompts, conversaciones ni resultados MCP. Las fechas se almacenan en UTC y la página las convierte a GMT-3. El umbral se guarda como decimal: 0.85 se muestra como 85 por ciento.

El esquema SQL y las funciones de inicialización de los componentes son caminos diferentes. `crear_tabla_mcps()` de Jeveador inserta `mcp_finanzas` con URL `http://127.0.0.1:8006/mcp` y `mcp_clima` con URL `http://localhost:8005/mcp`, ambos con `habilitado = 1`, al crear una tabla nueva. Si la tabla existe, no la modifica ni repuebla. `esquema.sql` permite empezar con el catálogo vacío. Ninguno de estos caminos arranca los servidores MCP.

La base y sus backups son archivos locales excluidos de Git. No hay migraciones automáticas, WAL configurado ni cola de escritura. No ejecutar inicializaciones sobre una base real desde las herramientas del agente.

## Pruebas

Esta carpeta no tiene una suite propia. Las operaciones SQLite y los endpoints se prueban con bases temporales en [api/tests](../api/tests/) y [jeveador/tests](../jeveador/tests/). Los comandos están en los README de esos componentes.
