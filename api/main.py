"""Entrada de la API: chat con Jeveador y administración SQL."""

from fastapi import FastAPI

from routers import chat_jev, consultas_sql


app = FastAPI(
    title="API JEVraulio",
    description="Chat con Jeveador, ejecución MCP y administración SQL.",
    version="1.0.0",
)

app.include_router(chat_jev.router)
app.include_router(consultas_sql.router)
