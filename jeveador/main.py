"""Entrada de Jeveador y registro de routers."""

from fastapi import FastAPI

from funciones import entorno
from routers import jev


app = FastAPI(
    title="Jeveador",
    description="Compara los MCP habilitados en SQLite para el mensaje del usuario.",
    version="1.0.0",
)

app.include_router(jev.router)
