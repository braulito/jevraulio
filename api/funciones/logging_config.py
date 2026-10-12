"""Configuración común del logging de la API y Uvicorn."""

import json
import logging.config
from pathlib import Path


def configurar_logging() -> None:
    """Da contexto a los logs de la aplicación y conserva el formato de Uvicorn."""
    archivo = Path(__file__).resolve().parent.parent / "logging.json"
    with archivo.open(encoding="utf-8") as configuracion:
        logging.config.dictConfig(json.load(configuracion))
