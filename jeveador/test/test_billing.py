"""Verificación del registro completo, sin usar configuración real."""

import unittest
from unittest.mock import patch

with patch.dict("os.environ", {"UMBRAL_DEFECTO": "0.61"}, clear=True):
    from funciones.billing import registrar_uso_jev


class TestBilling(unittest.TestCase):
    def registrar(self, usage):
        datos = {
            "id": "gen-dec-prueba",
            "model": "typesafe/jev-1.13",
            "provider": "TypeSafe",
            "usage": usage,
            "answers": {"texto": "contenido que no debe registrarse"},
            "headers": {"Authorization": "credencial-ficticia"},
        }
        with self.assertNoLogs("uvicorn.error.billing.jev", level="INFO"), \
                patch("funciones.billing.guardar_billing") as guardar:
            registrar_uso_jev(datos, "typesafe/jev-1.13")
        self.guardado = guardar.call_args.kwargs
        guardar.assert_called_once()

    def test_preserva_todos_los_detalles_sin_duplicar_tokens(self):
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "cost": 0.000012,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens_details": {"reasoning_tokens": 15},
            "cost_details": {"upstream_inference_cost": 0.00001},
            "campo_nuevo": {"valor": 3},
        }
        self.registrar(usage)
        self.assertEqual(self.guardado, {
            "input_tokens": 100, "cached_tokens": 40, "cache_write_tokens": 0,
            "output_tokens": 20, "reasoning_tokens": 15, "total_tokens": 120,
            "costo_estimado_usd": 0.000012,
        })

    def test_respeta_total_informado(self):
        self.registrar({"input_tokens": 10, "output_tokens": 5, "total_tokens": 16})
        self.assertEqual(self.guardado["total_tokens"], 16)

    def test_datos_ausentes_se_guardan_como_cero(self):
        for usage in [None, {}, {"input_tokens": 10}, {"cost": 0}]:
            with self.subTest(usage=usage):
                self.registrar(usage)
                self.assertEqual(self.guardado["total_tokens"], (usage or {}).get("input_tokens", 0))
                for campo in ("cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "costo_estimado_usd"):
                    self.assertEqual(self.guardado[campo], 0)

    def test_aliases_y_valores_null(self):
        self.registrar({
            "prompt_tokens": 50, "completion_tokens": 10, "total_tokens": None,
            "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 5},
            "completion_tokens_details": {"reasoning_tokens": None}, "cost": None,
        })
        self.assertEqual(self.guardado, {
            "input_tokens": 50, "cached_tokens": 20, "cache_write_tokens": 5,
            "output_tokens": 10, "reasoning_tokens": 0, "total_tokens": 60,
            "costo_estimado_usd": 0,
        })


if __name__ == "__main__":
    unittest.main()
