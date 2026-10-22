"""Permisos locales y validación de resultados independientes de Jev y del catálogo."""

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit


logger = logging.getLogger(__name__)
RUTA_POLITICA = Path(__file__).resolve().parent.parent / "politica_mcp.json"
MAX_RESULTADO_BYTES = 128 * 1024
MAX_TEXTO_BYTES = 64 * 1024
MAX_BLOQUES = 32
MAX_PROFUNDIDAD = 16
MAX_NODOS = 10000


def _normalizar_destino(url: str) -> str:
    """Solo literales loopback; localhost se conecta como 127.0.0.1 sin resolver DNS."""
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Formato de destino MCP inválido.")
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError as e:
        raise ValueError("Sintaxis de destino MCP inválida.") from None
    if (partes.scheme != "http" or partes.hostname not in {"localhost", "127.0.0.1", "::1"}
            or puerto is None or partes.username is not None or partes.password is not None
            or partes.query or partes.fragment or partes.path not in {"", "/", "/mcp", "/mcp/"}):
        raise ValueError("Destino MCP no permitido: solo endpoints loopback explícitos, sin credenciales ni parámetros.")
    host = "[::1]" if partes.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{puerto}/mcp"


def _leer_politica() -> dict:
    datos = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or not isinstance(datos.get("mcps"), dict):
        raise ValueError("La política debe declarar un objeto mcps.")
    for nombre, entrada in datos["mcps"].items():
        if not isinstance(nombre, str) or not isinstance(entrada, dict):
            raise ValueError("Registro inválido en la política MCP.")
        _normalizar_destino(entrada.get("url"))
        tools = entrada.get("herramientas")
        if not isinstance(tools, list) or any(not isinstance(t, str) or not t for t in tools):
            raise ValueError("La política debe declarar una lista de herramientas.")
    return datos["mcps"]


def validar_destino(url: str) -> tuple[bool, str | dict]:
    try:
        try:
            politica = _leer_politica()
        except Exception as e:
            logger.error("Error en validar_destino al leer la política: %s", e if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else type(e).__name__)
            return False, {"status_code": 503}
        destino = _normalizar_destino(url)
        if not any(_normalizar_destino(entrada["url"]) == destino for entrada in politica.values()):
            raise ValueError("El destino no está autorizado en la política local.")
        return True, destino
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Error en validar_destino: política local no disponible (%s).", type(e).__name__)
        return False, {"status_code": 503}
    except Exception as e:
        logger.error("Error en validar_destino: %s", e)
        return False, {"status_code": 403}


def autorizar_herramienta(nombre: str, url: str, mcp: str | None = None) -> tuple[bool, str | dict]:
    try:
        try:
            politica = _leer_politica()
        except Exception as e:
            logger.error("Error en autorizar_herramienta al leer la política: %s", e if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else type(e).__name__)
            return False, {"status_code": 503}
        destino = _normalizar_destino(url)
        for servidor, entrada in politica.items():
            if mcp is not None and servidor != mcp:
                continue
            if _normalizar_destino(entrada["url"]) == destino and nombre in entrada["herramientas"]:
                return True, destino
        raise ValueError("La herramienta no tiene permiso para ese MCP y destino.")
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Error en autorizar_herramienta: política local no disponible (%s).", type(e).__name__)
        return False, {"status_code": 503}
    except Exception as e:
        logger.error("Error en autorizar_herramienta: %s", e)
        return False, {"status_code": 403}


