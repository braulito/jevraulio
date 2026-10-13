"""Clientes HTTP de la API SQL y de la administración de Jev."""

import json
import logging
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


SALIDA_JSON = Path(__file__).resolve().parent / "salida.json"
TOKENS_JSON = Path(__file__).resolve().parent / "tokens_count.json"
logger = logging.getLogger(__name__)
JEV_ADMIN_URL = os.getenv("JEV_ADMIN_URL", "").strip()
JEV_ADMIN_KEY = os.getenv("JEV_ADMIN_KEY", "").strip()
JEV_ADMIN_TOKENS = os.getenv("JEV_ADMIN_TOKENS", "").strip()
API_COSTOS_URL = os.getenv("API_COSTOS_URL", "").strip()
API_MCPS_URL = os.getenv("API_MCPS_URL", "").strip()
API_MCP_URL = os.getenv("API_MCP_URL", "").strip()
API_UMBRAL_URL = os.getenv("API_UMBRAL_URL", "").strip()


def llamar_api_json(
    url: str, metodo: str = "GET", *, datos: dict | None = None,
    parametros: dict | None = None, id_mcp: int | None = None,
) -> tuple[bool, dict | list]:
    """Lee resultado/salida de la API y conserva los códigos HTTP de error."""
    try:
        metodo = metodo.upper()
        if not url or metodo not in {"GET", "POST", "PATCH", "DELETE", "PUT"}:
            raise ValueError("URL o método no configurado.")
        if id_mcp is not None:
            if type(id_mcp) is not int or id_mcp < 1 or "{id_mcp}" not in url:
                raise ValueError("ID o plantilla de URL inválidos.")
            url = url.replace("{id_mcp}", str(id_mcp))
        partes = urlsplit(url)
        if partes.scheme not in {"http", "https"} or not partes.hostname or "{id_mcp}" in url:
            raise ValueError("URL inválida.")
        if parametros:
            consulta = dict(parse_qsl(partes.query, keep_blank_values=True))
            consulta.update({
                clave: str(valor).lower() if isinstance(valor, bool) else valor
                for clave, valor in parametros.items() if valor is not None
            })
            url = urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(consulta), partes.fragment))
        cabeceras = {"Accept": "application/json"}
        cuerpo = None
        if datos is not None:
            cuerpo = json.dumps(datos, ensure_ascii=False, allow_nan=False).encode("utf-8")
            cabeceras["Content-Type"] = "application/json"
        peticion = Request(url, data=cuerpo, headers=cabeceras, method=metodo)
        with urlopen(peticion, timeout=30) as respuesta:
            contenido = json.load(respuesta)
        if (not isinstance(contenido, dict) or type(contenido.get("resultado")) is not bool
                or not isinstance(contenido.get("salida"), (dict, list))):
            raise ValueError("Contrato JSON inválido.")
        if not contenido["resultado"]:
            salida = contenido["salida"]
            codigo = salida.get("status_code") if isinstance(salida, dict) else None
            if type(codigo) is not int or not 400 <= codigo <= 599:
                raise ValueError("Código de error inválido.")
            logger.error("La API rechazó la operación. Método: %s; HTTP: %s", metodo, codigo)
            return False, salida
        return True, contenido["salida"]
    except Exception as error:
        logger.error(
            "Falló la consulta JSON a la API. Método: %s; Tipo: %s; HTTP: %s",
            metodo, type(error).__name__, getattr(error, "code", "no disponible"),
        )
        codigo = getattr(error, "code", 502)
        if type(codigo) is not int or not 400 <= codigo <= 599:
            codigo = 502
        return False, {"status_code": codigo}


def consultar_costos_api(
    pagina: int = 1, pagina_size: int = 50,
    mostrar_jev: bool = True, mostrar_openai: bool = True,
) -> tuple[bool, dict | list]:
    return llamar_api_json(API_COSTOS_URL, parametros={
        "pagina": pagina, "pagina_size": pagina_size,
        "mostrar_jev": mostrar_jev, "mostrar_openai": mostrar_openai,
    })


def consultar_mcps_api() -> tuple[bool, dict | list]:
    return llamar_api_json(API_MCPS_URL)


def consultar_mcp_api(id_mcp: int) -> tuple[bool, dict | list]:
    return llamar_api_json(API_MCP_URL, id_mcp=id_mcp)


def agregar_mcp_api(nombre: str, url: str) -> tuple[bool, dict | list]:
    return llamar_api_json(API_MCPS_URL, "POST", datos={"nombre": nombre, "url": url})


def guardar_estado_mcp_api(id_mcp: int, habilitado: int) -> tuple[bool, dict | list]:
    return llamar_api_json(API_MCP_URL, "PATCH", id_mcp=id_mcp, datos={"habilitado": habilitado})


def eliminar_mcp_api(id_mcp: int) -> tuple[bool, dict | list]:
    return llamar_api_json(API_MCP_URL, "DELETE", id_mcp=id_mcp)


def consultar_umbral_api() -> tuple[bool, dict | list]:
    return llamar_api_json(API_UMBRAL_URL)


def guardar_umbral_api(valor: float) -> tuple[bool, dict | list]:
    """Envía el valor decimal almacenado (0.85), no el porcentaje (85)."""
    return llamar_api_json(API_UMBRAL_URL, "PUT", datos={"valor": valor})

def consultar_costos_jev() -> tuple[bool, dict]:
    """Consulta JEV_ADMIN_URL y guarda su respuesta JSON en pagina/salida.json."""
    try:
        
        if not JEV_ADMIN_URL or not JEV_ADMIN_KEY:
            raise ValueError("Falta configurar JEV_ADMIN_URL o JEV_ADMIN_KEY.")

        peticion = Request(
            JEV_ADMIN_URL,
            headers={"Authorization": f"Bearer {JEV_ADMIN_KEY}", "Accept": "application/json"},
            method="GET",
        )
        with urlopen(peticion, timeout=30) as respuesta:
            datos = json.load(respuesta)

        '''with SALIDA_JSON.open("w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)'''
        
        salida = {
            "credito_total": datos["data"][0]["limit"],
            "usados": datos["data"][0]["usage"],
            "restantes": datos["data"][0]["limit_remaining"]
        }
        
        return True, salida
    except Exception as error:
        # El texto de la excepción puede contener la URL o credenciales.
        logger.error("No se pudieron consultar o guardar los costos de Jev. Tipo: %s", type(error).__name__)
        return False, {}


def consultar_tokens_jev() -> tuple[bool, dict]:
    """Consulta JEV_ADMIN_TOKENS y guarda la respuesta en tokens_count.json."""
    try:
        if not JEV_ADMIN_TOKENS or not JEV_ADMIN_KEY:
            raise ValueError("Falta configurar JEV_ADMIN_TOKENS o JEV_ADMIN_KEY.")

        peticion = Request(
            JEV_ADMIN_TOKENS,
            headers={"Authorization": f"Bearer {JEV_ADMIN_KEY}", "Accept": "application/json"},
            method="GET",
        )
        with urlopen(peticion, timeout=30) as respuesta:
            datos = json.load(respuesta)

        with TOKENS_JSON.open("w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)

        return True, datos
    except Exception as error:
        logger.error("No se pudieron consultar o guardar los tokens de Jev. Tipo: %s", type(error).__name__)
        return False, {}
