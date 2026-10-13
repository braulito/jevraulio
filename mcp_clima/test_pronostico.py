import ast
import logging
from pathlib import Path
import unittest
from unittest.mock import Mock

from funciones import combinar_pronostico


class PronosticoTests(unittest.TestCase):
    def consultas(self, mascara=15):
        valores = {"temperatura": "13.2 °C", "precipitaciones": "80 % de lluvias", "sensacion_termica": "10.5 °C", "presion": "1013.2 hPa"}
        return {
            nombre: Mock(return_value={"estado": "Ok", "respuesta": f"2026-10-18 20:00, {valor}"}
                         if mascara & (1 << indice) else {"estado": "Error", "status_code": 500})
            for indice, (nombre, valor) in enumerate(valores.items())
        }

    def test_todas_las_combinaciones_de_fallos(self):
        for mascara in range(16):
            with self.subTest(mascara=mascara):
                consultas = self.consultas(mascara)
                resultado = combinar_pronostico(consultas)
                for funcion in consultas.values():
                    funcion.assert_called_once_with()
                self.assertEqual(resultado["estado"], "Ok" if mascara else "Error")
                datos = resultado["respuesta"]["datos"] if mascara else resultado["datos"]
                for indice, nombre in enumerate(consultas):
                    self.assertEqual(datos[nombre]["estado"], "Ok" if mascara & (1 << indice) else "sin_datos")
                    if not mascara & (1 << indice):
                        self.assertEqual(datos[nombre]["respuesta"], f"No hay datos para {nombre}")
                if mascara:
                    self.assertEqual(resultado["respuesta"]["fecha_local"], "2026-10-18 20:00")
                    self.assertTrue(resultado["respuesta"]["fechas_coinciden"])
                else:
                    self.assertEqual(resultado["status_code"], 500)

    def test_fechas_distintas_se_conservan(self):
        consultas = self.consultas()
        consultas["presion"].return_value = {"estado": "Ok", "respuesta": "2026-10-19 20:00, 1013.2 hPa"}
        resultado = combinar_pronostico(consultas)["respuesta"]
        self.assertFalse(resultado["fechas_coinciden"])
        self.assertIsNone(resultado["fecha_local"])
        self.assertIn("advertencia", resultado)
        self.assertEqual(resultado["datos"]["presion"]["fecha_local"], "2026-10-19 20:00")
        self.assertEqual(resultado["datos"]["temperatura"]["fecha_local"], "2026-10-18 20:00")

    def test_excepcion_y_respuesta_malformada_no_invalidan_otras(self):
        consultas = self.consultas()
        consultas["temperatura"].side_effect = RuntimeError("Fallo simulado")
        consultas["presion"].return_value = {"estado": "Ok", "respuesta": "fecha invalida, 1013 hPa"}
        with self.assertLogs(level="ERROR"):
            resultado = combinar_pronostico(consultas)
        self.assertEqual(resultado["estado"], "Ok")
        self.assertEqual(resultado["respuesta"]["datos"]["temperatura"]["estado"], "sin_datos")
        self.assertEqual(resultado["respuesta"]["datos"]["presion"]["estado"], "sin_datos")
        self.assertEqual(resultado["respuesta"]["datos"]["precipitaciones"]["valor"], "80 % de lluvias")

    def test_tool_llama_a_las_cuatro_funciones_sin_cargar_configuracion(self):
        # Ejecutar solo la función seleccionada del AST, sin importar server ni .env.
        ruta = Path(__file__).with_name("server.py")
        arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))
        funcion = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "get_pronostico")
        funcion.decorator_list = []
        arbol.body = [funcion]
        consultas = self.consultas()
        espacio = {"combinar_pronostico": combinar_pronostico, **{f"get_{nombre}": consulta for nombre, consulta in consultas.items()}}
        exec(compile(arbol, str(ruta), "exec"), espacio)
        self.assertEqual(espacio["get_pronostico"]()["estado"], "Ok")
        for consulta in consultas.values():
            consulta.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
