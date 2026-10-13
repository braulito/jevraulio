"""Conexión SQLite y registro aplanado de billing para Jeveador."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import logging

from fastapi import HTTPException


DIRECTORIO_JEV = Path(__file__).resolve().parent.parent
try:
    UMBRAL_DEFECTO = float(os.getenv("UMBRAL_DEFECTO", "").strip())
except ValueError:
    UMBRAL_DEFECTO = 0.5


def conectar() -> sqlite3.Connection:
    cadena = os.getenv("CADENA", "").strip()
    if not cadena:
        raise HTTPException(status_code=503, detail="Falta configurar CADENA en jeveador/.env con la ruta del archivo SQLite.")
    archivo = Path(cadena).expanduser()
    if not archivo.is_absolute():
        archivo = DIRECTORIO_JEV / archivo
    conexion = sqlite3.connect(str(archivo), timeout=30)
    conexion.row_factory = sqlite3.Row
    return conexion


@contextmanager
def conexion_sqlite() -> Iterator[sqlite3.Connection]:
    """Confirma o revierte la transacción y cierra siempre la conexión."""
    conexion = conectar()
    try:
        yield conexion
        conexion.commit()
    except BaseException:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def guardar_billing(
    *,
    input_tokens: int = 0,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    total_tokens: int | None = None,
    costo_estimado_usd: float = 0,
) -> int:
    """Recibe columnas aplanadas; método y herramientas siempre son JEV."""
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
    try:
        with conexion_sqlite() as conexion:
            cursor = conexion.execute("""
                INSERT INTO billing (
                    input_tokens, cached_tokens, cache_write_tokens, output_tokens,
                    reasoning_tokens, total_tokens, costo_estimado_usd, metodo, herramientas
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                input_tokens, cached_tokens, cache_write_tokens, output_tokens,
                reasoning_tokens, total_tokens, costo_estimado_usd, "JEV", "JEV",
            ))
            return cursor.lastrowid
    except sqlite3.Error:
        raise HTTPException(status_code=500, detail="No se pudo guardar el consumo de Jev. Revisá CADENA y la tabla billing localmente.") from None


def crear_tabla_billing() -> None:
    """Inicialización opcional con la misma definición que la API."""
    with conexion_sqlite() as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS billing (
                id INTEGER PRIMARY KEY,
                fecha_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                input_tokens INTEGER,
                cached_tokens INTEGER,
                cache_write_tokens INTEGER,
                output_tokens INTEGER,
                reasoning_tokens INTEGER,
                total_tokens INTEGER,
                costo_estimado_usd REAL,
                metodo TEXT,
                herramientas TEXT NOT NULL
            )
        """)


def crear_tabla_config_umbral() -> None:
    """Crear la configuración con un único registro inicial de valor 0.85."""
    with conexion_sqlite() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        existe = conexion.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("config_umbral",),
        ).fetchone()
        if existe:
            return
        conexion.execute("""
            CREATE TABLE config_umbral (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                valor REAL NOT NULL
            )
        """)
        conexion.execute("INSERT INTO config_umbral (id, valor) VALUES (?, ?)", (1, 0.85))


def obtener_umbral() -> float:
    """Leer config_umbral y usar UMBRAL_DEFECTO si no se puede obtener."""
    try:
        with conexion_sqlite() as conexion:
            fila = conexion.execute("SELECT valor FROM config_umbral WHERE id = 1").fetchone()
            if fila is None:
                logging.warning("Falta el registro de config_umbral con id = 1. Se usará UMBRAL_DEFECTO.")
                return UMBRAL_DEFECTO
            
            return float(fila["valor"])
    except Exception as error:
        logging.error(
            "Error al obtener el umbral: %s: %s. Se usará UMBRAL_DEFECTO.",
            type(error).__name__,
            error,
            exc_info=True,
        )
        return UMBRAL_DEFECTO


def obtener_mcps() -> list[dict]:
    """Devolver todos los MCP registrados, ordenados por id."""
    with conexion_sqlite() as conexion:
        filas = conexion.execute("SELECT id, nombre, url, habilitado FROM mcps ORDER BY id").fetchall()
        return [dict(fila) for fila in filas]


def insertar_mcp_clima_temporal() -> None:
    """Insertar MCP Clima en mcps si aún no está registrado. Uso temporal."""
    with conexion_sqlite() as conexion:
        conexion.execute(
            """
            INSERT INTO mcps (nombre, url, habilitado)
            VALUES (?, ?, ?)
            ON CONFLICT(nombre) DO NOTHING
            """,
            ("mcp_clima", "http://localhost:8005/mcp", 1),
        )


def crear_tabla_mcps() -> None:
    """Crear el catálogo y sus datos iniciales solo si la tabla no existe."""
    with conexion_sqlite() as conexion:
        # Mantener la comprobación, creación e inserción en una transacción.
        conexion.execute("BEGIN IMMEDIATE")
        existe = conexion.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("mcps",),
        ).fetchone()
        if existe:
            return
        conexion.execute("""
            CREATE TABLE mcps (
                id INTEGER PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                habilitado INTEGER NOT NULL DEFAULT 1 CHECK (habilitado IN (0, 1))
            )
        """)
        conexion.executemany(
            "INSERT INTO mcps (nombre, url, habilitado) VALUES (?, ?, ?)",
            [
                ("mcp_autos", "http://localhost:8003/mcp", 1),
                ("mcp_cocina", "http://localhost:8004/mcp", 1),
                ("mcp_clima", "http://localhost:8005/mcp", 1),
            ],
        )
