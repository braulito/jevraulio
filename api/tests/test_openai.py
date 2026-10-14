"""Cliente LLM usado por Jeveador: HTTP simulado y configuración ficticia."""

import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

with patch("dotenv.load_dotenv", return_value=False):
    from funciones import openai_funciones as llm


class OpenaiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        entorno = patch.dict(os.environ, {"MODELO_OPENAI": "gpt-4.1-mini"}, clear=True)
        entorno.start()
        self.addCleanup(entorno.stop)
        guardar = patch("funciones.billing.registrar_consumo")
        self.billing = guardar.start()
        self.addCleanup(guardar.stop)

    async def consultar(self, cuerpo=None, status=200, error=None, tools=None):
        self.enviado = None

        def responder(request):
            self.enviado = json.loads(request.content)
            if error is not None:
                raise error
            return httpx.Response(status, json=cuerpo)

        async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
            return await llm.consultar_llm(client, [{"role": "user", "content": "pedido ficticio"}], tools or [])

    def cuerpo(self):
        return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "respuesta simulada"}]}]}

    async def test_modelo_opciones_y_cache_estable(self):
        with patch.dict(os.environ, {"MODELO_OPENAI": "gpt-6-luna"}):
            resultado = await self.consultar(self.cuerpo())
        self.assertEqual(llm.extraer_texto(resultado.output), "respuesta simulada")
        self.assertEqual(self.enviado["model"], "gpt-6-luna")
        self.assertEqual(self.enviado["reasoning"], {"effort": "none"})
        self.assertEqual(self.enviado["service_tier"], "default")
        self.assertFalse(self.enviado["parallel_tool_calls"])
        self.assertFalse(self.enviado["store"])
        self.assertEqual(self.enviado["prompt_cache_key"], llm.clave_cache_prompt("gpt-6-luna", []))

    async def test_usage_completo_y_costo_sin_duplicar_tokens(self):
        cuerpo = self.cuerpo()
        cuerpo["usage"] = {"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 1000}, "output_tokens": 100, "output_tokens_details": {"reasoning_tokens": 40}, "total_tokens": 2100}
        await self.consultar(cuerpo)
        datos = self.billing.call_args.args[0]
        self.assertEqual(datos["tokens"], cuerpo["usage"])
        self.assertEqual(datos["metodo"], "respuesta")
        self.assertAlmostEqual(datos["costo_estimado_usd"], 0.00066)
        self.assertNotIn("respuesta simulada", json.dumps(datos))
        self.assertNotIn("pedido ficticio", json.dumps(datos))

    async def test_error_credenciales_no_expone_cuerpo(self):
        with self.assertRaises(HTTPException) as error:
            await self.consultar({"error": {"message": "detalle ficticio del proveedor"}}, status=401)
        self.assertEqual(error.exception.status_code, 502)
        self.assertNotIn("detalle ficticio del proveedor", error.exception.detail)

    async def test_timeout_y_respuesta_invalida(self):
        with self.assertRaises(HTTPException) as error:
            await self.consultar(error=httpx.ReadTimeout("timeout simulado"))
        self.assertEqual(error.exception.status_code, 504)
        with self.assertRaises(HTTPException) as error:
            await self.consultar({"status": "incomplete", "output": []})
        self.assertEqual(error.exception.status_code, 502)

    def test_cache_cambia_con_modelo_o_catalogo(self):
        tools = [{"name": "convertir_divisas", "description": "Convierte monedas"}]
        clave = llm.clave_cache_prompt("gpt-4.1-mini", tools)
        self.assertNotEqual(clave, llm.clave_cache_prompt("otro-modelo", tools))
        self.assertNotEqual(clave, llm.clave_cache_prompt("gpt-4.1-mini", []))


if __name__ == "__main__":
    unittest.main()
