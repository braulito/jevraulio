"""Entrada y respuesta del chat coordinado por Jeveador."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.chat import ConsultaChat
from funciones.contexto_config import obtener_max_contexto


class ConsultaChatJev(ConsultaChat):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{"mensaje": "¿Cuál es el mejor auto?"}],
    })
    mcp: str | None = Field(default=None, min_length=1, examples=[None], description="Opcional: MCP elegido al resolver varias coincidencias. Omitir para la selección automática.")
    contexto: list[str] = Field(default_factory=list, max_length=obtener_max_contexto(), description="Mensajes recientes para interpretar respuestas como sí o no. Límite configurado en MAX_CONTEXTO.")

    @field_validator("contexto")
    @classmethod
    def validar_contexto(cls, mensajes: list[str]) -> list[str]:
        if any(not mensaje.strip() or len(mensaje) > 10000 for mensaje in mensajes):
            raise ValueError("Cada mensaje de contexto debe tener entre 1 y 10000 caracteres.")
        return mensajes

    @field_validator("mcp", mode="before")
    @classmethod
    def normalizar_mcp(cls, valor):
        if isinstance(valor, str):
            valor = valor.strip()
            # Swagger puede enviar su marcador de ejemplo como si fuera una selección.
            if not valor or valor == "string":
                return None
        return valor


class EvaluacionJev(BaseModel):
    estado: Literal["sirve", "sirve_parcialmente", "no_sirve", "falta_informacion"]
    mcp_evaluado: str = Field(min_length=1)
    motivo: str
    herramientas_aplicables: list[str]
    requiere_aclaracion: bool


class RecomendacionJev(BaseModel):
    mcp_recomendado: str | None
    evaluaciones: list[EvaluacionJev]


class RespuestaChatJev(BaseModel):
    estado: Literal["Ok", "sin_coincidencias", "seleccion_requerida", "requiere_aclaracion", "error_mcp"]
    respuesta: str
    mcp_recomendado: str | None = None
    evaluaciones: list[EvaluacionJev]
    herramientas: list[str] = Field(default_factory=list)
    resultado: dict | None = None
