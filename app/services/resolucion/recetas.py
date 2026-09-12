"""Recetas de resolución mecánica para mercados de dato publicado (no deportivos).

La inteligencia va en la siembra: cada mercado lleva en `auto_resolucion` qué
dato leer, de qué fuentes y contra qué umbral. El job ejecuta la receta sin LLM
y, como en deportes, solo propone con confianza alta cuando DOS fuentes de
dominios distintos dan el mismo veredicto; con una sola fuente el mercado sale
escalado con el valor leído como sugerencia.

Esquema de receta (JSON en markets.auto_resolucion):
  {"fuente": "<tipo>", "params": {...},
   "fecha": "AAAA-MM-DD",        # día del dato (cierre); default: día de ends_at
   "desde": "AAAA-MM-DD",        # ventanas ("toca"): inicio
   "op": ">=|>|<=|<|==",         # binarios: YES si  valor_leido op valor
   "valor": 100000}

Tipos (fuentes.py tiene los clientes; aquí los lectores):
  cripto_cierre       cfbenchmarks {indice} (BRR, ETHUSD_RR…) + Binance {symbol} 1d close
                      (sin indice: Binance + Kraken {pair})
  cripto_toca         extremo en ventana [desde, fecha]: cfbenchmarks diario (campo close)
                      o Binance high/low + Kraken {pair}; params {campo: close|high|low, agg: max|min}
  cripto_dominancia   CoinGecko global.market_cap_percentage.btc (una fuente → escalado)
  cripto_cap_total    CoinGecko global.total_market_cap.usd (una fuente → escalado)
  cripto_n_sobre_cap  CoinGecko coins/markets: nº de monedas con cap > params.umbral,
                      excluyendo params.excluir (stablecoins, envueltos) (una fuente → escalado)
  stablecoins_cap     DefiLlama stablecoincharts (máximo en ventana) + CoinGecko categoría stablecoins (actual)
  fed_tasa            FRED DFEDTARU (rango superior antes/después) + comunicado federalreserve.gov;
                      params {decision: "AAAA-MM-DD", tipo: mantiene|sube|baja}
  banxico_tasa        Banxico SIE SF61745 (token) — una fuente → escalado; params {decision, tipo}
  inegi_inflacion     INEGI INPC (token) + Banxico SIE inflación (token); params {periodo: "AAAA-MM",
                      indicador_inegi?, serie_banxico?}
  federal_register_eo Federal Register API (conteo, una fuente → escalado); params {presidente, desde, hasta}
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.config import settings

from .fuentes import Http

OPS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: abs(a - b) < 1e-9,
}
TIPOS = {
    "cripto_cierre", "cripto_toca", "cripto_dominancia", "cripto_cap_total", "cripto_n_sobre_cap",
    "stablecoins_cap", "fed_tasa", "banxico_tasa", "inegi_inflacion", "federal_register_eo",
}
_SIN_OP = {"fed_tasa", "banxico_tasa"}  # el veredicto es el tipo de movimiento, no un umbral
TOLERANCIA_PRECIO = 0.005  # 0.5 % entre fuentes para considerar el mismo dato


class RecetaError(Exception):
    """La fuente no pudo dar el dato (red, formato, token, fecha aún no publicada)."""


@dataclass
class Lectura:
    valor: float
    url: str
    fecha: str
    detalle: str
    fuente: str


# ── validación (pura, la usan el sembrador, el PATCH admin y el CLI) ─────────

def validar_receta(r: dict, market_type: str = "binary") -> list[str]:
    e: list[str] = []
    if not isinstance(r, dict):
        return ["auto_resolucion debe ser un objeto"]
    tipo = r.get("fuente")
    if tipo not in TIPOS:
        return [f"fuente desconocida '{tipo}' (válidas: {', '.join(sorted(TIPOS))})"]
    if market_type != "binary":
        e.append("las recetas solo aplican a mercados binarios")
    p = r.get("params") or {}
    if not isinstance(p, dict):
        e.append("params debe ser un objeto")
        p = {}
    for campo in ("fecha", "desde"):
        v = r.get(campo)
        if v is not None:
            try:
                date.fromisoformat(str(v))
            except ValueError:
                e.append(f"{campo} no es AAAA-MM-DD: {v}")
    if tipo in _SIN_OP:
        if p.get("tipo") not in ("mantiene", "sube", "baja"):
            e.append("params.tipo debe ser mantiene|sube|baja")
        if not p.get("decision"):
            e.append("params.decision (AAAA-MM-DD) es obligatorio")
    else:
        if r.get("op") not in OPS:
            e.append(f"op debe ser uno de {', '.join(OPS)}")
        try:
            float(r.get("valor"))
        except (TypeError, ValueError):
            e.append("valor debe ser numérico")
    if tipo == "cripto_cierre" and not (p.get("indice") or p.get("symbol")):
        e.append("cripto_cierre necesita params.indice (cfbenchmarks) o params.symbol (Binance)")
    if tipo == "cripto_toca":
        if p.get("campo") not in ("close", "high", "low"):
            e.append("cripto_toca: params.campo debe ser close|high|low")
        if p.get("agg") not in ("max", "min"):
            e.append("cripto_toca: params.agg debe ser max|min")
        if not r.get("desde"):
            e.append("cripto_toca necesita 'desde'")
        if not p.get("symbol"):
            e.append("cripto_toca necesita params.symbol (Binance)")
    if tipo == "cripto_n_sobre_cap" and not p.get("umbral"):
        e.append("cripto_n_sobre_cap necesita params.umbral")
    if tipo == "inegi_inflacion" and not p.get("periodo"):
        e.append("inegi_inflacion necesita params.periodo (AAAA-MM)")
    if tipo == "federal_register_eo" and not (p.get("presidente") and p.get("desde") and p.get("hasta")):
        e.append("federal_register_eo necesita params.presidente, desde y hasta")
    return e


# ── lectores ─────────────────────────────────────────────────────────────────

def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _fecha_ms(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def cf_serie(http: Http, indice: str) -> tuple[list[tuple[date, float]], str]:
    """Serie diaria de un índice de CF Benchmarks (valor de referencia por día UTC)."""
    url = f"https://www.cfbenchmarks.com/data/indices/{indice}"
    html = http.get_text(url)
    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        raise RecetaError(f"cfbenchmarks: sin buildId en {url}")
    data = http.get(f"https://www.cfbenchmarks.com/_next/data/{m.group(1)}/data/indices/{indice}.json")
    rrs = ((data.get("pageProps") or {}).get("indexConfig") or {}).get("rrs") or []
    serie = [(_fecha_ms(int(x["time"])), float(x["value"])) for x in rrs if x.get("value") not in (None, "")]
    if not serie:
        raise RecetaError(f"cfbenchmarks: serie vacía para {indice}")
    return sorted(serie), url


def leer_cf(http: Http, indice: str, dia: date) -> Lectura:
    serie, url = cf_serie(http, indice)
    for d, v in serie:
        if d == dia:
            return Lectura(v, url, dia.isoformat(), f"{indice} {dia:%d-%b-%Y}: {v:,.2f}", "cfbenchmarks")
    raise RecetaError(f"cfbenchmarks: {indice} no tiene dato del {dia} (último {serie[-1][0]})")


def leer_cf_ventana(http: Http, indice: str, desde: date, hasta: date, agg: str) -> Lectura:
    serie, url = cf_serie(http, indice)
    vals = [(d, v) for d, v in serie if desde <= d <= hasta]
    if not vals or vals[-1][0] < hasta:
        raise RecetaError(f"cfbenchmarks: {indice} sin serie completa hasta {hasta} (último {serie[-1][0]})")
    d, v = (max if agg == "max" else min)(vals, key=lambda t: t[1])
    return Lectura(v, url, d.isoformat(), f"{indice} {agg} entre {desde} y {hasta}: {v:,.2f} ({d})", "cfbenchmarks")


def binance_klines(http: Http, symbol: str, desde: date, hasta: date) -> tuple[list[dict], str]:
    """Velas diarias UTC [desde, hasta] de Binance (máx. 1000 por llamada)."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&startTime={_ms(desde)}&endTime={_ms(hasta) + 86_400_000 - 1}&limit=1000"
    rows = http.get(url)
    if not isinstance(rows, list):
        raise RecetaError(f"binance: respuesta inesperada {str(rows)[:120]}")
    velas = [{"fecha": _fecha_ms(int(r[0])), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]),
              "cerrada": int(r[6]) < int(datetime.now(timezone.utc).timestamp() * 1000)} for r in rows]
    return velas, f"https://www.binance.com/en/trade/{symbol}"


