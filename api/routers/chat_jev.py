"""Ruta independiente del chat que utiliza Jeveador."""

import logging

from fastapi import APIRouter, HTTPException

from funciones.chat_jev_funciones import responder_chat_jev
from schemas.chat import RespuestaChat
from schemas.chat_jev import ConsultaChatJev

router = APIRouter(tags=["Chat Jeveador"])
logger = logging.getLogger(__name__)


@router.post("/chat/jev", response_model=RespuestaChat,
             summary="Evaluar con Jeveador y ejecutar en el MCP seleccionado",
             responses={502: {"description": "Respuesta inválida o fallo de un servicio."},
                        503: {"description": "Configuración o catálogo no disponible."},
                        504: {"description": "Tiempo de espera agotado."}})
async def chat_jev(consulta: ConsultaChatJev) -> RespuestaChat:
    try:
        resultado = await responder_chat_jev(consulta)
    except HTTPException as error:
        logger.error("Falló /chat/jev. HTTP %s: %s", error.status_code, error.detail)
        raise
    texto = resultado.respuesta
    if resultado.estado == "error_mcp":
        texto = "La herramienta informó un error: " + texto
    return RespuestaChat(respuesta=texto, herramientas=resultado.herramientas)
