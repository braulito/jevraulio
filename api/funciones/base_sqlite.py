"""Conexiones SQLite al archivo configurado en CADENA en api/.env."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv


DIRECTORIO_API = Path(__file__).resolve().parent.parent
load_dotenv(DIRECTORIO_API / ".env")


def conectar() -> sqlite3.Connection:
    """Abre una conexión. El llamador debe cerrarla si no usa conexion_sqlite()."""
    cadena = os.getenv("CADENA", "").strip()
    if not cadena:
        raise ValueError("Falta configurar CADENA en api/.env con la ruta del archivo SQLite.")

    archivo = Path(cadena).expanduser()
    if not archivo.is_absolute():
        archivo = DIRECTORIO_API / archivo

    conexion = sqlite3.connect(str(archivo), timeout=30)
    conexion.row_factory = sqlite3.Row
    return conexion


@contextmanager
def conexion_sqlite() -> Iterator[sqlite3.Connection]:
    """Abre, confirma o revierte la transacción y cierra siempre la conexión."""
    conexion = conectar()
    try:
        yield conexion
        conexion.commit()
    except BaseException:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def obtener_errores() -> dict[int, dict[str, str]]:
    """Devuelve los errores en el formato que usa responses de FastAPI."""
    with conexion_sqlite() as conexion:
        filas = conexion.execute("SELECT codigo, descripcion FROM errores ORDER BY codigo").fetchall()
    return {fila["codigo"]: {"description": fila["descripcion"]} for fila in filas}


def obtener_mcp(nombre: str) -> dict | None:
    """Busca un MCP habilitado por nombre en el catálogo compartido."""
    with conexion_sqlite() as conexion:
        filas = conexion.execute(
            "SELECT nombre, url FROM mcps WHERE nombre = ? AND habilitado = 1",
            (nombre,),
        ).fetchall()
    if len(filas) > 1:
        raise ValueError("El catálogo contiene nombres de MCP duplicados.")
    return dict(filas[0]) if filas else None


def guardar_billing(datos: dict) -> int:
    """Descompone el consumo en columnas y devuelve el ID de la fila guardada."""
    tokens = datos.get("tokens") or {}
    entrada = tokens.get("input_tokens_details") or {}
    salida = tokens.get("output_tokens_details") or {}
    herramientas = "" if datos.get("metodo") == "tool_call" else ", ".join(datos.get("herramientas") or [])
    with conexion_sqlite() as conexion:
        cursor = conexion.execute("""
            INSERT INTO billing (
                input_tokens, cached_tokens, cache_write_tokens, output_tokens,
                reasoning_tokens, total_tokens, costo_estimado_usd, metodo, herramientas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tokens.get("input_tokens"), entrada.get("cached_tokens"),
            entrada.get("cache_write_tokens"), tokens.get("output_tokens"),
            salida.get("reasoning_tokens"), tokens.get("total_tokens"),
            datos.get("costo_estimado_usd"), datos.get("metodo"), herramientas,
        ))
        return cursor.lastrowid

# FUNCIONES DE UN SOLO USO


def crear_tabla_errores() -> None:
    """Crea la tabla y carga los códigos iniciales que todavía no existan."""
    with conexion_sqlite() as conexion:
        conexion.execute(
            "CREATE TABLE IF NOT EXISTS errores ("
            "codigo INTEGER PRIMARY KEY, descripcion TEXT NOT NULL)"
        )
        conexion.executemany(
            "INSERT INTO errores (codigo, descripcion) VALUES (?, ?) "
            "ON CONFLICT(codigo) DO NOTHING",
            [
                (502, "Error de OpenAI, del MCP o de sus respuestas."),
                (503, "Falta la clave de OpenAI."),
                (504, "Tiempo de espera agotado."),
            ],
        )


def crear_tabla_billing() -> None:
    """Crea el registro de consumo: una fila por llamada, sin columnas JSON."""
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



