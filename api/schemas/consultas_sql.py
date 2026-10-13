"""Cuerpos JSON para administrar el catálogo MCP y el umbral."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResultadoSql(BaseModel):
    resultado: bool
    salida: dict | list


class NuevoMcp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, examples=["mcp_clima"])
    url: str = Field(min_length=1, examples=["http://localhost:8005/mcp"])

    @field_validator("nombre", "url")
    @classmethod
    def limpiar_texto(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El campo no puede estar vacío.")
        return valor


class EstadoMcp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    habilitado: Literal[0, 1]


class NuevoUmbral(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: float = Field(ge=0, le=1, allow_inf_nan=False, examples=[0.85])