def leer_binance(http: Http, symbol: str, dia: date) -> Lectura:
    velas, url = binance_klines(http, symbol, dia, dia)
    for v in velas:
        if v["fecha"] == dia:
            if not v["cerrada"]:
                raise RecetaError(f"binance: la vela del {dia} aún no cierra")
            return Lectura(v["close"], url, dia.isoformat(), f"{symbol} cierre {dia:%d-%b-%Y} (UTC): {v['close']:,.2f}", "binance")
    raise RecetaError(f"binance: sin vela del {dia}")


def leer_binance_ventana(http: Http, symbol: str, desde: date, hasta: date, campo: str, agg: str) -> Lectura:
    velas, url = binance_klines(http, symbol, desde, hasta)
    velas = [v for v in velas if v["cerrada"]]
    if not velas or velas[-1]["fecha"] < hasta:
        raise RecetaError(f"binance: sin velas cerradas hasta {hasta}")
    v = (max if agg == "max" else min)(velas, key=lambda x: x[campo])
    return Lectura(v[campo], url, v["fecha"].isoformat(),
                   f"{symbol} {agg} de {campo} entre {desde} y {hasta}: {v[campo]:,.2f} ({v['fecha']})", "binance")


def kraken_ohlc(http: Http, pair: str, desde: date) -> tuple[list[dict], str]:
    since = int(datetime(desde.year, desde.month, desde.day, tzinfo=timezone.utc).timestamp())
    data = http.get(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1440&since={since - 1}")
    res = (data.get("result") or {})
    rows = next((v for k, v in res.items() if k != "last"), None)
    if not rows:
        raise RecetaError(f"kraken: sin OHLC para {pair}: {data.get('error')}")
    velas = [{"fecha": datetime.fromtimestamp(int(r[0]), tz=timezone.utc).date(), "open": float(r[1]), "high": float(r[2]),
              "low": float(r[3]), "close": float(r[4])} for r in rows]
    hoy = datetime.now(timezone.utc).date()
    return [v for v in velas if v["fecha"] < hoy], f"https://www.kraken.com/prices/{pair.lower()}"


def leer_kraken(http: Http, pair: str, dia: date) -> Lectura:
    velas, url = kraken_ohlc(http, pair, dia)
    for v in velas:
        if v["fecha"] == dia:
            return Lectura(v["close"], url, dia.isoformat(), f"{pair} cierre {dia:%d-%b-%Y} (UTC): {v['close']:,.2f}", "kraken")
    raise RecetaError(f"kraken: sin vela del {dia} (¿fuera de las 720 velas del API?)")


def leer_kraken_ventana(http: Http, pair: str, desde: date, hasta: date, campo: str, agg: str) -> Lectura:
    velas, url = kraken_ohlc(http, pair, desde)
    velas = [v for v in velas if desde <= v["fecha"] <= hasta]
    if not velas or velas[-1]["fecha"] < hasta or velas[0]["fecha"] > desde:
        raise RecetaError(f"kraken: ventana incompleta {desde}..{hasta} (tiene {len(velas)} velas)")
    v = (max if agg == "max" else min)(velas, key=lambda x: x[campo])
    return Lectura(v[campo], url, v["fecha"].isoformat(),
                   f"{pair} {agg} de {campo} entre {desde} y {hasta}: {v[campo]:,.2f} ({v['fecha']})", "kraken")


def leer_coingecko_global(http: Http, campo: str) -> Lectura:
    d = http.get("https://api.coingecko.com/api/v3/global").get("data") or {}
    hoy = datetime.now(timezone.utc).date().isoformat()
    if campo == "dominancia":
        v = float(d["market_cap_percentage"]["btc"])
        return Lectura(v, "https://www.coingecko.com/en/global-charts", hoy, f"dominancia BTC (CoinGecko, ahora): {v:.2f} %", "coingecko")
    v = float(d["total_market_cap"]["usd"])
    return Lectura(v, "https://www.coingecko.com/en/global-charts", hoy, f"capitalización total (CoinGecko, ahora): US${v/1e12:,.3f} T", "coingecko")


def leer_coingecko_n_sobre_cap(http: Http, umbral: float, excluir: list[str]) -> Lectura:
    rows = http.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1")
    ex = {s.lower() for s in excluir}
    top = [r for r in rows if (r.get("market_cap") or 0) > umbral and (r.get("symbol") or "").lower() not in ex]
    hoy = datetime.now(timezone.utc).date().isoformat()
    return Lectura(float(len(top)), "https://www.coingecko.com/", hoy,
                   f"{len(top)} monedas con cap > US${umbral/1e9:,.0f} B (CoinGecko, ahora): {', '.join(r['symbol'].upper() for r in top)}", "coingecko")


def leer_defillama_stablecoins(http: Http, desde: date | None, hasta: date, agg: str) -> Lectura:
    rows = http.get("https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=")
    if not isinstance(rows, list) or not rows:
        raise RecetaError("defillama: sin historial de stablecoins")
    serie = []
    for r in rows:
        try:
            d = datetime.fromtimestamp(int(r["date"]), tz=timezone.utc).date()
            serie.append((d, float((r.get("totalCirculatingUSD") or {}).get("peggedUSD") or 0)))
        except (KeyError, ValueError, TypeError):
            continue
    vals = [(d, v) for d, v in serie if (desde is None or d >= desde) and d <= hasta]
    if not vals:
        raise RecetaError(f"defillama: sin datos en la ventana hasta {hasta}")
    d, v = (max if agg == "max" else min)(vals, key=lambda t: t[1])
    return Lectura(v, "https://defillama.com/stablecoins", d.isoformat(),
                   f"stablecoins {agg} (DefiLlama) {desde or 'inicio'}..{hasta}: US${v/1e9:,.1f} B ({d})", "defillama")


def leer_coingecko_stablecoins(http: Http) -> Lectura:
    rows = http.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category=stablecoins&order=market_cap_desc&per_page=250&page=1")
    total = sum(float(r.get("market_cap") or 0) for r in rows)
    hoy = datetime.now(timezone.utc).date().isoformat()
    return Lectura(total, "https://www.coingecko.com/en/categories/stablecoins", hoy, f"stablecoins (CoinGecko, ahora): US${total/1e9:,.1f} B", "coingecko")


def leer_fred_movimiento(http: Http, decision: date) -> Lectura:
    """Movimiento del rango superior de fed funds (DFEDTARU) alrededor de la decisión:
    valor = nuevo − anterior (0 = mantiene)."""
    text = http.get_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU")
    rows = [(date.fromisoformat(r[0]), float(r[1])) for r in csv.reader(io.StringIO(text)) if r and r[0][:1].isdigit() and r[1] != "."]
    antes = [v for d, v in rows if d <= decision - timedelta(days=1)]
    despues = [v for d, v in rows if d >= decision + timedelta(days=2)]
    if not antes or not despues:
        raise RecetaError(f"FRED: DFEDTARU aún no cubre {decision + timedelta(days=2)}")
    return Lectura(despues[0] - antes[-1], "https://fred.stlouisfed.org/series/DFEDTARU", decision.isoformat(),
                   f"FRED DFEDTARU: {antes[-1]:.2f} % → {despues[0]:.2f} %", "fred")


def leer_fed_comunicado(http: Http, decision: date) -> Lectura:
    url = f"https://www.federalreserve.gov/newsevents/pressreleases/monetary{decision:%Y%m%d}a.htm"
    html = http.get_text(url)
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"decided to (maintain|lower|raise|reduce|increase) the target range", t, re.I)
    if not m:
        raise RecetaError(f"Fed: el comunicado {url} no tiene la frase 'decided to … the target range'")
    verbo = m.group(1).lower()
    mov = 0.0 if verbo == "maintain" else (-0.25 if verbo in ("lower", "reduce") else 0.25)
    rango = re.search(r"(\d[\d\-/]*\s*to\s*\d[\d\-/]*\s*percent)", t)
    return Lectura(mov, url, decision.isoformat(), f"comunicado FOMC {decision:%d-%b-%Y}: '{verbo} the target range' ({rango.group(1) if rango else 'rango no leído'})", "federalreserve")


