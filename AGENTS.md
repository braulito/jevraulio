# Instrucciones para agentes

## Protección de secretos

- Nunca leer, abrir, copiar, modificar ni mostrar el contenido de archivos `.env`, `.env.*` o `*.env` en ninguna carpeta del proyecto.
- Excluir esos archivos de búsquedas de contenido, lecturas masivas, indexación, diferencias y comandos de diagnóstico. No acceder mediante enlaces, copias, scripts, herramientas externas ni otros métodos indirectos.
- No ejecutar aplicaciones, importar módulos ni cargar configuraciones que lean esos archivos para inspeccionarlos o verificar sus valores. Las pruebas que los necesiten deben ejecutarlas el usuario fuera de las herramientas del agente.
- Nunca imprimir variables de entorno, credenciales o secretos. No solicitar al usuario que los pegue en el chat.
- Trabajar con nombres de variables y valores ficticios. Si hace falta una comprobación del archivo real, explicar cómo puede realizarla el usuario localmente.
- No solicitar permisos elevados ni intentar eludir una denegación de acceso a estos archivos.

Estas instrucciones son una regla de comportamiento. El bloqueo técnico debe configurarse adicionalmente en los permisos del entorno de Codex. `.gitignore` no bloquea la lectura por parte del agente.
