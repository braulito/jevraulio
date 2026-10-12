"""Modelos y validación de mensajes y respuestas de Jev."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from funciones.contexto_config import obtener_max_contexto


EstadoEvaluacion = Literal["sirve", "sirve_parcialmente", "no_sirve", "falta_informacion"]


class ConsultaJev(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mensaje: str = Field(min_length=1, max_length=10000, examples=["¿Cuál es el mejor auto?"])
    contexto: list[str] = Field(default_factory=list, max_length=obtener_max_contexto())

    @field_validator("mensaje")
    @classmethod
    def validar_mensaje(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El mensaje no puede estar vacío.")
        return valor

    @field_validator("contexto")
    @classmethod
    def validar_contexto(cls, mensajes: list[str]) -> list[str]:
        if any(not mensaje.strip() or len(mensaje) > 10000 for mensaje in mensajes):
            raise ValueError("Los mensajes de contexto deben tener entre 1 y 10000 caracteres.")
        return mensajes


class EvaluacionJev(BaseModel):
    estado: EstadoEvaluacion
    mcp_evaluado: str
    motivo: str
    herramientas_aplicables: list[str] = Field(default_factory=list)
    requiere_aclaracion: bool = False


class ComparacionJev(BaseModel):
    mcp_recomendado: str | None = None
    evaluaciones: list[EvaluacionJev] = Field(default_factory=list)


class EleccionJev(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float | None = None
    probabilities: dict[str, float] | None = None


class RespuestaJev(BaseModel):
    answers: dict[str, EleccionJev]
