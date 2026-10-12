"""Consultas de costos y configuración del umbral en SQLite."""

import os
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path


DIRECTORIO_PAGINA = Path(__file__).resolve().parent


def conectar(cadena: str | None = None, *, solo_lectura: bool = True) -> sqlite3.Connection:
    """Abre una base existente; por defecto solo permite leerla."""
    ruta = cadena if cadena is not None else os.getenv("CADENA", "")
    if not ruta or not ruta.strip():
        raise ValueError("Falta configurar CADENA con la ruta de la base SQLite.")

    archivo = Path(ruta.strip()).expanduser()
    if not archivo.is_absolute():
        archivo = DIRECTORIO_PAGINA / archivo

    modo = "ro" if solo_lectura else "rw"
    conexion = sqlite3.connect(archivo.resolve().as_uri() + f"?mode={modo}", uri=True, timeout=30)
    conexion.row_factory = sqlite3.Row
    return conexion


def obtener_umbral(cadena: str | None = None) -> Decimal:
    with closing(conectar(cadena)) as conexion:
        registro = conexion.execute("SELECT valor FROM config_umbral WHERE id = 1").fetchone()
    if registro is None:
        raise RuntimeError("No existe el registro del umbral.")
    return Decimal(str(registro["valor"]))


def guardar_umbral(valor: Decimal, cadena: str | None = None) -> None:
    """Actualiza únicamente el registro existente; nunca crea tablas ni filas."""
    if not valor.is_finite() or not Decimal("0") <= valor <= Decimal("1"):
        raise ValueError("El umbral debe estar entre 0 y 1.")
    with closing(conectar(cadena, solo_lectura=False)) as conexion:
        with conexion:
            cursor = conexion.execute(
                "UPDATE config_umbral SET valor = ? WHERE id = 1", (float(valor),)
            )
            if cursor.rowcount != 1:
                raise RuntimeError("No existe el registro del umbral.")


def obtener_costos(
    cadena: str | None = None, pagina: int = 1, pagina_size: int = 50,
    mostrar_jev: bool = True, mostrar_openai: bool = True,
) -> dict:
    """Consulta una página y los totales globales en la misma lectura."""
    if pagina_size < 1:
        raise ValueError("El tamaño de página debe ser positivo.")
    with closing(conectar(cadena)) as conexion:
        conexion.execute("BEGIN")
        resumen = conexion.execute(
            """
            SELECT COUNT(CASE WHEN
                       (? AND metodo = 'JEV')
                       OR (? AND (metodo IS NULL OR metodo <> 'JEV'))
                       THEN 1 END) AS total_registros,
                   COALESCE(SUM(CASE WHEN metodo = 'JEV'
                       THEN costo_estimado_usd ELSE 0 END), 0) AS costo_jev,
                   COALESCE(SUM(CASE WHEN metodo = 'JEV'
                       THEN 0 ELSE costo_estimado_usd END), 0) AS costo_openai,
                   COALESCE(SUM(CASE WHEN metodo = 'JEV'
                       THEN total_tokens ELSE 0 END), 0) AS tokens_jev,
                   COALESCE(SUM(CASE WHEN metodo = 'JEV'
                       THEN 0 ELSE total_tokens END), 0) AS tokens_openai
            FROM billing
            """,
            (mostrar_jev, mostrar_openai),
        ).fetchone()
        total = resumen["total_registros"]
        total_paginas = max(1, (total + pagina_size - 1) // pagina_size)
        pagina = min(max(1, pagina), total_paginas)
        offset = (pagina - 1) * pagina_size
        registros = conexion.execute(
            """
            SELECT id, fecha_utc, input_tokens, cached_tokens, cache_write_tokens,
                   output_tokens, reasoning_tokens, total_tokens,
                   costo_estimado_usd, metodo, herramientas
            FROM billing
            WHERE (? AND metodo = 'JEV')
               OR (? AND (metodo IS NULL OR metodo <> 'JEV'))
            ORDER BY fecha_utc DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (mostrar_jev, mostrar_openai, pagina_size, offset),
        ).fetchall()
    return {
        "registros": registros,
        "mostrar_jev": mostrar_jev,
        "mostrar_openai": mostrar_openai,
        "costo_jev": resumen["costo_jev"],
        "costo_openai": resumen["costo_openai"],
        "tokens_jev": resumen["tokens_jev"],
        "tokens_openai": resumen["tokens_openai"],
        "total_registros": total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "desde": offset + 1 if total else 0,
        "hasta": offset + len(registros),
    }
