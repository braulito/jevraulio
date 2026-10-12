"""Modelos y validación de datos del chat."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ConsultaChat(BaseModel):
    mensaje: str = Field(min_length=1, max_length=10000, examples=["¿Cuál es el mejor auto?"])

    @field_validator("mensaje")
    @classmethod
    def validar_mensaje(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El mensaje no puede estar vacío.")
        return value


class RespuestaChat(BaseModel):
    estado: Literal["Ok"] = "Ok"
    respuesta: str
    herramientas: list[str] = Field(default_factory=list)


class RespuestaOpenAI(BaseModel):
    status: str
    output: list[dict]


class LlamadaHerramienta(BaseModel):
    name: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    arguments: str
