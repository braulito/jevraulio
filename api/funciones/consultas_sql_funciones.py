"""Operaciones administrativas sobre las tablas SQLite existentes."""

import logging
import os
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit


DIRECTORIO_API = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def error_sql(error: Exception, operacion: str) -> tuple[bool, dict]:
    """Registra el error sin datos privados y conserva su código HTTP."""
    try:
        if isinstance(error, sqlite3.IntegrityError):
            codigo = 409
        elif isinstance(error, RuntimeError):
            codigo = 404
        elif isinstance(error, ValueError):
            codigo = 400
        elif isinstance(error, (sqlite3.Error, OSError)):
            codigo = 503
        else:
            codigo = 500
        logger.error("Falló %s. Tipo: %s; HTTP: %s", operacion, type(error).__name__, codigo)
        return False, {"status_code": codigo}
    except Exception:
        return False, {"status_code": 500}


def conectar(*, solo_lectura: bool = True) -> tuple[bool, sqlite3.Connection | dict]:
    try:
        cadena = os.getenv("CADENA", "").strip()
        if not cadena:
            raise sqlite3.OperationalError("Falta configurar CADENA.")
        archivo = Path(cadena).expanduser()
        if not archivo.is_absolute():
            archivo = DIRECTORIO_API / archivo
        modo = "ro" if solo_lectura else "rw"
        conexion = sqlite3.connect(archivo.resolve().as_uri() + f"?mode={modo}", uri=True, timeout=30)
        conexion.row_factory = sqlite3.Row
        return True, conexion

    except Exception as error:
        return error_sql(error, "conectar")


def obtener_mcps() -> tuple[bool, list[dict] | dict]:
    try:
        resultado, salida = conectar()
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            filas = conexion.execute("SELECT id, nombre, url, habilitado FROM mcps ORDER BY id").fetchall()
        return True, [dict(fila) for fila in filas]

    except Exception as error:
        return error_sql(error, "obtener_mcps")


def obtener_mcp(id_mcp: int) -> tuple[bool, dict]:
    try:
        resultado, salida = conectar()
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            fila = conexion.execute(
                "SELECT id, nombre, url, habilitado FROM mcps WHERE id = ?", (id_mcp,)
            ).fetchone()
        if fila is None:
            raise RuntimeError("No existe el MCP indicado.")
        return True, dict(fila)

    except Exception as error:
        return error_sql(error, "obtener_mcp")


def agregar_mcp(nombre: str, url: str) -> tuple[bool, dict]:
    try:
        nombre, url = nombre.strip(), url.strip()
        if not nombre:
            raise ValueError("Ingresá el nombre del MCP.")
        try:
            partes = urlsplit(url)
            if (partes.scheme not in {"http", "https"} or not partes.hostname
                    or any(caracter.isspace() or ord(caracter) < 32 for caracter in url)
                    or partes.username is not None or partes.password is not None):
                raise ValueError
            partes.port
        except ValueError:
            raise ValueError("Ingresá una URL HTTP o HTTPS válida, sin credenciales.") from None
        resultado, salida = conectar(solo_lectura=False)
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            with conexion:
                cursor = conexion.execute(
                    "INSERT INTO mcps (nombre, url, habilitado) VALUES (?, ?, 0)", (nombre, url)
                )
                id_mcp = cursor.lastrowid
        return True, {"id": id_mcp, "nombre": nombre, "url": url, "habilitado": 0}

    except Exception as error:
        return error_sql(error, "agregar_mcp")


def guardar_estado_mcp(id_mcp: int, habilitado: int) -> tuple[bool, dict]:
    try:
        if habilitado not in (0, 1):
            raise ValueError("El estado debe ser 0 o 1.")
        resultado, salida = conectar(solo_lectura=False)
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            with conexion:
                cursor = conexion.execute("UPDATE mcps SET habilitado = ? WHERE id = ?", (habilitado, id_mcp))
                if cursor.rowcount != 1:
                    raise RuntimeError("No existe el MCP indicado.")
                fila = conexion.execute("SELECT id, nombre, url, habilitado FROM mcps WHERE id = ?", (id_mcp,)).fetchone()
        return True, dict(fila)

    except Exception as error:
        return error_sql(error, "guardar_estado_mcp")


