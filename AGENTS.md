# Instrucciones para agentes

## Contrato de funciones y API

- Las funciones de operaciones deben devolver `(resultado, salida)`: `(True, datos)` si funcionan y `(False, {"status_code": codigo})` si fallan.
- Envolver las operaciones en `try`, capturar `Exception`, registrar el error sin secretos y terminar devolviendo el fallo.
- Los endpoints administrativos SQL publican `{"resultado": bool, "salida": datos}` y conservan los códigos HTTP correspondientes. No convertir todos los errores en 200 ni en un único código.
- Costos, MCPs y Umbral deben comprobar el resultado de las llamadas y mostrar el modal cuando falla la API.
- En las consultas de listados de Costos y MCPs, HTTP 404 significa ausencia de información: mostrar un mensaje en el lugar de la tabla sin modal. Esta excepción no aplica a escrituras ni a Umbral.

## Protección de secretos

- Nunca leer, abrir, copiar, modificar ni mostrar el contenido de archivos `.env`, `.env.*` o `*.env` en ninguna carpeta del proyecto.
- Excluir esos archivos de búsquedas de contenido, lecturas masivas, indexación, diferencias y comandos de diagnóstico. No acceder mediante enlaces, copias, scripts, herramientas externas ni otros métodos indirectos.
- No ejecutar aplicaciones, importar módulos ni cargar configuraciones que lean esos archivos para inspeccionarlos o verificar sus valores. Las pruebas que los necesiten deben ejecutarlas el usuario fuera de las herramientas del agente.
- Nunca imprimir variables de entorno, credenciales o secretos. No solicitar al usuario que los pegue en el chat.
- Trabajar con nombres de variables y valores ficticios. Si hace falta una comprobación del archivo real, explicar cómo puede realizarla el usuario localmente.
- No solicitar permisos elevados ni intentar eludir una denegación de acceso a estos archivos.

Estas instrucciones son una regla de comportamiento. El bloqueo técnico debe configurarse adicionalmente en los permisos del entorno de Codex. `.gitignore` no bloquea la lectura por parte del agente.
