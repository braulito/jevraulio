# MCP Cocina

Servidor Python con dos herramientas, construido con [FastMCP del SDK oficial](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).

Desde esta carpeta, instalar las dependencias y ejecutar en PowerShell:

```powershell
.\mcp_cocina\Scripts\python.exe -m pip install -r requirements.txt
.\mcp_cocina\Scripts\python.exe server.py
```

Endpoint MCP: `http://127.0.0.1:8004/mcp` (Streamable HTTP).

Se desactiva la carga automática de archivos `.env` de FastMCP. El servidor no necesita esos archivos.

- `mejor_plato()`: devuelve `{"estado": "Ok", "respuesta": "Milanesas"}`.
- `es_mejor_plato(plato: str)`: devuelve `{"estado": "Ok", "respuesta": "Si"}` para Milanesas y `"No"` para otros platos. Ignora mayúsculas y espacios al principio y al final.

Cada herramienta tiene su propio `try/except`. Ante una excepción, registra el error con `logging.error` y devuelve `{"estado": "Error", "respuesta": "Error interno", "status_code": 500}`. El campo `status_code` pertenece al resultado de la herramienta; no cambia el estado HTTP de la respuesta MCP.

Las definiciones se generan desde las funciones decoradas con `@mcp.tool()`: el nombre de la función define `name`, el docstring define `description` y los tipos y metadatos `Annotated` / `Field` definen `inputSchema`. `plato` es obligatorio porque no tiene un valor por defecto. La API puede consultar `list_tools()` y adaptar estas definiciones para OpenAI sin mantener un catálogo fijo. Reiniciar el servidor después de agregar o modificar funciones para publicar los cambios.

Para verificar los metadatos, las llamadas y el descubrimiento automático con un cliente MCP en memoria (sin Node.js ni un servidor externo):

```powershell
.\mcp_cocina\Scripts\python.exe -m unittest test_list_tools -v
```

La prueba registra una tercera herramienta temporal, comprueba que `list_tools()` la descubre y la elimina al finalizar.
