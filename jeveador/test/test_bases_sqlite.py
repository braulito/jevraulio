"""Pruebas de inserción sobre una base temporal, sin configuración real."""

import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

with patch.dict("os.environ", {"UMBRAL_DEFECTO": "0.61"}, clear=True):
    from funciones.bases_sqlite import conexion_sqlite, crear_tabla_billing, crear_tabla_config_umbral, crear_tabla_mcps, guardar_billing, obtener_mcps, obtener_umbral
    from funciones.billing import registrar_uso_jev


class TestBasesSqlite(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.archivo = Path(temporal.name) / "billing-prueba.sqlite3"
        entorno = patch.dict("os.environ", {"CADENA": str(self.archivo), "UMBRAL_DEFECTO": "0.61"}, clear=True)
        entorno.start()
        self.addCleanup(entorno.stop)
        crear_tabla_billing()

    def fila(self, identificador):
        with conexion_sqlite() as conexion:
            return dict(conexion.execute("SELECT * FROM billing WHERE id = ?", (identificador,)).fetchone())

    def test_config_umbral_inicial_y_conserva_valor_existente(self):
        crear_tabla_config_umbral()
        with conexion_sqlite() as conexion:
            filas = [dict(fila) for fila in conexion.execute("SELECT * FROM config_umbral")]
            self.assertEqual(filas, [{"id": 1, "valor": 0.85}])
            conexion.execute("UPDATE config_umbral SET valor = 0.9 WHERE id = 1")
        crear_tabla_config_umbral()
        with conexion_sqlite() as conexion:
            self.assertEqual([dict(fila) for fila in conexion.execute("SELECT * FROM config_umbral")],
                             [{"id": 1, "valor": 0.9}])
        with self.assertRaises(sqlite3.IntegrityError):
            with conexion_sqlite() as conexion:
                conexion.execute("INSERT INTO config_umbral (id, valor) VALUES (2, 0.7)")

    def test_obtener_umbral_lee_valor_actual_y_detecta_registro_ausente(self):
        crear_tabla_config_umbral()
        self.assertEqual(obtener_umbral(), 0.85)
        with conexion_sqlite() as conexion:
            conexion.execute("UPDATE config_umbral SET valor = 0.9 WHERE id = 1")
        self.assertEqual(obtener_umbral(), 0.9)
        with conexion_sqlite() as conexion:
            conexion.execute("DELETE FROM config_umbral")
        with self.assertLogs(level="WARNING"):
            self.assertEqual(obtener_umbral(), 0.61)

    def test_umbral_tabla_ausente_registra_error_y_usa_entorno(self):
        with self.assertLogs(level="ERROR") as logs:
            self.assertEqual(obtener_umbral(), 0.61)
        self.assertIn("no such table: config_umbral", logs.output[0])
        self.assertNotIn("0.61", logs.output[0])

    def test_umbral_respaldo_usa_variable_cargada_al_importar(self):
        with patch.dict("os.environ", {"UMBRAL_DEFECTO": "0.72"}), self.assertLogs(level="ERROR"):
            self.assertEqual(obtener_umbral(), 0.61)

    def test_crea_mcps_con_datos_iniciales(self):
        crear_tabla_mcps()
        with conexion_sqlite() as conexion:
            filas = [dict(fila) for fila in conexion.execute("SELECT * FROM mcps ORDER BY id")]
        self.assertEqual(filas, [
            {"id": 1, "nombre": "mcp_autos", "url": "http://localhost:8003/mcp", "habilitado": 1},
            {"id": 2, "nombre": "mcp_cocina", "url": "http://localhost:8004/mcp", "habilitado": 1},
            {"id": 3, "nombre": "mcp_clima", "url": "http://localhost:8005/mcp", "habilitado": 1},
        ])

    def test_mcps_existente_conserva_cambios_y_no_repone_datos(self):
        crear_tabla_mcps()
        with conexion_sqlite() as conexion:
            conexion.execute("DELETE FROM mcps WHERE nombre = 'mcp_cocina'")
            conexion.execute("UPDATE mcps SET habilitado = 0, url = 'http://prueba.invalid/mcp'")
        crear_tabla_mcps()
        with conexion_sqlite() as conexion:
            filas = [dict(fila) for fila in conexion.execute("SELECT * FROM mcps")]
        self.assertEqual(filas, [
            {"id": 1, "nombre": "mcp_autos", "url": "http://prueba.invalid/mcp", "habilitado": 0},
            {"id": 3, "nombre": "mcp_clima", "url": "http://prueba.invalid/mcp", "habilitado": 0},
        ])
        with conexion_sqlite() as conexion:
            conexion.execute("DELETE FROM mcps")
        crear_tabla_mcps()
        with conexion_sqlite() as conexion:
            self.assertEqual(conexion.execute("SELECT COUNT(*) FROM mcps").fetchone()[0], 0)

    def test_obtener_mcps_devuelve_todos_los_campos_y_registros(self):
        crear_tabla_mcps()
        with conexion_sqlite() as conexion:
            conexion.execute("UPDATE mcps SET habilitado = 0 WHERE id = 2")
        self.assertEqual(obtener_mcps(), [
            {"id": 1, "nombre": "mcp_autos", "url": "http://localhost:8003/mcp", "habilitado": 1},
            {"id": 2, "nombre": "mcp_cocina", "url": "http://localhost:8004/mcp", "habilitado": 0},
            {"id": 3, "nombre": "mcp_clima", "url": "http://localhost:8005/mcp", "habilitado": 1},
        ])
        with conexion_sqlite() as conexion:
            conexion.execute("DELETE FROM mcps")
        self.assertEqual(obtener_mcps(), [])

    def test_columnas_aplanadas_total_calculado_y_etiquetas_jev(self):
        identificador = guardar_billing(
            input_tokens=100, cached_tokens=40, cache_write_tokens=5,
            output_tokens=20, reasoning_tokens=15, costo_estimado_usd=0.000012,
        )
        fila = self.fila(identificador)
        self.assertEqual(fila["input_tokens"], 100)
        self.assertEqual(fila["cached_tokens"], 40)
        self.assertEqual(fila["cache_write_tokens"], 5)
        self.assertEqual(fila["output_tokens"], 20)
        self.assertEqual(fila["reasoning_tokens"], 15)
        self.assertEqual(fila["total_tokens"], 120)
        self.assertEqual(fila["costo_estimado_usd"], 0.000012)
        self.assertEqual(fila["metodo"], "JEV")
        self.assertEqual(fila["herramientas"], "JEV")
        self.assertTrue(fila["fecha_utc"])

    def test_valores_ausentes_cero_y_total_informado_respetado(self):
        fila = self.fila(guardar_billing())
        for columna in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "costo_estimado_usd"):
            self.assertEqual(fila[columna], 0)
        fila = self.fila(guardar_billing(input_tokens=10, output_tokens=5, total_tokens=16))
        self.assertEqual(fila["total_tokens"], 16)

    def test_consumo_jev_llega_a_la_tabla(self):
        registrar_uso_jev({"usage": {
            "input_tokens": 80, "output_tokens": 12, "cost": 0.000004,
            "input_tokens_details": {"cached_tokens": 25, "cache_write_tokens": None},
            "output_tokens_details": {"reasoning_tokens": None},
        }}, "typesafe/jev-1.13")
        fila = self.fila(1)
        self.assertEqual(fila["total_tokens"], 92)
        self.assertEqual(fila["cached_tokens"], 25)
        self.assertEqual(fila["cache_write_tokens"], 0)
        self.assertEqual(fila["reasoning_tokens"], 0)
        self.assertEqual(fila["costo_estimado_usd"], 0.000004)
        self.assertEqual(fila["metodo"], "JEV")
        self.assertEqual(fila["herramientas"], "JEV")

    def test_transaccion_fallida_se_revierte(self):
        with self.assertRaises(RuntimeError):
            with conexion_sqlite() as conexion:
                conexion.execute("INSERT INTO billing (metodo, herramientas) VALUES ('JEV', 'JEV')")
                raise RuntimeError("fallo de prueba")
        with conexion_sqlite() as conexion:
            self.assertEqual(conexion.execute("SELECT COUNT(*) FROM billing").fetchone()[0], 0)

    def test_errores_locales_identificables_sin_exponer_ruta(self):
        with conexion_sqlite() as conexion:
            conexion.execute("DROP TABLE billing")
        with self.assertRaises(HTTPException) as error:
            guardar_billing()
        self.assertEqual(error.exception.status_code, 500)
        self.assertNotIn(str(self.archivo), error.exception.detail)
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(HTTPException) as error:
                guardar_billing()
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("CADENA", error.exception.detail)


if __name__ == "__main__":
    unittest.main()
