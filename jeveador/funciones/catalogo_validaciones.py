"""Validación local de catálogos, sin configuración ni llamadas externas."""

import json
import logging
import re
from urllib.parse import urlsplit

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for


logger = logging.getLogger(__name__)
MAX_MCPS = 32
MAX_HERRAMIENTAS_MCP = 64
MAX_HERRAMIENTAS_TOTAL = 256
MAX_PAGINAS_MCP = 64
MAX_DESCRIPCION = 8192
MAX_ESQUEMA_BYTES = 64 * 1024
MAX_CATALOGO_BYTES = 512 * 1024
MAX_PROFUNDIDAD_ESQUEMA = 32
MAX_NODOS_ESQUEMA = 10000
IDENTIFICADOR = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _validar_nombre(nombre) -> None:
    if not isinstance(nombre, str) or not IDENTIFICADOR.fullmatch(nombre):
        raise ValueError("Identificador inválido: usar de 1 a 64 letras ASCII, dígitos, guiones o guiones bajos.")


def _validar_url(url) -> None:
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValueError("URL inválida o mayor a 2048 caracteres.")
    try:
        partes = urlsplit(url)
        partes.port
    except ValueError as e:
        raise ValueError("Sintaxis o puerto inválidos en la URL del MCP.") from None
    if (partes.scheme not in {"http", "https"} or not partes.hostname
            or partes.username is not None or partes.password is not None
            or any(c.isspace() or ord(c) < 32 for c in url)):
        raise ValueError("La URL debe ser HTTP o HTTPS y no contener espacios ni credenciales.")


