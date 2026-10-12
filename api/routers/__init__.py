"""Routers de la API."""

from pathlib import Path

from dotenv import load_dotenv

from funciones.logging_config import configurar_logging

configurar_logging()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
