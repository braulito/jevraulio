"""Comunicación del servidor Flask con el endpoint configurado en API_URL."""

import json
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


def consultar_chat(api_url: str, mensaje: str, contexto: list[str] | None = None) -> str:
    """Solo acepta HTTP 200, estado Ok y una respuesta de texto."""
    if not api_url or not api_url.strip():
        raise ValueError("API_URL no está configurada.")

    # Migrar la URL anterior sin modificar la configuración local del usuario.
    partes = urlsplit(api_url.strip())
    ruta = partes.path.rstrip("/")
    if ruta.endswith("/chat"):
        ruta += "/jev"
    elif not ruta:
        ruta = "/chat/jev"
    api_url = urlunsplit((partes.scheme, partes.netloc, ruta, partes.query, partes.fragment))

    datos_peticion = {"mensaje": mensaje}
    if contexto:
        datos_peticion["contexto"] = contexto
    peticion = Request(
        api_url.strip(),
        data=json.dumps(datos_peticion).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(peticion, timeout=200) as respuesta:
        if respuesta.status != 200:
            raise RuntimeError("Respuesta HTTP no válida.")
        datos = json.load(respuesta)

    if (
        not isinstance(datos, dict)
        or not isinstance(datos.get("estado"), str)
        or datos["estado"].strip().upper() != "OK"
        or not isinstance(datos.get("respuesta"), str)
    ):
        raise RuntimeError("Respuesta de API no válida.")
    return datos["respuesta"]
