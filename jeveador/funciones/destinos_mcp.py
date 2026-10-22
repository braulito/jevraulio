"""Control de destinos de descubrimiento antes de abrir conexiones MCP."""

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit


logger = logging.getLogger(__name__)
RUTA_POLITICA = Path(__file__).resolve().parent.parent / "destinos_mcp.json"


def _normalizar(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Formato del destino MCP inválido.")
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError as e:
        raise ValueError("Sintaxis del destino MCP inválida.") from None
    if (partes.scheme != "http" or partes.hostname not in {"localhost", "127.0.0.1", "::1"}
            or puerto is None or partes.username is not None or partes.password is not None
            or partes.query or partes.fragment or partes.path not in {"", "/", "/mcp", "/mcp/"}):
        raise ValueError("Solo se admiten destinos loopback explícitos, sin credenciales ni parámetros.")
    host = "[::1]" if partes.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{puerto}/mcp"


def validar_destino(url: str) -> tuple[bool, str | dict]:
    try:
        destino = _normalizar(url)
        politica = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))
        destinos = politica.get("destinos") if isinstance(politica, dict) else None
        if not isinstance(destinos, list):
            raise ValueError("La política de destinos debe contener una lista destinos.")
        permitidos = {_normalizar(entrada) for entrada in destinos}
        if destino not in permitidos:
            raise ValueError("El destino MCP no está autorizado en la política local.")
        return True, destino
    except Exception as e:
        # No registrar la URL, el contenido del archivo ni credenciales.
        detalle = e if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else type(e).__name__
        logger.error("Error en validar_destino: %s", detalle)
        return False, {"status_code": 503}