def validar_resultado_mcp(resultado) -> tuple[bool, dict]:
    try:
        if not isinstance(resultado, dict):
            raise ValueError("El resultado MCP debe ser un objeto.")
        if "isError" in resultado and type(resultado["isError"]) is not bool:
            raise ValueError("isError debe ser booleano.")
        bloques = resultado.get("content", [])
        estructurado = resultado.get("structuredContent")
        if not isinstance(bloques, list) or len(bloques) > MAX_BLOQUES:
            raise ValueError("Cantidad o estructura de bloques MCP inválida.")
        if estructurado is not None and not isinstance(estructurado, dict):
            raise ValueError("structuredContent debe ser un objeto.")
        if not bloques and estructurado is None:
            raise ValueError("El resultado MCP no contiene datos.")
        for bloque in bloques:
            if not isinstance(bloque, dict) or bloque.get("type") != "text" or not isinstance(bloque.get("text"), str):
                raise ValueError("Solo se admiten bloques MCP de texto; no se cargan recursos externos.")
            if len(bloque["text"].encode("utf-8")) > MAX_TEXTO_BYTES:
                raise ValueError("Un bloque de texto supera 64 KiB.")
        try:
            longitud = len(json.dumps(resultado, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError, RecursionError, UnicodeError) as e:
            raise ValueError("El resultado no es JSON válido.") from None
        if longitud > MAX_RESULTADO_BYTES:
            raise ValueError("El resultado MCP supera 128 KiB.")
        pendientes = [(resultado, 0)]
        nodos = 0
        while pendientes:
            valor, profundidad = pendientes.pop()
            nodos += 1
            if profundidad > MAX_PROFUNDIDAD or nodos > MAX_NODOS:
                raise ValueError("El resultado supera los límites de profundidad o nodos.")
            if isinstance(valor, dict):
                if any(not isinstance(clave, str) for clave in valor):
                    raise ValueError("El resultado contiene claves no textuales.")
                pendientes.extend((v, profundidad + 1) for v in valor.values())
            elif isinstance(valor, list):
                pendientes.extend((v, profundidad + 1) for v in valor)
        # No transferir metadatos ni campos desconocidos al redactor.
        limpio = {}
        if "isError" in resultado:
            limpio["isError"] = resultado["isError"]
        if "content" in resultado:
            limpio["content"] = [{"type": "text", "text": b["text"]} for b in bloques]
        if estructurado is not None:
            limpio["structuredContent"] = estructurado
        return True, limpio
    except Exception as e:
        logger.error("Error en validar_resultado_mcp: %s", e)
        return False, {"status_code": 502}


def validar_definiciones_mcp(herramientas) -> tuple[bool, list[dict] | dict]:
    """Comprobar el catálogo que la API vuelve a descubrir, sin resolver referencias externas."""
    try:
        if not isinstance(herramientas, list) or len(herramientas) > 64:
            raise ValueError("El catálogo de ejecución admite hasta 64 herramientas.")
        nombres = set()
        for herramienta in herramientas:
            if not isinstance(herramienta, dict):
                raise ValueError("La definición de herramienta debe ser un objeto.")
            nombre = herramienta.get("name")
            if not isinstance(nombre, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", nombre) or nombre in nombres:
                raise ValueError("Identificador de herramienta inválido o duplicado.")
            nombres.add(nombre)
            descripcion = herramienta.get("description", "")
            if not isinstance(descripcion, str) or len(descripcion) > 8192:
                raise ValueError("La descripción excede el límite del catálogo.")
            esquema = herramienta.get("parameters")
            if not isinstance(esquema, dict) or esquema.get("type") != "object":
                raise ValueError("Los parámetros deben ser un esquema object.")
            if len(json.dumps(esquema, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 64 * 1024:
                raise ValueError("El esquema excede 64 KiB.")
            pendientes = [(esquema, 0)]
            nodos = 0
            while pendientes:
                valor, profundidad = pendientes.pop()
                nodos += 1
                if profundidad > 32 or nodos > 10000:
                    raise ValueError("El esquema supera los límites de profundidad o nodos.")
                if isinstance(valor, dict):
                    for clave in ("$ref", "$dynamicRef", "$recursiveRef"):
                        if clave in valor and (not isinstance(valor[clave], str) or not valor[clave].startswith("#")):
                            raise ValueError("El esquema de ejecución contiene referencias externas no permitidas.")
                    pendientes.extend((v, profundidad + 1) for v in valor.values())
                elif isinstance(valor, list):
                    pendientes.extend((v, profundidad + 1) for v in valor)
        if len(json.dumps(herramientas, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 512 * 1024:
            raise ValueError("El catálogo de ejecución excede 512 KiB.")
        return True, herramientas
    except Exception as e:
        # Los fallos propios no incluyen el contenido del catálogo.
        detalle = e if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else type(e).__name__
        logger.error("Error en validar_definiciones_mcp: %s", detalle)
        return False, {"status_code": 502}