def leer_banxico_movimiento(http: Http, decision: date) -> Lectura:
    if not settings.BANXICO_TOKEN:
        raise RecetaError("falta BANXICO_TOKEN")
    d1, d2 = decision - timedelta(days=10), decision + timedelta(days=10)
    data = http.get(f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF61745/datos/{d1}/{d2}?token={settings.BANXICO_TOKEN}")
    datos = (((data.get("bmx") or {}).get("series") or [{}])[0].get("datos")) or []
    serie = []
    for x in datos:
        try:
            serie.append((datetime.strptime(x["fecha"], "%d/%m/%Y").date(), float(x["dato"])))
        except (KeyError, ValueError):
            continue
    antes = [v for d, v in serie if d < decision]
    despues = [v for d, v in serie if d > decision]
    if not antes or not despues:
        raise RecetaError(f"Banxico SIE: SF61745 aún no cubre después del {decision}")
    return Lectura(despues[0] - antes[-1], "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?accion=consultarCuadro&idCuadro=CF101",
                   decision.isoformat(), f"tasa objetivo (SIE SF61745): {antes[-1]:.2f} % → {despues[0]:.2f} %", "banxico")


def leer_inegi_inflacion(http: Http, periodo: str, indicador: str) -> Lectura:
    if not settings.INEGI_TOKEN:
        raise RecetaError("falta INEGI_TOKEN")
    url = f"https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/{indicador}/es/0700/false/BIE/2.0/{settings.INEGI_TOKEN}?type=json"
    data = http.get(url)
    obs = ((data.get("Series") or [{}])[0].get("OBSERVATIONS")) or []
    por_periodo = {o.get("TIME_PERIOD"): o.get("OBS_VALUE") for o in obs}
    y, m = periodo.split("-")
    clave = f"{y}/{int(m):02d}"
    if clave not in por_periodo:
        raise RecetaError(f"INEGI: el indicador {indicador} aún no tiene {clave}")
    v = float(por_periodo[clave])
    return Lectura(v, "https://www.inegi.org.mx/temas/inpc/", periodo, f"INEGI indicador {indicador} {clave}: {v}", "inegi")


def leer_banxico_inflacion(http: Http, periodo: str, serie: str) -> Lectura:
    if not settings.BANXICO_TOKEN:
        raise RecetaError("falta BANXICO_TOKEN")
    data = http.get(f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{serie}/datos/oportuno?token={settings.BANXICO_TOKEN}")
    datos = (((data.get("bmx") or {}).get("series") or [{}])[0].get("datos")) or []
    for x in datos:
        f = x.get("fecha") or ""
        if f.endswith(f"{periodo[5:7]}/{periodo[:4]}") or f == periodo:
            return Lectura(float(x["dato"]), "https://www.banxico.org.mx/SieInternet/", periodo, f"Banxico SIE {serie} {f}: {x['dato']}", "banxico")
    raise RecetaError(f"Banxico SIE: {serie} aún no tiene {periodo}")


def leer_federal_register_eo(http: Http, presidente: str, desde: str, hasta: str) -> Lectura:
    url = ("https://www.federalregister.gov/api/v1/documents.json?conditions%5Bpresidential_document_type%5D=executive_order"
           f"&conditions%5Bpresident%5D={presidente}&conditions%5Bsigning_date%5D%5Bgte%5D={desde}&conditions%5Bsigning_date%5D%5Blte%5D={hasta}&per_page=1")
    n = int(http.get(url).get("count") or 0)
    return Lectura(float(n), f"https://www.federalregister.gov/presidential-documents/executive-orders/{presidente}/{desde[:4]}", hasta,
                   f"Federal Register: {n} órdenes ejecutivas firmadas entre {desde} y {hasta}", "federalregister")


# ── ejecutar una receta ──────────────────────────────────────────────────────

def _d(s: str | None, default: date) -> date:
    return date.fromisoformat(str(s)) if s else default


def fecha_dato(r: dict, ends_at: datetime) -> date:
    """Día en que el dato debe existir: `fecha` explícita; en recetas de tasa, dos
    días después de la decisión (FRED/SIE publican con rezago); si no, el día
    de cierre del mercado."""
    if r.get("fecha"):
        return date.fromisoformat(str(r["fecha"]))
    if r.get("fuente") in _SIN_OP and (r.get("params") or {}).get("decision"):
        return date.fromisoformat(str(r["params"]["decision"])) + timedelta(days=2)
    return ends_at.astimezone(timezone.utc).date()


def lecturas(r: dict, ends_at: datetime, http: Http) -> tuple[Lectura, Lectura | None, str]:
    """(primaria, secundaria|None, nota). Lanza RecetaError si la primaria falla."""
    tipo, p = r["fuente"], r.get("params") or {}
    fecha = _d(r.get("fecha"), ends_at.astimezone(timezone.utc).date())
    desde = _d(r.get("desde"), fecha)
    nota = ""
    if tipo == "cripto_cierre":
        if p.get("indice"):
            l1 = leer_cf(http, p["indice"], fecha)
            l2 = _try(lambda: leer_binance(http, p["symbol"], fecha)) if p.get("symbol") else None
        else:
            l1 = leer_binance(http, p["symbol"], fecha)
            l2 = _try(lambda: leer_kraken(http, p["pair"], fecha)) if p.get("pair") else None
    elif tipo == "cripto_toca":
        campo, agg = p["campo"], p["agg"]
        if p.get("indice") and campo == "close":
            l1 = leer_cf_ventana(http, p["indice"], desde, fecha, agg)
            l2 = _try(lambda: leer_binance_ventana(http, p["symbol"], desde, fecha, campo, agg))
        else:
            l1 = leer_binance_ventana(http, p["symbol"], desde, fecha, campo, agg)
            l2 = _try(lambda: leer_kraken_ventana(http, p["pair"], desde, fecha, campo, agg)) if p.get("pair") else None
    elif tipo in ("cripto_dominancia", "cripto_cap_total"):
        l1 = leer_coingecko_global(http, "dominancia" if tipo == "cripto_dominancia" else "cap_total")
        l2, nota = None, "CoinGecko no ofrece historial gratuito: valor actual, una sola fuente"
    elif tipo == "cripto_n_sobre_cap":
        l1 = leer_coingecko_n_sobre_cap(http, float(p["umbral"]), list(p.get("excluir") or []))
        l2, nota = None, "una sola fuente (CoinGecko, ahora)"
    elif tipo == "stablecoins_cap":
        l1 = leer_defillama_stablecoins(http, desde if r.get("desde") else None, fecha, p.get("agg", "max"))
        l2 = _try(lambda: leer_coingecko_stablecoins(http))
    elif tipo == "fed_tasa":
        dec = date.fromisoformat(p["decision"])
        l1 = leer_fred_movimiento(http, dec)
        l2 = _try(lambda: leer_fed_comunicado(http, dec))
    elif tipo == "banxico_tasa":
        l1 = leer_banxico_movimiento(http, date.fromisoformat(p["decision"]))
        l2, nota = None, "sin segunda fuente mecánica para Banxico (una sola fuente)"
    elif tipo == "inegi_inflacion":
        l1 = leer_inegi_inflacion(http, p["periodo"], str(p.get("indicador_inegi") or "910406"))
        l2 = _try(lambda: leer_banxico_inflacion(http, p["periodo"], str(p.get("serie_banxico") or "SP1")))
    elif tipo == "federal_register_eo":
        l1 = leer_federal_register_eo(http, p["presidente"], p["desde"], p["hasta"])
        l2, nota = None, "una sola fuente (Federal Register)"
    else:
        raise RecetaError(f"fuente desconocida {tipo}")
    return l1, l2, nota


def _try(fn):
    try:
        return fn()
    except (RecetaError, RuntimeError, KeyError, ValueError, TypeError) as e:
        return e


def veredicto(r: dict, l: Lectura) -> str:
    tipo, p = r["fuente"], r.get("params") or {}
    if tipo in _SIN_OP:
        mov = "mantiene" if abs(l.valor) < 1e-9 else ("sube" if l.valor > 0 else "baja")
        return "YES" if mov == p["tipo"] else "NO"
    return "YES" if OPS[r["op"]](l.valor, float(r["valor"])) else "NO"


def resolver_receta(m: dict, http: Http | None = None, ahora: datetime | None = None) -> dict:
    """Entrada de plan (confianza alta) o escalado, con la forma de los deportivos."""
    http = http or Http()
    ahora = ahora or datetime.now(timezone.utc)
    r = m.get("auto_resolucion") or {}
    base = {"id": m["id"], "pregunta": m.get("question"), "liga": m.get("subcategory") or m.get("category"),
            "volume": round(float(m.get("volume") or 0)), "num_trades": int(m.get("num_trades") or 0)}
    errs = validar_receta(r, m.get("market_type") or "binary")
    if errs:
        return {**base, "escalar": True, "razon": f"receta inválida: {'; '.join(errs)}"}
    ends_at = datetime.fromisoformat(str(m["ends_at"]).replace("Z", "+00:00"))
    fecha = fecha_dato(r, ends_at)
    if fecha > ahora.date():
        return {**base, "escalar": True, "razon": f"receta: el dato es del {fecha}, todavía no"}
    try:
        l1, l2, nota = lecturas(r, ends_at, http)
    except (RecetaError, RuntimeError, KeyError, ValueError, TypeError) as e:
        return {**base, "escalar": True, "razon": f"receta ({r['fuente']}): {e}"}
    v1 = veredicto(r, l1)
    umbral = "" if r["fuente"] in _SIN_OP else f" {r['op']} {float(r['valor']):,.2f}"
    if l2 is None or isinstance(l2, Exception):
        motivo = nota or f"la segunda fuente falló: {l2}"
        return {**base, "escalar": True, "veredicto_sugerido": v1, "fuente_1": l1.url,
                "razon": f"receta {r['fuente']} con una sola fuente ({motivo})",
                "resultado": f"{l1.detalle}{umbral} → {v1}"}
    v2 = veredicto(r, l2)
    if v1 != v2:
        return {**base, "escalar": True, "veredicto_sugerido": v1, "fuente_1": l1.url, "fuente_2": l2.url,
                "razon": f"las fuentes discrepan en el veredicto: {l1.fuente} {v1} ({l1.detalle}) vs {l2.fuente} {v2} ({l2.detalle})",
                "resultado": f"{l1.detalle} / {l2.detalle}"}
    return {**base, "veredicto": v1, "confianza": "alta", "fuente_1": l1.url, "fuente_2": l2.url,
            "resultado": f"{l1.detalle}; {l2.detalle}{umbral} → {v1}"}
