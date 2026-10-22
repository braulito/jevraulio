"""Política local y resultados ficticios; sin configuración privada ni conexiones reales."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx

from fastapi import HTTPException
from funciones import seguridad_mcp as seguridad
from funciones import mcp_funciones


class PoliticaMcpTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.archivo = Path(temporal.name) / "politica.json"
        self.politica = {"mcps": {"prueba": {"url": "http://127.0.0.1:8123/mcp", "herramientas": ["leer"]}}}
        self.archivo.write_text(json.dumps(self.politica), encoding="utf-8")
        parche = patch.object(seguridad, "RUTA_POLITICA", self.archivo)
        parche.start()
        self.addCleanup(parche.stop)

    def test_permiso_explicito_y_alias_localhost(self):
        """Una herramienta autorizada se conecta al literal loopback, sin resolver localhost."""
        self.assertEqual(seguridad.autorizar_herramienta("leer", "http://localhost:8123/mcp", "prueba"), (True, "http://127.0.0.1:8123/mcp"))

    def test_herramienta_nueva_se_deniega_aunque_el_mcp_la_publique(self):
        """La publicación o recomendación no concede permiso a una operación nueva."""
        with self.assertLogs(level="ERROR"):
            self.assertEqual(seguridad.autorizar_herramienta("borrar", "http://127.0.0.1:8123/mcp", "prueba"), (False, {"status_code": 403}))

    def test_nombre_mcp_no_puede_suplantar_otro_destino(self):
        """La autorización vincula nombre del MCP, herramienta y endpoint."""
        with self.assertLogs(level="ERROR"):
            self.assertEqual(seguridad.autorizar_herramienta("leer", "http://127.0.0.1:8123/mcp", "otro"), (False, {"status_code": 403}))

    def test_destinos_internos_remotos_y_codificaciones_no_se_autorizan(self):
        """Se rechazan rutas, puertos, credenciales y hosts fuera de la política."""
        urls = ["http://169.254.169.254/latest/meta-data", "http://10.0.0.1:8123/mcp", "https://ejemplo.invalid/mcp",
                "http://localhost.ejemplo.invalid:8123/mcp", "http://2130706433:8123/mcp", "http://127.0.0.1:8124/mcp",
                "http://usuario:secreto-ficticio@127.0.0.1:8123/mcp", "http://127.0.0.1:8123/mcp?url=externa",
                "http://127.0.0.1:8123/%6dcp", "file:///archivo"]
        for url in urls:
            with self.subTest(url=url), self.assertLogs(level="ERROR") as logs:
                self.assertEqual(seguridad.validar_destino(url), (False, {"status_code": 403}))
            self.assertNotIn("secreto-ficticio", "\n".join(logs.output))

    def test_politica_se_relee_y_revocacion_tiene_efecto(self):
        """Un permiso retirado no persiste en caché para la siguiente ejecución."""
        self.assertTrue(seguridad.autorizar_herramienta("leer", "http://127.0.0.1:8123/mcp")[0])
        self.politica["mcps"]["prueba"]["herramientas"] = []
        self.archivo.write_text(json.dumps(self.politica), encoding="utf-8")
        with self.assertLogs(level="ERROR"):
            self.assertFalse(seguridad.autorizar_herramienta("leer", "http://127.0.0.1:8123/mcp")[0])

    def test_politica_ausente_no_autoriza_por_defecto(self):
        """Sin archivo de política no se ejecuta y se conserva HTTP 503."""
        with patch.object(seguridad, "RUTA_POLITICA", self.archivo.parent / "inexistente.json"), self.assertLogs(level="ERROR"):
            self.assertEqual(seguridad.autorizar_herramienta("leer", "http://127.0.0.1:8123/mcp"), (False, {"status_code": 503}))


class ResultadoMcpTests(unittest.TestCase):
    def test_referencias_externas_del_catalogo_no_se_resuelven(self):
        """El segundo descubrimiento de la API no puede usar JSON Schema para consultar URLs externas."""
        definicion = {"name": "leer", "description": "Consulta datos", "parameters": {"type": "object", "properties": {"dato": {"$ref": "http://169.254.169.254/esquema"}}}}
        with patch("urllib.request.urlopen") as red, self.assertLogs(level="ERROR"):
            self.assertEqual(seguridad.validar_definiciones_mcp([definicion]), (False, {"status_code": 502}))
        red.assert_not_called()

    def test_resultado_valido_conserva_datos_y_descarta_metadatos(self):
        """Solo texto y datos estructurados llegan al redactor; no metadatos arbitrarios."""
        datos = {"isError": False, "content": [{"type": "text", "text": "Dato real", "annotations": {"instruccion": "ignorar"}}],
                 "structuredContent": {"valor": 23}, "_meta": {"instruccion": "ejecutar otra tool"}}
        ok, salida = seguridad.validar_resultado_mcp(datos)
        self.assertTrue(ok)
        self.assertEqual(salida, {"isError": False, "content": [{"type": "text", "text": "Dato real"}], "structuredContent": {"valor": 23}})

    def test_resultados_grandes_profundos_vacios_o_malformados(self):
        """Resultados fuera de límites se rechazan con 502 antes de llamar a OpenAI."""
        profundo = {}
        actual = profundo
        for _ in range(20):
            actual["dato"] = {}
            actual = actual["dato"]
        casos = [None, {}, {"content": "texto"}, {"isError": "false", "content": []},
                 {"structuredContent": []}, {"structuredContent": {"numero": float("nan")}},
                 {"content": [{"type": "text", "text": "x" * (seguridad.MAX_TEXTO_BYTES + 1)}]},
                 {"structuredContent": {"dato": "x" * seguridad.MAX_RESULTADO_BYTES}},
                 {"structuredContent": profundo}, {"content": [{"type": "text", "text": "x"}] * (seguridad.MAX_BLOQUES + 1)}]
        for caso in casos:
            with self.subTest(tipo=type(caso).__name__), self.assertLogs(level="ERROR"):
                self.assertEqual(seguridad.validar_resultado_mcp(caso), (False, {"status_code": 502}))

    def test_recursos_externos_no_se_procesan(self):
        """No se aceptan bloques que requieran cargar imágenes, audio o recursos remotos."""
        for tipo in ["image", "audio", "resource", "resource_link"]:
            with self.subTest(tipo=tipo), self.assertLogs(level="ERROR"):
                self.assertFalse(seguridad.validar_resultado_mcp({"content": [{"type": tipo, "uri": "http://ejemplo.invalid"}]})[0])


class BloqueoAntesDeConexionTests(unittest.IsolatedAsyncioTestCase):
    async def test_redireccion_http_no_se_sigue(self):
        """Un MCP permitido no puede redirigir initialize hacia otro host."""
        peticiones = []
        constructor_real = httpx.AsyncClient

        def responder(request):
            peticiones.append(request)
            return httpx.Response(307, headers={"Location": "http://169.254.169.254/metadata"})

        def crear_cliente(*args, **kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            return constructor_real(*args, **kwargs, transport=httpx.MockTransport(responder))

        with patch.object(mcp_funciones, "validar_destino", return_value=(True, "http://127.0.0.1:8123/mcp")), \
                patch.object(mcp_funciones.httpx, "AsyncClient", side_effect=crear_cliente), self.assertLogs(level="ERROR"):
            with self.assertRaises(HTTPException) as error:
                await mcp_funciones.obtener_herramientas_mcp("http://127.0.0.1:8123/mcp")
        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(len(peticiones), 1)
        self.assertEqual(peticiones[0].url.host, "127.0.0.1")
    async def test_permiso_denegado_no_abre_cliente_ni_sesion(self):
        """El cliente MCP no llega a conectarse cuando falta autorización de ejecución."""
        with patch.object(mcp_funciones, "autorizar_herramienta", return_value=(False, {"status_code": 403})), \
                patch.object(mcp_funciones.httpx, "AsyncClient") as cliente:
            with self.assertRaises(HTTPException) as error:
                await mcp_funciones.llamar_herramienta_mcp("borrar", {}, "http://127.0.0.1:8123/mcp")
        self.assertEqual(error.exception.status_code, 403)
        cliente.assert_not_called()

    async def test_destino_denegado_no_abre_cliente_de_descubrimiento(self):
        """Una URL no permitida no recibe initialize ni tools/list."""
        with patch.object(mcp_funciones, "validar_destino", return_value=(False, {"status_code": 403})), \
                patch.object(mcp_funciones.httpx, "AsyncClient") as cliente:
            with self.assertRaises(HTTPException) as error:
                await mcp_funciones.obtener_herramientas_mcp("http://ejemplo.invalid/mcp")
        self.assertEqual(error.exception.status_code, 403)
        cliente.assert_not_called()
