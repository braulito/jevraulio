"""Carga automática del entorno propio de Jeveador."""

import logging
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# No registrar cuerpos HTTP, URLs de configuración ni credenciales.
for nombre in ("httpx", "httpcore", "mcp.client.streamable_http"):
    logging.getLogger(nombre).setLevel(logging.CRITICAL)
