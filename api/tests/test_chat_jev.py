"""Pruebas aisladas: sin cargar .env, SQLite real ni servicios externos."""

import ast
import json
import logging
import os
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import anyio
import httpx
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from jsonschema import ValidationError as ErrorEsquema
from jsonschema.validators import validator_for
from pydantic import ValidationError

from schemas.chat import LlamadaHerramienta, RespuestaChat
from schemas.chat_jev import ConsultaChatJev, RecomendacionJev, RespuestaChatJev


def cargar_funciones():
    # Se ejecutan únicamente las funciones; se sustituyen las dependencias que
    # importarían base_sqlite y cargarían el archivo .env.
    archivo = Path(__file__).resolve().parents[1] / "funciones/chat_jev_funciones.py"
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    arbol.body = [n for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    contexto = dict(globals())
    contexto.update(
        obtener_mcp=Mock(return_value={"nombre": "autos", "url": "http://mcp.test/mcp"}),
        obtener_herramientas_mcp=AsyncMock(), llamar_herramienta_mcp=AsyncMock(),
        llm=SimpleNamespace(consultar_llm=AsyncMock(), extraer_texto=Mock(return_value="¿Qué auto?")),
    )
    exec(compile(arbol, str(archivo), "exec"), contexto)
    contexto["redactar_respuesta"] = AsyncMock(return_value="Sí")
    contexto["redactar_capacidades"] = AsyncMock(return_value="Puedo responder consultas sobre autos.")
    contexto["redactar_aclaracion"] = AsyncMock(return_value="¿Te referís a un auto o a un plato?")
    contexto["preguntar_seleccion_real"] = contexto["preguntar_seleccion"]
    contexto["preguntar_seleccion"] = AsyncMock(return_value="¿Te referís a un auto o a un plato?")
    return contexto


def evaluacion(nombre="autos", estado="sirve", herramientas=None, aclaracion=False):
    return dict(mcp_evaluado=nombre, estado=estado, motivo="Precisá el auto.",
                herramientas_aplicables=(["consultar"] if herramientas is None else herramientas),
                requiere_aclaracion=aclaracion)


class ChatJevTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.c = cargar_funciones()
        self.tool = {"name": "consultar", "description": "Consultar un auto", "parameters": {"type": "object", "properties": {"auto": {"type": "string"}}, "required": ["auto"], "additionalProperties": False}}
        self.c["obtener_herramientas_mcp"].return_value = [self.tool]
        self.c["llamar_herramienta_mcp"].return_value = {"isError": False, "structuredContent": {"respuesta": "Sí"}}
        self.c["llm"].consultar_llm.return_value = SimpleNamespace(output=[{
            "type": "function_call", "name": "consultar", "call_id": "1", "arguments": '{"auto":"Fiat"}',
        }])
        self.env = patch.dict(os.environ, {"API_KEY": "clave-ficticia", "JEV_URL": "http://jev.test"})
        self.env.start()
        self.addCleanup(self.env.stop)

    async def flujo(self, evaluaciones, recomendado="autos", mcp=None):
        self.c["consultar_jeveador"] = AsyncMock(return_value=RecomendacionJev(
            mcp_recomendado=recomendado, evaluaciones=evaluaciones))
        return await self.c["responder_chat_jev"](ConsultaChatJev(mensaje="¿Fiat es el mejor auto?", mcp=mcp))

    def sin_ejecucion(self):
        self.c["llamar_herramienta_mcp"].assert_not_awaited()
        self.c["llm"].consultar_llm.assert_not_awaited()
        self.c["redactar_respuesta"].assert_not_awaited()

    async def test_sin_coincidencias(self):
        r = await self.flujo([evaluacion(estado="no_sirve", herramientas=[])], None)
        self.assertEqual(r.estado, "sin_coincidencias")
        self.assertEqual(r.respuesta, "No tengo las herramientas necesarias para responder tu pregunta.")
        self.sin_ejecucion()

    async def test_capacidades_usa_catalogos_de_jev_sin_ejecutar_tools(self):
        capacidades = [{"nombre": "mcp_autos", "herramientas": [{
            "name": "mejor_auto", "description": "Consulta cuál es el mejor auto",
            "inputSchema": {"type": "object", "properties": {}},
        }]}]
        self.c["consultar_jeveador"] = AsyncMock(return_value=RecomendacionJev(
            intencion="consultar_capacidades", mcp_recomendado=None, evaluaciones=[], capacidades=capacidades,
        ))
        consulta = ConsultaChatJev(mensaje="¿Qué datos me podés ofrecer?", contexto=["Usuario: hola"])
        resultado = await self.c["responder_chat_jev"](consulta)
        self.assertEqual(resultado.estado, "Ok")
        self.assertEqual(resultado.herramientas, [])
        self.assertIsNone(resultado.resultado)
        self.assertEqual(resultado.respuesta, self.c["redactar_capacidades"].return_value)
        self.c["redactar_capacidades"].assert_awaited_once_with(consulta.mensaje, consulta.contexto, capacidades)
        self.c["obtener_mcp"].assert_not_called()
        self.c["obtener_herramientas_mcp"].assert_not_awaited()
        self.c["preguntar_seleccion"].assert_not_awaited()
        self.sin_ejecucion()

    async def test_cliente_jev_conserva_nuevo_contrato_de_capacidades(self):
        datos = {
            "intencion": "consultar_capacidades", "mcp_recomendado": None, "evaluaciones": [],
            "capacidades": [{"nombre": "mcp_nuevo", "herramientas": [{
                "name": "consulta_nueva", "description": "Ofrece datos nuevos", "inputSchema": {"type": "object"},
            }]}],
        }
        with patch("httpx.AsyncClient") as constructor:
            post = constructor.return_value.__aenter__.return_value.post
            post.return_value = httpx.Response(200, json=datos, request=httpx.Request("POST", "http://jev.test/evaluar"))
            recomendacion = await self.c["consultar_jeveador"]("¿Qué podés hacer?")
        self.assertEqual(recomendacion.intencion, "consultar_capacidades")
        self.assertEqual([c.model_dump() for c in recomendacion.capacidades], datos["capacidades"])

    async def test_varias_coincidencias_sigue_recomendacion(self):
        r = await self.flujo([evaluacion(), evaluacion("cocina")])
        self.assertEqual(r.estado, "Ok")
        self.c["obtener_mcp"].assert_called_once_with("autos")
        self.c["preguntar_seleccion"].assert_not_awaited()

    async def test_sin_coincidencias_aunque_usuario_elija_mcp(self):
        r = await self.flujo([evaluacion(estado="no_sirve", herramientas=[])], None, mcp="autos")
        self.assertEqual(r.estado, "sin_coincidencias")
        self.sin_ejecucion()

    async def test_aclaracion_no_ejecuta(self):
        r = await self.flujo([evaluacion(estado="falta_informacion", aclaracion=True)], None)
        self.assertEqual(r.estado, "requiere_aclaracion")
        self.sin_ejecucion()

    async def test_aclaracion_sin_herramientas(self):
        r = await self.flujo([evaluacion(estado="falta_informacion", herramientas=[])], None)
        self.assertEqual(r.estado, "requiere_aclaracion")
        self.sin_ejecucion()

    async def test_exito_usa_url_catalogo_y_mensaje_original(self):
        r = await self.flujo([evaluacion()])
        self.assertEqual((r.estado, r.respuesta), ("Ok", "Sí"))
        self.c["obtener_mcp"].assert_called_once_with("autos")
        self.c["obtener_herramientas_mcp"].assert_awaited_once_with("http://mcp.test/mcp")
        self.c["llamar_herramienta_mcp"].assert_awaited_once_with("consultar", {"auto": "Fiat"}, "http://mcp.test/mcp")
        entrada = self.c["llm"].consultar_llm.call_args.args[1]
        self.assertEqual(entrada[-1]["content"], "¿Fiat es el mejor auto?")
        self.c["redactar_respuesta"].assert_awaited_once_with(
            "¿Fiat es el mejor auto?", [], "consultar", {"auto": "Fiat"},
            {"isError": False, "structuredContent": {"respuesta": "Sí"}},
        )

    async def test_devuelve_redaccion_y_no_resultado_crudo(self):
        self.c["llamar_herramienta_mcp"].return_value = {"content": [{"type": "text", "text": '{"respuesta":"No"}'}]}
        self.c["redactar_respuesta"].return_value = "Entiendo que prefieras el Falcon Futura. Según esta consulta, el elegido sigue siendo el Fiat Pulse."
        r = await self.flujo([evaluacion()])
        self.assertEqual(r.respuesta, self.c["redactar_respuesta"].return_value)
        self.assertEqual(r.herramientas, ["consultar"])

    async def test_eleccion_usuario_entre_varios(self):
        r = await self.flujo([evaluacion(), evaluacion("cocina")], mcp="cocina")
        self.assertEqual(r.mcp_recomendado, "cocina")
        self.c["obtener_mcp"].assert_called_once_with("cocina")

    async def test_marcador_swagger_no_impide_seleccion_automatica(self):
        r = await self.flujo([evaluacion()], mcp="string")
        self.assertEqual(r.estado, "Ok")
        self.c["llamar_herramienta_mcp"].assert_awaited_once()

    async def test_marcador_swagger_no_elimina_ambiguedad(self):
        r = await self.flujo([evaluacion(), evaluacion("cocina")], recomendado=None, mcp="string")
        self.assertEqual(r.estado, "requiere_aclaracion")
        self.assertEqual(r.respuesta, "¿Te referís a un auto o a un plato?")
        self.sin_ejecucion()

    async def test_respuesta_natural_con_contexto_resuelve_eleccion(self):
        candidatos = [evaluacion(), evaluacion("cocina")]
        self.c["consultar_jeveador"] = AsyncMock(side_effect=[
            RecomendacionJev(mcp_recomendado=None, evaluaciones=candidatos),
            RecomendacionJev(mcp_recomendado="cocina", evaluaciones=candidatos),
        ])
        primera = await self.c["responder_chat_jev"](ConsultaChatJev(mensaje="¿Cuál es el mejor?"))
        self.assertEqual(primera.estado, "requiere_aclaracion")
        self.c["llamar_herramienta_mcp"].assert_not_awaited()
        contexto = ["Usuario: ¿Cuál es el mejor?", "Asistente: " + primera.respuesta]
        segunda = await self.c["responder_chat_jev"](ConsultaChatJev(mensaje="un plato", contexto=contexto))
        self.assertEqual((segunda.estado, segunda.mcp_recomendado), ("Ok", "cocina"))
        self.c["consultar_jeveador"].assert_awaited_with("un plato", contexto)
        self.c["obtener_mcp"].assert_called_once_with("cocina")

    async def test_aclaracion_usa_capacidades_reales_sin_identificadores(self):
        consulta = ConsultaChatJev(mensaje="¿Cuál es el mejor?")
        from schemas.chat_jev import EvaluacionJev
        texto = await self.c["preguntar_seleccion_real"](consulta, [EvaluacionJev(**evaluacion())])
        self.assertEqual(texto, "¿Te referís a un auto o a un plato?")
        argumentos = self.c["redactar_aclaracion"].call_args.args
        self.assertEqual(argumentos[0], consulta.mensaje)
        self.assertEqual(argumentos[2][0]["capacidades"][0]["descripcion"], "Consultar un auto")
        self.assertNotIn("mcp_evaluado", argumentos[2][0])
        self.c["llamar_herramienta_mcp"].assert_not_awaited()

    async def test_confirmacion_envia_contexto_a_jev_y_llm(self):
        contexto = ["Usuario: no, el mejor es el falco", "Asistente: ¿Querés que consulte si el Falco es el mejor auto?"]
        self.c["consultar_jeveador"] = AsyncMock(return_value=RecomendacionJev(
            mcp_recomendado="autos", evaluaciones=[evaluacion()]))
        self.c["llm"].consultar_llm.return_value.output[0]["arguments"] = '{"auto":"Falco"}'
        r = await self.c["responder_chat_jev"](ConsultaChatJev(mensaje="si", contexto=contexto))
        self.assertEqual(r.estado, "Ok")
        self.c["consultar_jeveador"].assert_awaited_once_with("si", contexto)
        entrada = self.c["llm"].consultar_llm.call_args.args[1]
        self.assertIn("Falco", entrada[-2]["content"])
        self.assertEqual(entrada[-1]["content"], "si")
        self.c["llamar_herramienta_mcp"].assert_awaited_once_with("consultar", {"auto": "Falco"}, "http://mcp.test/mcp")

    async def test_pedido_general_aclarado_no_repite_comparacion_anterior(self):
        contexto = [
            "Usuario: ¿Qué es mejor, un flan o una milanesa?",
            "Asistente: ¿Mejor en qué sentido?",
            "Usuario: en el sentido de cuál es el mejor plato",
        ]
        self.c["consultar_jeveador"] = AsyncMock(return_value=RecomendacionJev(
            mcp_recomendado="cocina", evaluaciones=[evaluacion("cocina", herramientas=["mejor_plato"])]))
        self.c["obtener_herramientas_mcp"].return_value = [{
            "name": "mejor_plato", "description": "Consulta cuál es el mejor plato",
            "parameters": {"type": "object", "properties": {}},
        }]
        self.c["llm"].consultar_llm.return_value.output = [{
            "type": "function_call", "name": "mejor_plato", "call_id": "plato_1", "arguments": "{}",
        }]
        self.c["llamar_herramienta_mcp"].return_value = {"structuredContent": {"respuesta": "Milanesas"}}
        self.c["redactar_respuesta"].return_value = "Las milanesas son el mejor plato, y punto."
        r = await self.c["responder_chat_jev"](ConsultaChatJev(mensaje="¿Cuál es el mejor plato de cocina?", contexto=contexto))
        self.assertEqual(r.herramientas, ["mejor_plato"])
        self.assertEqual(r.respuesta, "Las milanesas son el mejor plato, y punto.")
        self.c["preguntar_seleccion"].assert_not_awaited()
        self.c["llamar_herramienta_mcp"].assert_awaited_once_with("mejor_plato", {}, "http://mcp.test/mcp")
        entrada = self.c["llm"].consultar_llm.call_args.args[1]
        self.assertEqual(entrada[-1]["content"], "¿Cuál es el mejor plato de cocina?")

    async def test_contexto_se_envia_en_post_evaluar(self):
        cliente = AsyncMock()
        cliente.post.return_value = httpx.Response(200, json={"mcp_recomendado": None, "evaluaciones": []}, request=httpx.Request("POST", "http://jev.test/evaluar"))
        with patch.object(httpx, "AsyncClient") as fabrica:
            fabrica.return_value.__aenter__.return_value = cliente
            await self.c["consultar_jeveador"]("si", ["Usuario: Falco"])
        cliente.post.assert_awaited_once_with("http://jev.test/evaluar", json={"mensaje": "si", "contexto": ["Usuario: Falco"]})

    async def test_argumentos_invalidos_no_ejecuta(self):
        self.c["llm"].consultar_llm.return_value.output[0]["arguments"] = '{"auto": 42}'
        with self.assertRaises(HTTPException) as error:
            await self.flujo([evaluacion()])
        self.assertEqual(error.exception.status_code, 502)
        self.c["llamar_herramienta_mcp"].assert_not_awaited()

    async def test_herramienta_no_autorizada_no_ejecuta(self):
        self.c["llm"].consultar_llm.return_value.output[0]["name"] = "otra"
        with self.assertRaises(HTTPException):
            await self.flujo([evaluacion()])
        self.c["llamar_herramienta_mcp"].assert_not_awaited()

    async def test_llm_pide_datos_no_ejecuta(self):
        self.c["llm"].consultar_llm.return_value.output = []
        r = await self.flujo([evaluacion()])
        self.assertEqual(r.estado, "requiere_aclaracion")
        self.c["llamar_herramienta_mcp"].assert_not_awaited()

    async def test_catalogo_desactualizado_no_ejecuta(self):
        self.c["obtener_herramientas_mcp"].return_value = []
        with self.assertRaises(HTTPException):
            await self.flujo([evaluacion()])
        self.sin_ejecucion()

    async def test_mcp_deshabilitado_no_ejecuta(self):
        self.c["obtener_mcp"].return_value = None
        with self.assertRaises(HTTPException) as error:
            await self.flujo([evaluacion()])
        self.assertEqual(error.exception.status_code, 503)
        self.sin_ejecucion()

    async def test_error_mcp_no_informa_exito(self):
        self.c["llamar_herramienta_mcp"].return_value = {"isError": True, "content": [{"type": "text", "text": "Falló"}]}
        r = await self.flujo([evaluacion()])
        self.assertEqual(r.estado, "error_mcp")

    async def test_error_de_negocio_mcp_no_informa_exito(self):
        for resultado in [
            {"isError": False, "structuredContent": {"estado": "Error", "respuesta": "No hay datos", "status_code": 500}},
            {"isError": False, "content": [{"type": "text", "text": '{"estado":"Error","respuesta":"No hay datos","status_code":500}'}]},
        ]:
            with self.subTest(resultado=resultado):
                self.c["llamar_herramienta_mcp"].return_value = resultado
                r = await self.flujo([evaluacion()])
                self.assertEqual(r.estado, "error_mcp")
                self.assertEqual(r.resultado, resultado)

    async def test_pronostico_parcial_sigue_siendo_exitoso(self):
        self.c["llamar_herramienta_mcp"].return_value = {"structuredContent": {
            "estado": "Ok", "respuesta": {"datos": {
                "temperatura": {"estado": "Ok", "valor": "13.2 °C"},
                "presion": {"estado": "sin_datos", "respuesta": "No hay datos para presion"},
            }},
        }}
        r = await self.flujo([evaluacion()])
        self.assertEqual(r.estado, "Ok")

    async def test_json_mcp_en_texto_extrae_respuesta(self):
        self.c["llamar_herramienta_mcp"].return_value = {
            "content": [{"type": "text", "text": '{\n "estado": "Ok", "respuesta": "Fiat Pulse"\n}'}],
        }
        self.assertEqual(self.c["texto_resultado"](self.c["llamar_herramienta_mcp"].return_value), "Fiat Pulse")

    async def test_texto_mcp_sin_json_se_conserva(self):
        self.c["llamar_herramienta_mcp"].return_value = {
            "content": [{"type": "text", "text": "Fiat Pulse"}],
        }
        self.assertEqual(self.c["texto_resultado"](self.c["llamar_herramienta_mcp"].return_value), "Fiat Pulse")

    async def test_post_evaluar_con_url_base_o_completa(self):
        for url in ("http://jev.test", "http://jev.test/evaluar"):
            with patch.dict(os.environ, {"JEV_URL": url}):
                cliente = AsyncMock()
                cliente.post.return_value = httpx.Response(200, json={"mcp_recomendado": None, "evaluaciones": []}, request=httpx.Request("POST", url))
                with patch.object(httpx, "AsyncClient") as fabrica:
                    fabrica.return_value.__aenter__.return_value = cliente
                    await self.c["consultar_jeveador"]("pedido")
                cliente.post.assert_awaited_once_with("http://jev.test/evaluar", json={"mensaje": "pedido"})

    async def test_respuesta_jeveador_invalida(self):
        cliente = AsyncMock()
        cliente.post.return_value = httpx.Response(200, json={"evaluaciones": "incorrecto"}, request=httpx.Request("POST", "http://jev.test/evaluar"))
        with patch.object(httpx, "AsyncClient") as fabrica:
            fabrica.return_value.__aenter__.return_value = cliente
            with self.assertRaises(HTTPException) as error:
                await self.c["consultar_jeveador"]("pedido")
        self.assertEqual(error.exception.status_code, 502)

    async def test_recomendacion_inconsistente_no_ejecuta(self):
        with self.assertRaises(HTTPException) as error:
            await self.flujo([evaluacion(), evaluacion("cocina", estado="no_sirve", herramientas=[])], "cocina")
        self.assertEqual(error.exception.status_code, 502)
        self.sin_ejecucion()

    async def test_error_http_jeveador(self):
        cliente = AsyncMock()
        cliente.post.return_value = httpx.Response(500, request=httpx.Request("POST", "http://jev.test/evaluar"))
        with patch.object(httpx, "AsyncClient") as fabrica:
            fabrica.return_value.__aenter__.return_value = cliente
            with self.assertRaises(HTTPException) as error:
                await self.c["consultar_jeveador"]("pedido")
        self.assertEqual(error.exception.status_code, 502)
        self.assertIn("HTTP 500", error.exception.detail)

    async def test_timeout_jeveador(self):
        cliente = AsyncMock()
        cliente.post.side_effect = httpx.ReadTimeout("Tiempo agotado simulado")
        with patch.object(httpx, "AsyncClient") as fabrica:
            fabrica.return_value.__aenter__.return_value = cliente
            with self.assertRaises(HTTPException) as error:
                await self.c["consultar_jeveador"]("pedido")
        self.assertEqual(error.exception.status_code, 504)


class ContratoClienteTests(unittest.TestCase):
    def test_formato_http_en_todos_los_estados(self):
        archivo = Path(__file__).resolve().parents[1] / "routers/chat_jev.py"
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        arbol.body = [n for n in arbol.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        responder = AsyncMock()
        contexto = {"logging": logging, "__name__": "prueba_chat_jev", "HTTPException": HTTPException, "JSONResponse": JSONResponse, "APIRouter": APIRouter, "RespuestaChat": RespuestaChat,
                    "ConsultaChatJev": ConsultaChatJev, "responder_chat_jev": responder}
        exec(compile(arbol, str(archivo), "exec"), contexto)
        app = FastAPI()
        app.include_router(contexto["router"])
        with TestClient(app) as cliente:
            for estado in ("Ok", "sin_coincidencias", "seleccion_requerida", "requiere_aclaracion", "error_mcp"):
                with self.subTest(estado=estado):
                    responder.return_value = RespuestaChatJev(estado=estado, respuesta="Mensaje", evaluaciones=[], herramientas=["mejor_auto"] if estado == "Ok" else [])
                    respuesta = cliente.post("/chat/jev", json={"mensaje": "pedido"})
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(respuesta.json(), {
                        "estado": "Ok", "respuesta": "La herramienta informó un error: Mensaje" if estado == "error_mcp" else "Mensaje",
                        "herramientas": ["mejor_auto"] if estado == "Ok" else [],
                    })


if __name__ == "__main__":
    unittest.main()
