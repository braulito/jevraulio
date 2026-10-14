"""Billing compartido por /chat/jev, sin configuración ni SQLite real."""

import unittest
from unittest.mock import patch

with patch("dotenv.load_dotenv", return_value=False):
    from funciones import billing


def mensaje(texto):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": texto}]}]}


class BillingTests(unittest.TestCase):
    def setUp(self):
        guardar = patch("funciones.billing.guardar_billing")
        self.guardar_mock = guardar.start()
        self.addCleanup(guardar.stop)

    def test_registra_tokens_y_costo(self):
        datos = {
            "tokens": {"input_tokens": 257, "output_tokens": 15, "total_tokens": 272},
            "costo_estimado_usd": 3.32e-05,
            "metodo": "tool_call", "herramientas": [],
        }
        with self.assertNoLogs(billing.logger, level="INFO"):
            billing.registrar_consumo(datos)
        self.guardar_mock.assert_called_once_with(datos)

    def test_datos_no_disponibles_no_inventa_consumo(self):
        datos = {"tokens": None, "costo_estimado_usd": None}
        with self.assertNoLogs(billing.logger, level="INFO"):
            billing.registrar_consumo(datos)
        self.guardar_mock.assert_called_once_with(datos)

    def test_identifica_tool_call_y_respuesta_con_mcp(self):
        tool = {"type": "function_call", "name": "herramienta_nueva", "call_id": "call_1"}
        self.assertEqual(billing.identificar_metodo([tool], []), ("tool_call", []))
        entrada = [tool, {"type": "function_call_output", "call_id": "call_1", "output": "resultado"}]
        self.assertEqual(billing.identificar_metodo(mensaje("Respuesta")["output"], entrada), ("mcp", ["herramienta_nueva"]))


    def test_costo_sin_cache_y_modelo_desconocido(self):
        usage = {"input_tokens": 1000, "output_tokens": 100}
        self.assertAlmostEqual(billing.costo_uso(usage, "gpt-4.1-mini"), 0.00056)
        self.assertIsNone(billing.costo_uso(usage, "modelo-desconocido"))
        self.assertIsNone(billing.costo_uso(None, "gpt-4.1-mini"))

    def test_luna_costo_lectura_y_escritura_cache(self):
        usage = {
            "input_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 1000, "cache_write_tokens": 500},
            "output_tokens": 100,
            "output_tokens_details": {"reasoning_tokens": 40},
        }
        self.assertAlmostEqual(billing.costo_uso(usage, "gpt-6-luna"), 0.0001725)
        self.assertAlmostEqual(billing.costo_uso({"input_tokens": 1000, "output_tokens": 100}, "gpt-6-luna"), 0.00015)

    def test_luna_tarifa_contexto_largo(self):
        self.assertAlmostEqual(billing.costo_uso({"input_tokens": 300000, "output_tokens": 100}, "gpt-6-luna"), 0.060075)


if __name__ == "__main__":
    unittest.main()
