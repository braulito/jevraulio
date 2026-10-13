"""Aplicación Flask para conversar con la API y consultar sus costos."""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from secrets import compare_digest, token_bytes, token_urlsafe
import logging

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from cliente_api import consultar_chat


class ErrorConsultaApi(RuntimeError):
    """La API falló o devolvió un contrato que la página no puede utilizar."""


def solicitar_api(operacion, *args, tipo=dict, campos=(), **kwargs):
    try:
        exito, salida = operacion(*args, **kwargs)
        if type(exito) is not bool:
            raise ErrorConsultaApi
        if not exito:
            return False, salida if isinstance(salida, dict) else {"status_code": 502}
        if not isinstance(salida, tipo):
            raise ErrorConsultaApi
        elementos = salida if tipo is list else [salida]
        if campos and any(not isinstance(elemento, dict) or not set(campos).issubset(elemento) for elemento in elementos):
            raise ErrorConsultaApi
        return True, salida
    except Exception as error:
        logging.getLogger(__name__).error("Falló una consulta administrativa a la API. Tipo: %s", type(error).__name__)
        return False, {"status_code": 502}


def crear_app(*, cargar_entorno: bool = True) -> Flask:
    """Las verificaciones pueden omitir la carga del archivo de configuración."""
    if cargar_entorno:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env")

    from funciones import (
        agregar_mcp_api, consultar_costos_api, consultar_mcp_api, consultar_mcps_api,
        consultar_umbral_api, eliminar_mcp_api, guardar_estado_mcp_api, guardar_umbral_api,
    )

    app = Flask(__name__)
    # Werkzeug conserva su salida de acceso sin repetirla en el logger raíz.
    logging.getLogger("werkzeug").propagate = False
    app.secret_key = token_bytes(32)
    try:
        max_contexto = int(os.getenv("MAX_CONTEXTO", "20"))
        if max_contexto <= 0:
            raise ValueError
    except ValueError as error:
        raise ValueError("MAX_CONTEXTO debe ser un entero mayor que cero.") from error
    app.config["MAX_CONTEXTO"] = max_contexto
    app.config["CADENA"] = os.getenv("CADENA", "")
    app.config["API_URL"] = os.getenv("API_URL", "")
    try:
        pagina_size = int(os.getenv("PAGINA_SIZE", "50"))
    except ValueError:
        pagina_size = 50
    app.config["PAGINA_SIZE"] = pagina_size if pagina_size > 0 else 50

    @app.template_filter("fecha_gmt3")
    def fecha_gmt3(valor):
        if not valor:
            return "—"
        try:
            fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return valor
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")

    @app.template_filter("numero")
    def numero(valor):
        return "—" if valor is None else format(valor, ",").replace(",", ".")

    @app.template_filter("usd")
    def usd(valor):
        return "—" if valor is None else "USD " + format(valor, ".8f")

    @app.get("/")
    @app.get("/index.html")
    def inicio():
        return render_template("index.html", max_contexto=app.config["MAX_CONTEXTO"])

    @app.post("/chat")
    def chat():
        datos = request.get_json(silent=True)
        mensaje = datos.get("mensaje") if isinstance(datos, dict) else None
        if not isinstance(mensaje, str) or not 1 <= len(mensaje.strip()) <= 10000:
            return jsonify(respuesta="Ocurrió un error."), 400
        contexto = datos.get("contexto", [])
        if (not isinstance(contexto, list) or len(contexto) > app.config["MAX_CONTEXTO"]
                or any(not isinstance(item, str) or not item.strip() or len(item) > 10000 for item in contexto)):
            return jsonify(respuesta="Ocurrió un error."), 400
        try:
            respuesta = consultar_chat(app.config["API_URL"], mensaje.strip(), contexto)
        except (ValueError, OSError, RuntimeError) as error:
            # No registrar URLs, cuerpos de respuesta ni valores de configuración.
            app.logger.error(
                "No se pudo consultar el chat de la API. Tipo: %s; HTTP: %s",
                type(error).__name__, getattr(error, "code", "no disponible"),
            )
            return jsonify(respuesta="Ocurrió un error."), 502
        return jsonify(respuesta=respuesta)

    @app.get("/costos")
    @app.get("/costos.html")
    def costos():

        filtros_activos = request.args.get("filtros") == "1"
        mostrar_jev = not filtros_activos or request.args.get("mostrar_jev") == "1"
        mostrar_openai = not filtros_activos or request.args.get("mostrar_openai") == "1"
        try:
            resultado, datos = solicitar_api(
                consultar_costos_api,
                pagina=request.args.get("pagina", default=1, type=int),
                pagina_size=app.config["PAGINA_SIZE"],
                mostrar_jev=mostrar_jev,
                mostrar_openai=mostrar_openai,
                campos=("registros", "costo_jev", "costo_openai", "tokens_jev", "tokens_openai", "total_registros", "pagina", "total_paginas", "desde", "hasta", "mostrar_jev", "mostrar_openai"),
            )
            if not resultado and datos.get("status_code") == 404:
                return render_template(
                    "costos.html", registros=[], pagina=1, error=None,
                    sin_informacion=True, mostrar_jev=mostrar_jev,
                    mostrar_openai=mostrar_openai,
                )
            if not resultado:
                raise ErrorConsultaApi
            if not isinstance(datos["registros"], list):
                raise ErrorConsultaApi
            campos_registro = {"id", "fecha_utc", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "costo_estimado_usd", "metodo", "herramientas"}
            if any(not isinstance(fila, dict) or not campos_registro.issubset(fila) for fila in datos["registros"]):
                raise ErrorConsultaApi
            if any(type(datos[campo]) is not int for campo in ("pagina", "total_paginas", "total_registros", "desde", "hasta", "tokens_jev", "tokens_openai")):
                raise ErrorConsultaApi
            if any(not isinstance(datos[campo], (int, float)) for campo in ("costo_jev", "costo_openai")):
                raise ErrorConsultaApi
        except ErrorConsultaApi:
            return render_template(
                "costos.html",
                registros=[],
                mostrar_jev=mostrar_jev, mostrar_openai=mostrar_openai,
                error="No se pudieron consultar los costos en la API.",
                error_modal="No se pudieron consultar los costos en la API. Intentá nuevamente.",
            ), 503
        return render_template("costos.html", error=None, **datos)

    @app.route("/umbral", methods=["GET", "POST"])
    @app.route("/umbral.html", methods=["GET", "POST"])
    def umbral():
        if "csrf_umbral" not in session:
            session["csrf_umbral"] = token_urlsafe(32)
        porcentaje = request.form.get("porcentaje", "") if request.method == "POST" else ""
        error = None
        codigo = 200
        if request.method == "POST":
            if not compare_digest(request.form.get("csrf_token", "").encode("utf-8"), session["csrf_umbral"].encode("utf-8")):
                error = "El formulario venció. Recargá la página e intentá nuevamente."
                codigo = 400
            else:
                try:
                    numero = Decimal(porcentaje.strip().replace(",", "."))
                    if not numero.is_finite() or not Decimal("0") <= numero <= Decimal("100"):
                        raise ValueError
                except (InvalidOperation, ValueError):
                    error = "Ingresá un porcentaje entre 0 y 100."
                    codigo = 400
                else:
                    try:
                        resultado, salida = solicitar_api(guardar_umbral_api, float(numero / Decimal("100")), campos=("id", "valor"))
                        if not resultado:
                            raise ErrorConsultaApi
                    except ErrorConsultaApi:
                        error = "No se pudo guardar el umbral en la API. Intentá nuevamente."
                        codigo = 503
                    else:
                        flash("Umbral guardado correctamente.", "exito")
                        return redirect(url_for("umbral"))
        if request.method == "GET":
            try:
                resultado, datos = solicitar_api(consultar_umbral_api, campos=("id", "valor"))
                if not resultado:
                    raise ErrorConsultaApi
                valor = Decimal(str(datos["valor"]))
                if not valor.is_finite() or not Decimal("0") <= valor <= Decimal("1"):
                    raise ValueError
                porcentaje = format(valor * Decimal("100"), "f")
                if "." in porcentaje:
                    porcentaje = porcentaje.rstrip("0").rstrip(".")
            except (InvalidOperation, ValueError, ErrorConsultaApi):
                error = "No se pudo consultar el umbral en la API. Intentá nuevamente."
                codigo = 503
        return render_template("umbral.html", porcentaje=porcentaje, error=error, error_modal=error if codigo == 503 else None), codigo

    @app.route("/mcps", methods=["GET", "POST"])
    @app.route("/mcps.html", methods=["GET", "POST"])
    def mcps():
        if "csrf_mcps" not in session:
            session["csrf_mcps"] = token_urlsafe(32)
        error = None
        codigo = 200
        if request.method == "POST":
            if not compare_digest(request.form.get("csrf_token", "").encode("utf-8"), session["csrf_mcps"].encode("utf-8")):
                error = "El formulario venció. Recargá la página e intentá nuevamente."
                codigo = 400
            else:
                try:
                    id_mcp = int(request.form.get("id_mcp", ""))
                    estado = request.form.get("habilitado", "")
                    if id_mcp < 1 or estado not in ("0", "1"):
                        raise ValueError
                except ValueError:
                    error = "El registro o el estado solicitado no es válido."
                    codigo = 400
                else:
                    try:
                        resultado, salida = solicitar_api(guardar_estado_mcp_api, id_mcp, int(estado), campos=("id", "nombre", "url", "habilitado"))
                        if not resultado:
                            raise ErrorConsultaApi
                    except ErrorConsultaApi:
                        error = "No se pudo actualizar el MCP en la API. Intentá nuevamente."
                        codigo = 503
                    else:
                        flash("MCP habilitado correctamente." if estado == "1" else "MCP deshabilitado correctamente.", "exito")
                        return redirect(url_for("mcps"))
        try:
            resultado, registros = solicitar_api(consultar_mcps_api, tipo=list, campos=("id", "nombre", "url", "habilitado"))
            if not resultado and registros.get("status_code") == 404:
                registros = []
            elif not resultado:
                raise ErrorConsultaApi
        except ErrorConsultaApi:
            registros = None
            error = "No se pudo consultar el catálogo MCP en la API. Intentá nuevamente."
            codigo = 503
        return render_template("mcps.html", registros=registros, error=error, error_modal=error if codigo == 503 else None), codigo

    @app.post("/mcps/agregar")
    def crear_mcp():
        nombre = request.form.get("nombre", "")
        url = request.form.get("url", "")
        token = session.get("csrf_mcps", "")
        if not token or not compare_digest(request.form.get("csrf_token", "").encode("utf-8"), token.encode("utf-8")):
            error = "El formulario venció. Recargá la página e intentá nuevamente."
            codigo = 400
        else:
            try:
                resultado, salida = solicitar_api(agregar_mcp_api, nombre, url, campos=("id", "nombre", "url", "habilitado"))
                if not resultado:
                    raise ErrorConsultaApi
            except ErrorConsultaApi:
                error = "No se pudo agregar el MCP en la API. Revisá los datos e intentá nuevamente."
                codigo = 503
            else:
                flash("MCP agregado como deshabilitado. Podés habilitarlo desde la tabla cuando lo necesites.", "exito")
                return redirect(url_for("mcps"))
        try:
            resultado, registros = solicitar_api(consultar_mcps_api, tipo=list, campos=("id", "nombre", "url", "habilitado"))
            if not resultado and registros.get("status_code") == 404:
                registros = []
            elif not resultado:
                raise ErrorConsultaApi
        except ErrorConsultaApi:
            registros = None
            error = "No se pudo consultar el catálogo MCP en la API. Intentá nuevamente."
            codigo = 503
        return render_template(
            "mcps.html", registros=registros, error=error,
            nuevo_nombre=nombre, nueva_url=url,
            error_modal=error if codigo == 503 else None,
        ), codigo

    @app.route("/mcps/<int:id_mcp>/borrar", methods=["GET", "POST"])
    def borrar_mcp(id_mcp):
        if "csrf_mcps" not in session:
            session["csrf_mcps"] = token_urlsafe(32)
        error = None
        codigo = 200
        registro = None
        if request.method == "POST":
            if not compare_digest(request.form.get("csrf_token", "").encode("utf-8"), session["csrf_mcps"].encode("utf-8")):
                error = "El formulario venció. Recargá la página e intentá nuevamente."
                codigo = 400
            else:
                try:
                    resultado, datos = solicitar_api(eliminar_mcp_api, id_mcp, campos=("id", "eliminado"))
                    if not resultado:
                        raise ErrorConsultaApi
                    if datos["eliminado"] is not True:
                        raise ErrorConsultaApi
                except ErrorConsultaApi:
                    error = "No se pudo borrar el MCP en la API. Intentá nuevamente."
                    codigo = 503
                else:
                    flash("MCP eliminado del catálogo.", "exito")
                    return redirect(url_for("mcps"))
        try:
            resultado, registro = solicitar_api(consultar_mcp_api, id_mcp, campos=("id", "nombre", "url", "habilitado"))
            if not resultado:
                raise ErrorConsultaApi
        except ErrorConsultaApi:
            error = "No se pudo consultar el MCP en la API. Intentá nuevamente."
            codigo = 503
        return render_template("mcps_borrar.html", registro=registro, error=error, error_modal=error if codigo == 503 else None), codigo

    return app


if __name__ == "__main__":
    crear_app().run(host="127.0.0.1", port=8000)