def eliminar_mcp(id_mcp: int) -> tuple[bool, dict]:
    try:
        resultado, salida = conectar(solo_lectura=False)
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            with conexion:
                cursor = conexion.execute("DELETE FROM mcps WHERE id = ?", (id_mcp,))
                if cursor.rowcount != 1:
                    raise RuntimeError("No existe el MCP indicado.")
        return True, {"id": id_mcp, "eliminado": True}

    except Exception as error:
        return error_sql(error, "eliminar_mcp")


def obtener_umbral() -> tuple[bool, dict]:
    try:
        resultado, salida = conectar()
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            fila = conexion.execute("SELECT id, valor FROM config_umbral WHERE id = 1").fetchone()
        if fila is None:
            raise RuntimeError("No existe el registro del umbral.")
        return True, dict(fila)

    except Exception as error:
        return error_sql(error, "obtener_umbral")


def guardar_umbral(valor: Decimal) -> tuple[bool, dict]:
    try:
        if not valor.is_finite() or not Decimal("0") <= valor <= Decimal("1"):
            raise ValueError("El umbral debe estar entre 0 y 1.")
        resultado, salida = conectar(solo_lectura=False)
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            with conexion:
                cursor = conexion.execute("UPDATE config_umbral SET valor = ? WHERE id = 1", (float(valor),))
                if cursor.rowcount != 1:
                    raise RuntimeError("No existe el registro del umbral.")
        return True, {"id": 1, "valor": float(valor)}

    except Exception as error:
        return error_sql(error, "guardar_umbral")


def obtener_costos(pagina: int = 1, pagina_size: int = 50,
                   mostrar_jev: bool = True, mostrar_openai: bool = True) -> tuple[bool, dict]:
    try:
        if pagina_size < 1:
            raise ValueError("El tamaño de página debe ser positivo.")
        resultado, salida = conectar()
        if not resultado:
            return False, salida
        with closing(salida) as conexion:
            conexion.execute("BEGIN")
            resumen = conexion.execute(
                """
                SELECT COUNT(CASE WHEN (? AND metodo = 'JEV')
                           OR (? AND (metodo IS NULL OR metodo <> 'JEV')) THEN 1 END) AS total_registros,
                       COALESCE(SUM(CASE WHEN metodo = 'JEV'
                           THEN costo_estimado_usd ELSE 0 END), 0) AS costo_jev,
                       COALESCE(SUM(CASE WHEN metodo = 'JEV'
                           THEN 0 ELSE costo_estimado_usd END), 0) AS costo_openai,
                       COALESCE(SUM(CASE WHEN metodo = 'JEV'
                           THEN total_tokens ELSE 0 END), 0) AS tokens_jev,
                       COALESCE(SUM(CASE WHEN metodo = 'JEV'
                           THEN 0 ELSE total_tokens END), 0) AS tokens_openai
                FROM billing
                """, (mostrar_jev, mostrar_openai),
            ).fetchone()
            total = resumen["total_registros"]
            total_paginas = max(1, (total + pagina_size - 1) // pagina_size)
            pagina = min(max(1, pagina), total_paginas)
            offset = (pagina - 1) * pagina_size
            filas = conexion.execute(
                """
                SELECT id, fecha_utc, input_tokens, cached_tokens, cache_write_tokens,
                       output_tokens, reasoning_tokens, total_tokens,
                       costo_estimado_usd, metodo, herramientas
                FROM billing
                WHERE (? AND metodo = 'JEV') OR (? AND (metodo IS NULL OR metodo <> 'JEV'))
                ORDER BY fecha_utc DESC, id DESC LIMIT ? OFFSET ?
                """, (mostrar_jev, mostrar_openai, pagina_size, offset),
            ).fetchall()
        return True, {
            "registros": [dict(fila) for fila in filas],
            "mostrar_jev": mostrar_jev, "mostrar_openai": mostrar_openai,
            "costo_jev": resumen["costo_jev"], "costo_openai": resumen["costo_openai"],
            "tokens_jev": resumen["tokens_jev"], "tokens_openai": resumen["tokens_openai"],
            "total_registros": total, "pagina": pagina, "total_paginas": total_paginas,
            "desde": offset + 1 if total else 0, "hasta": offset + len(filas),
        }

    except Exception as error:
        return error_sql(error, "obtener_costos")
