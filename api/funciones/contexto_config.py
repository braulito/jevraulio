"""Límite del contexto cargado por el servicio."""

import os


def obtener_max_contexto() -> int:
    try:
        limite = int(os.getenv("MAX_CONTEXTO", "20"))
        if limite <= 0:
            raise ValueError
    except ValueError as error:
        raise ValueError("MAX_CONTEXTO debe ser un entero mayor que cero.") from error
    return limite
