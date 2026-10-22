"""Recoge evidencia de unittest y genera informes HTML estáticos, sin leer .env."""

import argparse
import datetime as dt
import html
import inspect
import json
import re
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch


DIRECTORIO = Path(__file__).resolve().parent
PROYECTO = DIRECTORIO.parent
EVIDENCIAS = DIRECTORIO / ".evidencias"
CSS = """
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172339;font:16px/1.65 system-ui,sans-serif}
main{max-width:1120px;margin:auto;padding:40px 24px}a{color:#145bc2}h1{font-size:clamp(26px,4vw,38px);line-height:1.25}
h2{font-size:20px;margin-top:0}.muted{color:#617087}.card{background:white;border:1px solid #dfe5ef;border-radius:14px;padding:24px;margin:20px 0}
.badge{display:inline-block;border-radius:20px;padding:5px 14px;font-size:13px;font-weight:700;background:#e7edf8;color:#214a89}
.APROBADA{background:#dcf5e6;color:#155c33}.FALLIDA,.ERROR{background:#ffe3e3;color:#9c2222}.OMITIDA{background:#fff0ce;color:#805800}
pre{overflow:auto;padding:18px;background:#111c30;color:#e1eaff;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
code{font-family:Consolas,monospace}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #e5eaf2;vertical-align:top}
th{color:#59697f;font-size:13px}input{width:100%;padding:12px;border:1px solid #c4cede;border-radius:8px;font:inherit}details summary{cursor:pointer;color:#145bc2}
.stats{display:flex;gap:12px;flex-wrap:wrap}.stats .card{flex:1;min-width:150px}.number{display:block;font-size:30px;font-weight:750}
@media(max-width:650px){main{padding:22px 12px}.card{padding:16px}table{font-size:13px}th,td{padding:8px}.componente{display:none}}
"""


def ahora():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds")


def guardar_evidencia(nombre, casos):
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    (EVIDENCIAS / f"{nombre}.json").write_text(json.dumps(casos, ensure_ascii=False, indent=2), encoding="utf-8")


class ResultadoConEvidencia(unittest.TestResult):
    def __init__(self, componente):
        super().__init__()
        self.componente = componente
        self.casos = []

    def startTest(self, test):
        super().startTest(test)
        self.inicio = time.monotonic()
        metodo = getattr(test, test._testMethodName)
        try:
            fuente = inspect.getsource(metodo)
        except (TypeError, OSError) as e:
            fuente = "No se pudo recuperar el código de la prueba: " + type(e).__name__
        self.actual = {
            "id": self.componente + "." + test.id(), "componente": self.componente,
            "titulo": test._testMethodName.removeprefix("test_").replace("_", " ").capitalize(),
            "tipo": "Aislada / simulada", "objetivo": inspect.getdoc(metodo) or test._testMethodName.removeprefix("test_").replace("_", " ").capitalize() + ".",
            "esperado": "Todas las aserciones de esta prueba deben cumplirse; los casos de rechazo deben conservar su código de error.",
            "estado": "APROBADA", "fecha": ahora(), "fuente": fuente,
            "evidencia": "La prueba finalizó sin errores ni aserciones fallidas.",
            "alcance": "Servicios HTTP, LLM y catálogos se simulan; SQLite y políticas se prueban con archivos temporales. Esto verifica el código y no demuestra inmunidad del modelo ante todos los ataques.",
        }

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.actual["estado"] = "FALLIDA"
        self.actual["evidencia"] = self._exc_info_to_string(err, test)

    def addError(self, test, err):
        super().addError(test, err)
        self.actual["estado"] = "ERROR"
        self.actual["evidencia"] = self._exc_info_to_string(err, test)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.actual["estado"] = "OMITIDA"
        self.actual["evidencia"] = reason

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.actual["estado"] = "FALLIDA"
            self.actual["evidencia"] = self._exc_info_to_string(err, test)

    def stopTest(self, test):
        self.actual["segundos"] = round(time.monotonic() - self.inicio, 3)
        self.casos.append(self.actual)
        super().stopTest(test)


def ejecutar_suite(componente):
    carpeta = PROYECTO / componente
    # Nunca cargar archivos privados ni usar configuraciones heredadas del proceso.
    with patch("dotenv.load_dotenv", return_value=False), patch.dict("os.environ", {"MAX_CONTEXTO": "20", "UMBRAL_DEFECTO": "0.61"}, clear=True):
        suite = unittest.TestLoader().discover(str(carpeta / "tests"), top_level_dir=str(carpeta))
        resultado = ResultadoConEvidencia(componente)
        suite.run(resultado)
    guardar_evidencia(componente, resultado.casos)
    print(json.dumps({"componente": componente, "pruebas": resultado.testsRun, "fallos": len(resultado.failures), "errores": len(resultado.errors)}, ensure_ascii=False))
    return resultado.wasSuccessful()


def pagina(titulo, contenido, script=""):
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(titulo) + '</title><style>' + CSS + '</style></head><body><main>' + contenido + '</main>' + script + '</body></html>'


