"""Ruta HTTP para evaluar el mensaje del usuario."""

from fastapi import APIRouter

from funciones.jev_funciones import evaluar_mensaje
from schemas.jev import ComparacionJev, ConsultaJev


router = APIRouter(tags=["Jev"])

ERRORES = {
    500: {"description": "No se pudo guardar el consumo de Jev en SQLite."},
    502: {"description": "Error del MCP, de Jev o de sus respuestas."},
    503: {"description": "Configuración incompleta, tabla mcps inaccesible, sin MCP habilitados o URL inválida."},
    504: {"description": "Tiempo de espera agotado."},
}


@router.post(
    "/evaluar",
    response_model=ComparacionJev,
    summary="Comparar los MCP habilitados para el pedido",
    description="Lee mcps en cada consulta, descubre sus herramientas y las compara con Jev. No las ejecuta.",
    responses=ERRORES,
)
async def evaluar(consulta: ConsultaJev) -> ComparacionJev:
    return await evaluar_mensaje(consulta)
