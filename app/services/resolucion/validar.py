"""Validación de una entrada del plan contra el estado actual del mercado.
Función pura (sin red ni BD): la usan `agent-resolver.py check-plan` y la
aprobación del plan nocturno."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse


def host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def validar_entrada(entrada: dict, detalle: dict | None, ahora: datetime) -> list[str]:
    """Errores de una resolución del plan contra el detalle del mercado (formato
    del API pública: status, market_type, ends_at ISO, outcomes[{outcome_key}])."""
    errores: list[str] = []
    if detalle is None or detalle.get("http_error"):
        return ["mercado no encontrado en el API"]

    if detalle.get("status") != "pending_resolution":
        errores.append(f"status es '{detalle.get('status')}', no pending_resolution")

    ends_at = detalle.get("ends_at")
    if ends_at:
        try:
            if datetime.fromisoformat(str(ends_at).replace("Z", "+00:00")) > ahora:
                errores.append("el mercado todavía no cierra (ends_at en el futuro)")
        except ValueError:
            errores.append(f"ends_at ilegible: {ends_at}")

    veredicto = str(entrada.get("veredicto") or "").strip()
    if veredicto == "CANCELAR":
        pass  # válido para binarios y multi: reembolsa (aplazado fuera de ventana, inactivo, empate NFL)
    elif detalle.get("market_type") == "multi":
        keys = [o.get("outcome_key") for o in (detalle.get("outcomes") or [])]
        if veredicto not in keys:
            errores.append(f"veredicto '{veredicto}' no es un outcome_key válido ({', '.join(keys)})")
    else:
        if veredicto not in ("YES", "NO"):
            errores.append(f"veredicto '{veredicto}' debe ser YES o NO (binario)")

    f1, f2 = str(entrada.get("fuente_1") or ""), str(entrada.get("fuente_2") or "")
    h1, h2 = host(f1), host(f2)
    if not h1 or not f1.startswith("http"):
        errores.append("fuente_1 no es una URL")
    if not h2 or not f2.startswith("http"):
        errores.append("fuente_2 no es una URL")
    if h1 and h2 and h1 == h2:
        errores.append(f"las dos fuentes son del mismo host ({h1}); se requieren fuentes independientes")

    if entrada.get("confianza") != "alta":
        errores.append(f"confianza '{entrada.get('confianza')}' (solo se ejecuta con 'alta')")

    if not str(entrada.get("resultado") or "").strip():
        errores.append("falta 'resultado' (hecho verificado)")
    return errores
