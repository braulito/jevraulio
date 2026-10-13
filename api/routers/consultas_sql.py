"""Endpoints administrativos SQL con resultado/salida y códigos HTTP."""

import logging
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from funciones import consultas_sql_funciones as sql
from schemas.consultas_sql import EstadoMcp, NuevoMcp, NuevoUmbral, ResultadoSql


class RutaSql(APIRoute):
    """Conserva HTTP 422 y el contrato JSON cuando falla la validación."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def manejar(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={
                    "resultado": False, "salida": {"status_code": 422},
                })

        return manejar


router = APIRouter(prefix="/consultas_sql", tags=["admin sql"], route_class=RutaSql,
                   default_response_class=JSONResponse, responses={
    400: {"description": "Datos inválidos.", "model": ResultadoSql},
    404: {"description": "Registro inexistente.", "model": ResultadoSql},
    409: {"description": "Conflicto con un registro existente.", "model": ResultadoSql},
    422: {"description": "Error de validación.", "model": ResultadoSql},
    500: {"description": "Error interno.", "model": ResultadoSql},
    503: {"description": "Base de datos o tabla no disponible.", "model": ResultadoSql},
})
logger = logging.getLogger(__name__)
IdMcp = Annotated[int, Path(ge=1)]


def ejecutar_sql(operacion, *args, codigo_exito=200, **kwargs):
    try:
        resultado, salida = operacion(*args, **kwargs)
        if type(resultado) is not bool or not isinstance(salida, (dict, list)):
            raise ValueError("Contrato SQL inválido.")
        codigo = codigo_exito
        if not resultado:
            codigo = salida.get("status_code") if isinstance(salida, dict) else None
            if type(codigo) is not int or codigo not in {400, 404, 409, 422, 500, 503}:
                raise ValueError("Código de error SQL inválido.")
        return JSONResponse(status_code=codigo, content={"resultado": resultado, "salida": salida})
    except Exception as error:
        logger.error("Falló una consulta SQL administrativa. Tipo: %s", type(error).__name__)
        return JSONResponse(status_code=500, content={"resultado": False, "salida": {"status_code": 500}})


@router.get("/costos", response_model=ResultadoSql, summary="Consultar consumos paginados y totales por grupo")
def costos(pagina: int = 1, pagina_size: Annotated[int, Query(ge=1, le=2147483647)] = 50,
           mostrar_jev: bool = True, mostrar_openai: bool = True):
    return ejecutar_sql(sql.obtener_costos, pagina, pagina_size, mostrar_jev, mostrar_openai)


@router.get("/mcps", response_model=ResultadoSql, summary="Listar todos los MCPs, habilitados y deshabilitados")
def mcps():
    return ejecutar_sql(sql.obtener_mcps)


@router.get("/mcps/{id_mcp}", response_model=ResultadoSql, summary="Consultar un MCP por ID")
def mcp(id_mcp: IdMcp):
    return ejecutar_sql(sql.obtener_mcp, id_mcp)


@router.post("/mcps", status_code=201, response_model=ResultadoSql, summary="Agregar un MCP deshabilitado")
def crear_mcp(datos: NuevoMcp):
    return ejecutar_sql(sql.agregar_mcp, datos.nombre, datos.url, codigo_exito=201)


@router.patch("/mcps/{id_mcp}", response_model=ResultadoSql, summary="Habilitar o deshabilitar un MCP")
def estado_mcp(id_mcp: IdMcp, datos: EstadoMcp):
    return ejecutar_sql(sql.guardar_estado_mcp, id_mcp, datos.habilitado)


@router.delete("/mcps/{id_mcp}", response_model=ResultadoSql, summary="Eliminar un MCP del catálogo")
def borrar_mcp(id_mcp: IdMcp):
    return ejecutar_sql(sql.eliminar_mcp, id_mcp)


@router.get("/umbral", response_model=ResultadoSql, summary="Consultar el umbral guardado, entre 0 y 1")
def umbral():
    return ejecutar_sql(sql.obtener_umbral)


@router.put("/umbral", response_model=ResultadoSql, summary="Actualizar el umbral existente, entre 0 y 1")
def actualizar_umbral(datos: NuevoUmbral):
    return ejecutar_sql(sql.guardar_umbral, Decimal(str(datos.valor)))
