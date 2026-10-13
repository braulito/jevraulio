"""Entrada de la API y registro de routers."""

from fastapi import FastAPI

from routers import autos, chat, chat_jev, consultas_sql


app = FastAPI(
    title="API Jevs",
    description="Ejecuta todo",
    version="1.0.0",
)

app.include_router(chat.router)

app.include_router(autos.router)

app.include_router(chat_jev.router)
app.include_router(consultas_sql.router)

