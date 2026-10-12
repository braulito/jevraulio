"""Registro del consumo de OpenRouter en SQLite."""

from funciones.bases_sqlite import guardar_billing

def registrar_uso_jev(datos: dict, modelo_solicitado: str) -> None:
    """Guardar las columnas de consumo sin imprimir el JSON del proveedor."""
    usage = datos.get("usage")
    if not isinstance(usage, dict):
        usage = None
    tokens = usage or {}
    entrada = tokens.get("input_tokens", tokens.get("prompt_tokens")) or 0
    salida = tokens.get("output_tokens", tokens.get("completion_tokens")) or 0
    detalles_entrada = tokens.get("input_tokens_details") or tokens.get("prompt_tokens_details") or {}
    detalles_salida = tokens.get("output_tokens_details") or tokens.get("completion_tokens_details") or {}
    total = tokens.get("total_tokens")
    if total is None:
        # Caché y razonamiento son detalles de entrada/salida, no tokens adicionales.
        total = entrada + salida
    guardar_billing(
        input_tokens=entrada,
        cached_tokens=detalles_entrada.get("cached_tokens") or 0,
        cache_write_tokens=detalles_entrada.get("cache_write_tokens") or 0,
        output_tokens=salida,
        reasoning_tokens=detalles_salida.get("reasoning_tokens") or 0,
        total_tokens=total,
        costo_estimado_usd=tokens.get("cost") or 0,
    )
