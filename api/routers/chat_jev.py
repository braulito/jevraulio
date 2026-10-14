"""Ruta del chat que utiliza Jeveador."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from funciones.chat_jev_funciones import responder_chat_jev
from schemas.chat import RespuestaChat
from schemas.chat_jev import ConsultaChatJev

router = APIRouter(tags=["Chat Jeveador"])
logger = logging.getLogger(__name__)


@router.post("/chat/jev", response_model=RespuestaChat,
             summary="Consultar capacidades o resolver un pedido con Jeveador",
             description="Jeveador identifica la intención. La API describe las capacidades de los MCP habilitados o coordina la ejecución de una herramienta para una consulta concreta.",
             responses={500: {"description": "Error interno al procesar la respuesta del chat."},
                        502: {"description": "Respuesta inválida o fallo de un servicio."},
                        503: {"description": "Configuración o catálogo no disponible."},
                        504: {"description": "Tiempo de espera agotado."}})
async def chat_jev(consulta: ConsultaChatJev) -> RespuestaChat | JSONResponse:
    try:
        resultado = await responder_chat_jev(consulta)
        texto = resultado.respuesta
        if resultado.estado == "error_mcp":
            texto = "La herramienta informó un error: " + texto
        return RespuestaChat(respuesta=texto, herramientas=resultado.herramientas)
    except HTTPException as e:
        logger.error("Error en chat_jev. HTTP %s: %s", e.status_code, e)
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail}, headers=e.headers)
    except Exception as e:
        logger.error("Error interno al procesar la respuesta de chat_jev: %s", e)
        return JSONResponse(status_code=500, content={"detail": "Error interno al procesar la respuesta del chat."})
