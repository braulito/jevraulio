"""Endpoints SQL con SQLite temporal, sin importar main ni cargar .env."""

import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from funciones import consultas_sql_funciones as sql
# El paquete routers carga dotenv al importar: bloquear esa lectura en pruebas.
with patch("dotenv.load_dotenv", return_value=False):
    from routers.consultas_sql import router


class ConsultasSqlTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="jev_admin_sql_")
        self.addCleanup(temporal.cleanup)
        self.archivo = Path(temporal.name) / "ficticia.sqlite"
        with closing(sqlite3.connect(self.archivo)) as conexion:
            conexion.execute("CREATE TABLE mcps (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL UNIQUE, url TEXT NOT NULL, habilitado INTEGER NOT NULL DEFAULT 1 CHECK (habilitado IN (0, 1)))")
            conexion.execute("INSERT INTO mcps VALUES (1, 'mcp_autos', 'http://localhost:8003/mcp', 1)")
            conexion.execute("INSERT INTO mcps VALUES (2, 'mcp_cocina', 'http://localhost:8004/mcp', 0)")
            conexion.execute("CREATE TABLE config_umbral (id INTEGER PRIMARY KEY CHECK (id = 1), valor REAL NOT NULL)")
            conexion.execute("INSERT INTO config_umbral VALUES (1, 0.85)")
            conexion.execute("CREATE TABLE billing (id INTEGER PRIMARY KEY, fecha_utc TEXT, input_tokens INTEGER, cached_tokens INTEGER, cache_write_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, total_tokens INTEGER, costo_estimado_usd REAL, metodo TEXT, herramientas TEXT)")
            conexion.executemany("INSERT INTO billing VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, '')", [
                (1, "2026-10-13 12:00:00", 100, 1, "JEV"),
                (2, "2026-10-13 12:00:00", 200, 2, "JEV"),
                (3, "2026-10-13 12:00:00", 30, 0.1, "respuesta"),
                (4, "2026-10-13 12:00:00", 40, 0.2, "mcp"),
                (5, "2026-10-13 12:00:00", None, None, None),
            ])
            conexion.commit()
        entorno = patch.dict(os.environ, {"CADENA": str(self.archivo)}, clear=True)
        entorno.start()
        self.addCleanup(entorno.stop)
        app = FastAPI()
        app.include_router(router)
        self.cliente = TestClient(app)
        self.addCleanup(self.cliente.close)

    def test_swagger_publica_ocho_operaciones_con_tag(self):
        rutas = self.cliente.get("/openapi.json").json()["paths"]
        operaciones = [datos for metodos in rutas.values() for datos in metodos.values()]
        self.assertEqual(len(operaciones), 8)
        self.assertTrue(all(datos["tags"] == ["admin sql"] for datos in operaciones))

    def test_listar_y_consultar_mcp_incluye_deshabilitados(self):
        registros = self.cliente.get("/consultas_sql/mcps").json()["salida"]
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[1]["habilitado"], 0)
        self.assertEqual(self.cliente.get("/consultas_sql/mcps/2").json()["salida"], registros[1])
        self.assertEqual(self.cliente.get("/consultas_sql/mcps/99").status_code, 404)

    def test_alta_deshabilitada_estado_y_borrado(self):
        respuesta = self.cliente.post("/consultas_sql/mcps", json={"nombre": " mcp_clima ", "url": "http://localhost:8005/mcp"})
        self.assertEqual(respuesta.status_code, 201)
        nuevo = respuesta.json()["salida"]
        self.assertEqual(nuevo["nombre"], "mcp_clima")
        self.assertEqual(nuevo["habilitado"], 0)
        ruta = f'/consultas_sql/mcps/{nuevo["id"]}'
        for estado in (1, 0):
            respuesta = self.cliente.patch(ruta, json={"habilitado": estado})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.json()["salida"]["habilitado"], estado)
        self.assertEqual(self.cliente.delete(ruta).json()["salida"], {"id": nuevo["id"], "eliminado": True})
        self.assertEqual(self.cliente.delete(ruta).status_code, 404)
        self.assertEqual(len(self.cliente.get("/consultas_sql/mcps").json()["salida"]), 2)

    def test_altas_invalidas_duplicados_y_estado_invalido(self):
        ruta = "/consultas_sql/mcps"
        self.assertEqual(self.cliente.post(ruta, json={"nombre": "mcp_autos", "url": "http://localhost/mcp"}).status_code, 409)
        self.assertEqual(self.cliente.post(ruta, json={"nombre": " ", "url": "http://localhost/mcp"}).status_code, 422)
        self.assertEqual(self.cliente.post(ruta, json={"nombre": "prueba", "url": "ftp://localhost/mcp"}).status_code, 400)
        self.assertEqual(self.cliente.post(ruta, json={"nombre": "prueba", "url": "http://localhost/mcp", "habilitado": 1}).status_code, 422)
        self.assertEqual(self.cliente.patch(ruta + "/1", json={"habilitado": 2}).status_code, 422)
        self.assertEqual(self.cliente.patch(ruta + "/99", json={"habilitado": 1}).status_code, 404)

    def test_umbral_decimal_validacion_y_registro_ausente(self):
        ruta = "/consultas_sql/umbral"
        self.assertEqual(self.cliente.get(ruta).json()["salida"], {"id": 1, "valor": 0.85})
        self.assertEqual(self.cliente.put(ruta, json={"valor": 0.7}).json()["salida"], {"id": 1, "valor": 0.7})
        self.assertEqual(self.cliente.get(ruta).json()["salida"]["valor"], 0.7)
        for valor in (-0.1, 1.1, 85):
            self.assertEqual(self.cliente.put(ruta, json={"valor": valor}).status_code, 422)
        with closing(sqlite3.connect(self.archivo)) as conexion:
            conexion.execute("DELETE FROM config_umbral")
            conexion.commit()
        self.assertEqual(self.cliente.get(ruta).status_code, 404)
        self.assertEqual(self.cliente.put(ruta, json={"valor": 0.8}).status_code, 404)

    def test_costos_paginacion_filtros_y_totales_globales(self):
        for pagina, ids in ((1, [5, 4]), (2, [3, 2]), (99, [1])):
            respuesta = self.cliente.get("/consultas_sql/costos", params={"pagina": pagina, "pagina_size": 2})
            self.assertEqual(respuesta.status_code, 200)
            datos = respuesta.json()["salida"]
            self.assertEqual([fila["id"] for fila in datos["registros"]], ids)
            self.assertEqual(datos["total_paginas"], 3)
            self.assertEqual(datos["costo_jev"], 3)
            self.assertAlmostEqual(datos["costo_openai"], 0.3)
            self.assertEqual(datos["tokens_jev"], 300)
            self.assertEqual(datos["tokens_openai"], 70)
        datos = self.cliente.get("/consultas_sql/costos?mostrar_openai=false").json()["salida"]
        self.assertEqual([fila["id"] for fila in datos["registros"]], [2, 1])
        datos = self.cliente.get("/consultas_sql/costos?mostrar_jev=false&mostrar_openai=false").json()["salida"]
        self.assertEqual(datos["registros"], [])
        self.assertEqual(datos["total_registros"], 0)
        self.assertEqual(self.cliente.get("/consultas_sql/costos?pagina_size=0").status_code, 422)

    def test_lectura_no_escribe_y_base_ausente_no_se_crea(self):
        resultado, conexion = sql.conectar()
        self.assertTrue(resultado)
        with closing(conexion) as conexion:
            with self.assertRaises(sqlite3.OperationalError):
                conexion.execute("DELETE FROM mcps")
        inexistente = self.archivo.parent / "inexistente.sqlite"
        with patch.dict(os.environ, {"CADENA": str(inexistente)}), self.assertLogs("funciones.consultas_sql_funciones", level="ERROR"):
            self.assertEqual(self.cliente.get("/consultas_sql/mcps").status_code, 503)
            self.assertEqual(self.cliente.post("/consultas_sql/mcps", json={"nombre": "prueba", "url": "http://localhost/mcp"}).status_code, 503)
        self.assertFalse(inexistente.exists())

    def test_contrato_python_exito_y_errores_sin_excepciones(self):
        resultado, salida = sql.obtener_umbral()
        self.assertIs(resultado, True)
        self.assertEqual(salida, {"id": 1, "valor": 0.85})
        casos = [
            (sql.obtener_mcp, (99,), 404),
            (sql.eliminar_mcp, (99,), 404),
            (sql.guardar_estado_mcp, (99, 1), 404),
            (sql.guardar_estado_mcp, (1, 2), 400),
            (sql.agregar_mcp, ("mcp_autos", "http://localhost/mcp"), 409),
            (sql.guardar_umbral, (Decimal("2"),), 400),
            (sql.obtener_costos, (1, 0), 400),
        ]
        for operacion, argumentos, codigo in casos:
            with self.subTest(operacion=operacion.__name__), patch.object(sql.logger, "error") as registrar:
                self.assertEqual(operacion(*argumentos), (False, {"status_code": codigo}))
                registrar.assert_called_once()
        with patch.object(sql, "conectar", side_effect=Exception("detalle privado")), patch.object(sql.logger, "error"):
            self.assertEqual(sql.obtener_mcps(), (False, {"status_code": 500}))

    def test_errores_http_conservan_codigo_y_contrato(self):
        casos = [
            ("GET", "/consultas_sql/mcps/99", None, 404),
            ("POST", "/consultas_sql/mcps", {"nombre": "mcp_autos", "url": "http://localhost/mcp"}, 409),
            ("POST", "/consultas_sql/mcps", {"nombre": "prueba", "url": "ftp://localhost/mcp"}, 400),
            ("PUT", "/consultas_sql/umbral", {"valor": 85}, 422),
        ]
        for metodo, ruta, datos, codigo in casos:
            with self.subTest(codigo=codigo):
                respuesta = self.cliente.request(metodo, ruta, json=datos)
                self.assertEqual(respuesta.status_code, codigo)
                self.assertEqual(respuesta.json(), {"resultado": False, "salida": {"status_code": codigo}})
        with patch.object(sql, "obtener_umbral", side_effect=Exception("detalle privado")):
            respuesta = self.cliente.get("/consultas_sql/umbral")
        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(respuesta.json(), {"resultado": False, "salida": {"status_code": 500}})


if __name__ == "__main__":
    unittest.main()