def _validar_tamano_json(datos, limite: int) -> None:
    try:
        texto = json.dumps(datos, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        longitud = len(texto.encode("utf-8"))
    except (TypeError, ValueError, RecursionError, UnicodeError) as e:
        raise ValueError("Estructura no serializable como JSON válido.") from None
    if longitud > limite:
        raise ValueError(f"El tamaño JSON supera el límite de {limite} bytes UTF-8.")


def _validar_esquema(esquema) -> None:
    if not isinstance(esquema, dict) or esquema.get("type") != "object":
        raise ValueError("inputSchema debe ser un esquema de tipo object.")
    _validar_tamano_json(esquema, MAX_ESQUEMA_BYTES)
    if "$schema" in esquema and not isinstance(esquema["$schema"], str):
        raise ValueError("El dialecto $schema debe ser texto.")
    pendientes = [(esquema, 0)]
    nodos = 0
    while pendientes:
        valor, profundidad = pendientes.pop()
        nodos += 1
        if nodos > MAX_NODOS_ESQUEMA or profundidad > MAX_PROFUNDIDAD_ESQUEMA:
            raise ValueError("El esquema supera los límites de profundidad o cantidad de nodos.")
        if isinstance(valor, dict):
            for clave, contenido in valor.items():
                if not isinstance(clave, str):
                    raise ValueError("Todas las claves del esquema deben ser texto.")
                if clave in {"$ref", "$dynamicRef", "$recursiveRef"}:
                    if not isinstance(contenido, str) or not contenido.startswith("#"):
                        raise ValueError("El esquema solo admite referencias locales; se rechazan referencias externas.")
            pendientes.extend((contenido, profundidad + 1) for contenido in valor.values())
        elif isinstance(valor, list):
            pendientes.extend((contenido, profundidad + 1) for contenido in valor)
    try:
        clase = validator_for(esquema, default=None) if "$schema" in esquema else validator_for(esquema)
        if clase is None:
            raise ValueError("El dialecto JSON Schema no está soportado.")
        clase.check_schema(esquema)
    except SchemaError as e:
        # No registrar e: contiene el esquema externo y sus posibles secretos.
        raise ValueError("inputSchema no cumple el dialecto JSON Schema indicado.") from None


def validar_registros_mcps(registros) -> tuple[bool, list[dict] | dict]:
    """Validar los MCP habilitados antes de abrir conexiones; errores de configuración: 503."""
    try:
        if not isinstance(registros, list):
            raise ValueError("El registro de MCP debe ser una lista.")
        activos = []
        nombres = set()
        for indice, registro in enumerate(registros):
            if not isinstance(registro, dict) or type(registro.get("habilitado")) is not int or registro["habilitado"] not in (0, 1):
                raise ValueError(f"Registro MCP {indice}: estructura o habilitado inválido.")
            if registro["habilitado"] == 0:
                continue
            _validar_nombre(registro.get("nombre"))
            _validar_url(registro.get("url"))
            if registro["nombre"] in nombres:
                raise ValueError("El registro contiene nombres de MCP habilitados duplicados.")
            nombres.add(registro["nombre"])
            activos.append(registro)
            if len(activos) > MAX_MCPS:
                raise ValueError(f"El registro supera el límite de {MAX_MCPS} MCP habilitados.")
        return True, activos
    except Exception as e:
        # Los ValueError propios describen la causa sin incluir nombres, URLs o cuerpos externos.
        detalle = e if isinstance(e, ValueError) else type(e).__name__
        logger.error("Error en validar_registros_mcps: %s", detalle)
        return False, {"status_code": 503 if isinstance(e, ValueError) else 500}


def validar_herramientas(herramientas) -> tuple[bool, list[dict] | dict]:
    """Validar las herramientas de un MCP; catálogo publicado inválido: 502."""
    try:
        if not isinstance(herramientas, list) or len(herramientas) > MAX_HERRAMIENTAS_MCP:
            raise ValueError(f"El catálogo debe ser una lista de hasta {MAX_HERRAMIENTAS_MCP} herramientas.")
        nombres = set()
        validas = []
        for indice, herramienta in enumerate(herramientas):
            try:
                if not isinstance(herramienta, dict):
                    raise ValueError("La herramienta debe ser un objeto.")
                nombre = herramienta.get("name")
                _validar_nombre(nombre)
                if nombre in nombres:
                    raise ValueError("Nombre de herramienta duplicado dentro del MCP.")
                descripcion = herramienta.get("description", "")
                if not isinstance(descripcion, str) or len(descripcion) > MAX_DESCRIPCION:
                    raise ValueError(f"La descripción debe ser texto de hasta {MAX_DESCRIPCION} caracteres.")
                esquema = herramienta.get("inputSchema")
                _validar_esquema(esquema)
                nombres.add(nombre)
                validas.append({"name": nombre, "description": descripcion, "inputSchema": esquema})
            except ValueError as e:
                raise ValueError(f"Herramienta {indice}: {e}") from None
        _validar_tamano_json(validas, MAX_CATALOGO_BYTES)
        return True, validas
    except Exception as e:
        detalle = e if isinstance(e, ValueError) else type(e).__name__
        logger.error("Error en validar_herramientas: %s", detalle)
        return False, {"status_code": 502 if isinstance(e, ValueError) else 500}


def validar_catalogos(catalogos) -> tuple[bool, list[dict] | dict]:
    """Validar el conjunto completo antes de enviarlo a Jev, también en consultas de capacidades."""
    try:
        if not isinstance(catalogos, list) or len(catalogos) > MAX_MCPS:
            raise ValueError(f"Se admiten hasta {MAX_MCPS} catálogos MCP.")
        nombres = set()
        total = 0
        validos = []
        for indice, catalogo in enumerate(catalogos):
            if not isinstance(catalogo, dict):
                raise ValueError(f"Catálogo {indice}: debe ser un objeto.")
            nombre = catalogo.get("nombre")
            _validar_nombre(nombre)
            if nombre in nombres:
                raise ValueError("Nombre MCP duplicado en los catálogos.")
            resultado, salida = validar_herramientas(catalogo.get("herramientas"))
            if not resultado:
                return False, salida
            total += len(salida)
            if total > MAX_HERRAMIENTAS_TOTAL:
                raise ValueError(f"Los catálogos superan el límite total de {MAX_HERRAMIENTAS_TOTAL} herramientas.")
            nombres.add(nombre)
            validos.append({"nombre": nombre, "herramientas": salida})
        _validar_tamano_json(validos, MAX_CATALOGO_BYTES)
        return True, validos
    except Exception as e:
        detalle = e if isinstance(e, ValueError) else type(e).__name__
        logger.error("Error en validar_catalogos: %s", detalle)
        return False, {"status_code": 502 if isinstance(e, ValueError) else 500}