def generar_html():
    casos = []
    for nombre in ("api", "jeveador", "integracion"):
        archivo = EVIDENCIAS / f"{nombre}.json"
        if archivo.exists():
            casos.extend(json.loads(archivo.read_text(encoding="utf-8")))
    if not casos:
        raise RuntimeError("No hay evidencia de pruebas para generar informes.")
    filas = []
    for numero, caso in enumerate(casos, 1):
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", caso["id"])[-150:]
        nombre = f"{numero:04d}_{slug}.html"
        estado = caso["estado"]
        evidencia = caso["evidencia"]
        if not isinstance(evidencia, str):
            evidencia = json.dumps(evidencia, ensure_ascii=False, indent=2)
        cuerpo = '<a href="index.html">← Índice de pruebas</a><h1>' + html.escape(caso["titulo"]) + '</h1>'
        cuerpo += '<span class="badge ' + estado + '">' + estado + '</span> <span class="badge">' + html.escape(caso["tipo"]) + '</span>'
        cuerpo += '<p class="muted">' + html.escape(caso["fecha"]) + ' · ' + str(caso.get("segundos", 0)) + ' segundos · ' + html.escape(caso["componente"]) + '</p>'
        for titulo, clave in [("Qué se probó", "objetivo"), ("Resultado esperado", "esperado"), ("Alcance de esta evidencia", "alcance")]:
            cuerpo += '<section class="card"><h2>' + titulo + '</h2><p>' + html.escape(caso[clave]) + '</p></section>'
        cuerpo += '<section class="card"><h2>Resultado obtenido</h2><pre>' + html.escape(evidencia) + '</pre></section>'
        if caso.get("fuente"):
            cuerpo += '<details class="card"><summary>Código exacto de la prueba</summary><pre>' + html.escape(caso["fuente"]) + '</pre></details>'
        cuerpo += '<p class="muted">Identificador: <code>' + html.escape(caso["id"]) + '</code></p>'
        (DIRECTORIO / nombre).write_text(pagina(caso["titulo"], cuerpo), encoding="utf-8")
        filas.append('<tr><td>' + f"{numero:04d}" + '</td><td><a href="' + nombre + '">' + html.escape(caso["titulo"]) + '</a></td><td class="componente">' + html.escape(caso["componente"]) + '</td><td>' + html.escape(caso["tipo"]) + '</td><td><span class="badge ' + estado + '">' + estado + '</span></td></tr>')
    aprobadas = sum(c["estado"] == "APROBADA" for c in casos)
    contenido = '<p class="muted">JEVraulio · Evidencia de pruebas</p><h1>Controles de herramientas MCP</h1>'
    contenido += '<p>Permisos independientes de Jev, destinos permitidos, validación de catálogos y resultados, regresiones y consultas con los componentes encendidos.</p>'
    contenido += '<div class="stats">' + ''.join('<div class="card">' + etiqueta + '<span class="number">' + str(valor) + '</span></div>' for etiqueta, valor in [("Pruebas", len(casos)), ("Aprobadas", aprobadas), ("Para revisar", len(casos) - aprobadas)]) + '</div>'
    contenido += '<section class="card"><h2>Cómo leer estos informes</h2><p>Cada enlace corresponde a una prueba ejecutada. Las pruebas aisladas usan datos ficticios y servicios simulados; las de integración consultan los servicios reales ya encendidos y pueden consumir tokens. Un rechazo esperado (403, 422 o 502) puede ser una prueba aprobada si demuestra el bloqueo previsto.</p><p>No se modificaron registros MCP ni umbrales de la base real. No se leyeron archivos .env. No se implementó ni evaluó autenticación administrativa: está fuera de este alcance. Estas pruebas no demuestran seguridad absoluta ni resistencia universal a prompt injection.</p></section>'
    contenido += '<label for="buscar">Buscar prueba</label><input id="buscar" type="search" placeholder="Permisos, resultados, capacidades…"><section class="card" style="overflow:auto"><table><thead><tr><th>Nº</th><th>Prueba</th><th class="componente">Componente</th><th>Modalidad</th><th>Estado</th></tr></thead><tbody>' + ''.join(filas) + '</tbody></table></section>'
    script = '<script>document.getElementById("buscar").addEventListener("input",function(){const q=this.value.toLocaleLowerCase();document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLocaleLowerCase().includes(q));});</script>'
    (DIRECTORIO / "index.html").write_text(pagina("Resultados de pruebas · JEVraulio", contenido, script), encoding="utf-8")
    print(json.dumps({"informes": len(casos), "aprobadas": aprobadas, "para_revisar": len(casos) - aprobadas, "indice": "resultados_pruebas/index.html"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["api", "jeveador"])
    parser.add_argument("--generar", action="store_true")
    args = parser.parse_args()
    if args.suite:
        sys.exit(0 if ejecutar_suite(args.suite) else 1)
    if args.generar:
        generar_html()
