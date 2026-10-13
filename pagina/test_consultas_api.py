"""Cliente SQL con HTTP simulado; no carga .env ni ejecuta operaciones reales."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import funciones


class ConsultasApiTests(unittest.TestCase):
    def setUp(self):
        configuracion = patch.multiple(funciones,
            API_COSTOS_URL="http://api-ficticia.invalid/consultas_sql/costos",
            API_MCPS_URL="http://api-ficticia.invalid/consultas_sql/mcps",
            API_MCP_URL="http://api-ficticia.invalid/consultas_sql/mcps/{id_mcp}",
            API_UMBRAL_URL="http://api-ficticia.invalid/consultas_sql/umbral",
        )
        configuracion.start()
        self.addCleanup(configuracion.stop)

    def test_metodos_cuerpos_y_rutas_de_todas_las_operaciones(self):
        casos = [
            (funciones.consultar_mcps_api, (), "GET", "/mcps", None),
            (funciones.consultar_mcp_api, (7,), "GET", "/mcps/7", None),
            (funciones.agregar_mcp_api, ("mcp_clima", "http://localhost:8005/mcp"), "POST", "/mcps", {"nombre": "mcp_clima", "url": "http://localhost:8005/mcp"}),
            (funciones.guardar_estado_mcp_api, (7, 1), "PATCH", "/mcps/7", {"habilitado": 1}),
            (funciones.eliminar_mcp_api, (7,), "DELETE", "/mcps/7", None),
            (funciones.consultar_umbral_api, (), "GET", "/umbral", None),
            (funciones.guardar_umbral_api, (0.85,), "PUT", "/umbral", {"valor": 0.85}),
        ]
        for funcion, argumentos, metodo, ruta, datos in casos:
            with self.subTest(operacion=funcion.__name__):
                salida = [{"id": 7}] if funcion == funciones.consultar_mcps_api else {"id": 7}
                with patch("funciones.urlopen", return_value=io.BytesIO(json.dumps({"resultado": True, "salida": salida}).encode())) as enviar:
                    self.assertEqual(funcion(*argumentos), (True, salida))
                peticion = enviar.call_args.args[0]
                self.assertEqual(peticion.get_method(), metodo)
                self.assertEqual(urlsplit(peticion.full_url).path, "/consultas_sql" + ruta)
                self.assertEqual(json.loads(peticion.data) if peticion.data is not None else None, datos)
                self.assertEqual(enviar.call_args.kwargs["timeout"], 30)
                self.assertIsNone(peticion.get_header("Authorization"))
                if datos is not None:
                    self.assertEqual(peticion.get_header("Content-type"), "application/json")

    def test_costos_envia_paginacion_y_filtros(self):
        with patch("funciones.urlopen", return_value=io.BytesIO(b'{"resultado": true, "salida": {"registros": []}}')) as enviar:
            self.assertEqual(funciones.consultar_costos_api(2, 10, False, True), (True, {"registros": []}))
        peticion = enviar.call_args.args[0]
        self.assertEqual(peticion.get_method(), "GET")
        self.assertIsNone(peticion.data)
        self.assertEqual(parse_qs(urlsplit(peticion.full_url).query), {
            "pagina": ["2"], "pagina_size": ["10"], "mostrar_jev": ["false"], "mostrar_openai": ["true"],
        })

    def test_parametros_conservan_query_existente(self):
        with patch("funciones.urlopen", return_value=io.BytesIO(b'{"resultado": true, "salida": {}}')) as enviar:
            funciones.llamar_api_json("http://api-ficticia.invalid/costos?origen=prueba&pagina=1", parametros={"pagina": 2})
        self.assertEqual(parse_qs(urlsplit(enviar.call_args.args[0].full_url).query), {"origen": ["prueba"], "pagina": ["2"]})

    def test_error_http_registra_codigo_sin_url_o_cuerpo(self):
        for codigo in (404, 409, 422, 503):
            with patch("funciones.urlopen", side_effect=HTTPError("http://privado.invalid", codigo, "detalle-privado", {}, None)), patch.object(funciones.logger, "error") as registrar:
                self.assertEqual(funciones.consultar_mcps_api(), (False, {"status_code": codigo}))
            self.assertEqual(registrar.call_args.args[-1], codigo)
            self.assertNotIn("privado.invalid", str(registrar.call_args))
            self.assertNotIn("detalle-privado", str(registrar.call_args))

    def test_json_invalido_y_excepcion_generica(self):
        for cuerpo in (b"no es json", b"null", b"123", b"{}", b'{"resultado": 1, "salida": {}}', b'{"resultado": true, "salida": null}'):
            with patch("funciones.urlopen", return_value=io.BytesIO(cuerpo)), patch.object(funciones.logger, "error"):
                self.assertEqual(funciones.consultar_umbral_api(), (False, {"status_code": 502}))
        with patch("funciones.urlopen", side_effect=RuntimeError()), patch.object(funciones.logger, "error"):
            self.assertEqual(funciones.consultar_mcps_api(), (False, {"status_code": 502}))

    def test_resultado_falso_no_se_confunde_con_exito_http(self):
        cuerpo = b'{"resultado": false, "salida": {"status_code": 409}}'
        with patch("funciones.urlopen", return_value=io.BytesIO(cuerpo)), patch.object(funciones.logger, "error") as registrar:
            self.assertEqual(funciones.consultar_mcps_api(), (False, {"status_code": 409}))
        registrar.assert_called_once()

    def test_configuracion_id_y_json_invalidos_no_hacen_llamada(self):
        with patch("funciones.urlopen") as enviar, patch.object(funciones.logger, "error"):
            for id_mcp in (0, -1, "7", True):
                self.assertEqual(funciones.eliminar_mcp_api(id_mcp), (False, {"status_code": 502}))
            self.assertEqual(funciones.llamar_api_json(""), (False, {"status_code": 502}))
            self.assertEqual(funciones.llamar_api_json("ftp://api-ficticia.invalid"), (False, {"status_code": 502}))
            self.assertEqual(funciones.guardar_umbral_api(float("nan")), (False, {"status_code": 502}))
        enviar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
