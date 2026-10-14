"""Pruebas SQLite en archivos temporales, sin acceder a la base configurada."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

with patch("dotenv.load_dotenv", return_value=False):
    from funciones.base_sqlite import (
        conectar, conexion_sqlite, crear_tabla_errores, obtener_errores,
        crear_tabla_billing, guardar_billing,
    )


class BaseSQLiteTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.archivo = Path(temporal.name) / "prueba.sqlite3"
        env = patch.dict(os.environ, {"CADENA": str(self.archivo)})
        env.start()
        self.addCleanup(env.stop)

    def test_conecta_y_devuelve_filas_por_nombre(self):
        conexion = conectar()
        try:
            fila = conexion.execute("SELECT 42 AS valor").fetchone()
            self.assertEqual(fila["valor"], 42)
        finally:
            conexion.close()

    def test_confirma_transaccion_y_cierra(self):
        with conexion_sqlite() as conexion:
            conexion.execute("CREATE TABLE datos (valor INTEGER)")
            conexion.execute("INSERT INTO datos VALUES (?)", (7,))
        with self.assertRaises(sqlite3.ProgrammingError):
            conexion.execute("SELECT 1")
        with conexion_sqlite() as nueva:
            self.assertEqual(nueva.execute("SELECT valor FROM datos").fetchone()["valor"], 7)

    def test_revierte_si_hay_error(self):
        with conexion_sqlite() as conexion:
            conexion.execute("CREATE TABLE datos (valor INTEGER)")
        with self.assertRaises(ValueError):
            with conexion_sqlite() as conexion:
                conexion.execute("INSERT INTO datos VALUES (?)", (7,))
                raise ValueError("Error simulado")
        with conexion_sqlite() as nueva:
            self.assertEqual(nueva.execute("SELECT COUNT(*) FROM datos").fetchone()[0], 0)

    def test_exige_cadena(self):
        with patch.dict(os.environ, {"CADENA": ""}):
            with self.assertRaisesRegex(ValueError, "CADENA"):
                conectar()

    def test_errores_devuelve_formato_fastapi(self):
        crear_tabla_errores()
        self.assertEqual(obtener_errores(), {
            502: {"description": "Error de OpenAI, del MCP o de sus respuestas."},
            503: {"description": "Falta la clave de OpenAI."},
            504: {"description": "Tiempo de espera agotado."},
        })

    def test_inicializacion_no_duplica_ni_pisa_ediciones(self):
        crear_tabla_errores()
        with conexion_sqlite() as conexion:
            conexion.execute("UPDATE errores SET descripcion = ? WHERE codigo = ?", ("Descripción editada", 503))
        crear_tabla_errores()
        self.assertEqual(len(obtener_errores()), 3)
        self.assertEqual(obtener_errores()[503], {"description": "Descripción editada"})

    def test_billing_guarda_datos_en_una_fila(self):
        crear_tabla_billing()
        datos = {
            "tokens": {
                "input_tokens": 257,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens": 15,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 272,
            },
            "costo_estimado_usd": 0.0000332,
            "metodo": "tool_call",
            "herramientas": [],
        }
        identificador = guardar_billing(datos)
        with conexion_sqlite() as conexion:
            filas = conexion.execute("SELECT * FROM billing").fetchall()
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(fila["id"], identificador)
        self.assertEqual(fila["input_tokens"], 257)
        self.assertEqual(fila["output_tokens"], 15)
        self.assertEqual(fila["total_tokens"], 272)
        self.assertEqual(fila["cached_tokens"], 0)
        self.assertEqual(fila["cache_write_tokens"], 0)
        self.assertEqual(fila["reasoning_tokens"], 0)
        self.assertAlmostEqual(fila["costo_estimado_usd"], 0.0000332)
        self.assertEqual(fila["metodo"], "tool_call")
        self.assertEqual(fila["herramientas"], "")

    def test_billing_herramientas_y_consumo_no_disponible(self):
        crear_tabla_billing()
        guardar_billing({"metodo": "mcp", "herramientas": ["es_mejor_auto", "otra_tool"]})
        with conexion_sqlite() as conexion:
            fila = conexion.execute("SELECT * FROM billing").fetchone()
        self.assertEqual(fila["herramientas"], "es_mejor_auto, otra_tool")
        self.assertIsNone(fila["total_tokens"])
        self.assertIsNone(fila["costo_estimado_usd"])
