"""Ruta HTTP del chat."""

from fastapi import APIRouter

from funciones.base_sqlite import obtener_errores
from funciones.chat_funciones import responder_chat
from schemas.chat import ConsultaChat, RespuestaChat


router = APIRouter(tags=["Chat"])


@router.post(
    "/chat",
    response_model=RespuestaChat,
    summary="Conversar con OpenAI usando las herramientas descubiertas en el MCP",
    description="Cada petición procesa un mensaje independiente; no guarda historial entre peticiones.",
    responses=obtener_errores(),
)
async def chat(consulta: ConsultaChat) -> RespuestaChat:
    return await responder_chat(consulta.mensaje)
