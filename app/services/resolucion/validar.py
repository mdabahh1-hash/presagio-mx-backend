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


# Segunda fuente admitida para mercados NO deportivos (decisión de Mark,
# 12-sep-2026: confiable y una sola, sin tabla por tema). Hosts exactos (sin
# www) o sufijos de dominio oficial. Deportes usa sus propias fuentes.
FUENTES_CONFIABLES_HOSTS = {
    # agencias y medios internacionales
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "bbc.com", "bbc.co.uk", "theguardian.com",
    "nytimes.com", "wsj.com", "afp.com", "elpais.com",
    # medios mexicanos
    "eluniversal.com.mx", "reforma.com", "milenio.com", "elfinanciero.com.mx", "eleconomista.com.mx",
    "expansion.mx", "animalpolitico.com", "proceso.com.mx", "aristeguinoticias.com",
    # datos
    "coinmarketcap.com", "coingecko.com", "defillama.com", "tradingview.com", "investing.com",
    "finance.yahoo.com", "nhc.noaa.gov", "fred.stlouisfed.org", "cfbenchmarks.com", "binance.com",
    "kraken.com", "federalregister.gov", "en.wikipedia.org", "es.wikipedia.org",
    # deportes (las usa el job mecánico; también valen como segunda fuente)
    "espn.com", "thesportsdb.com", "skysports.com", "cbssports.com", "nfl.com", "uefa.com", "fifa.com",
    "mlssoccer.com", "ligamx.net", "premierleague.com", "laliga.com", "bundesliga.com", "formula1.com",
}
FUENTES_CONFIABLES_SUFIJOS = (
    ".gob.mx", ".gov", ".gov.uk", ".gouv.fr", ".gov.br", ".gov.il", ".govt.nz", ".gc.ca", ".go.jp",
    ".europa.eu", ".un.org", ".nato.int", ".banxico.org.mx", ".inegi.org.mx", ".ine.mx", ".iecm.mx",
    ".jus.br", ".val.se", ".cvk.lv", ".cik.bg", ".elections.ma", ".bundeskanzler.de", ".elysee.fr",
    ".federalreserve.gov", ".ecb.europa.eu", ".uefa.com", ".fifa.com",
)


def es_fuente_confiable(url: str) -> bool:
    h = host(url)
    if not h:
        return False
    if h in FUENTES_CONFIABLES_HOSTS:
        return True
    return any(h == s.lstrip(".") or h.endswith(s) for s in FUENTES_CONFIABLES_SUFIJOS)


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

    # No deportivos: fuente 1 = la que citan las normas (si el mercado la trae);
    # fuente 2 = una de la lista cerrada de fuentes confiables.
    categoria = str(detalle.get("category") or "").lower()
    if categoria and categoria not in ("deportes", "sports"):
        oficial = host(str(detalle.get("resolution_source_url") or ""))
        if oficial and h1 and h1 != oficial and h2 != oficial:
            errores.append(f"ninguna fuente es la oficial de las normas ({oficial})")
        if h2 and not es_fuente_confiable(f2) and not (oficial and h2 == oficial):
            errores.append(f"fuente_2 ({h2}) no es una fuente confiable de la lista (validar.py:FUENTES_CONFIABLES)")

    if entrada.get("confianza") != "alta":
        errores.append(f"confianza '{entrada.get('confianza')}' (solo se ejecuta con 'alta')")

    if not str(entrada.get("resultado") or "").strip():
        errores.append("falta 'resultado' (hecho verificado)")
    return errores
