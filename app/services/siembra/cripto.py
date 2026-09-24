"""Generador de Crypto para el agente de siembra (sin LLM): la escalera del mes y
el rango de cierre de BTC, ETH y SOL, y la escalera de stablecoins. Es el mismo
formato de agente-mercados/generar-escaleras-cripto.py, pero los niveles ya no se
eligen a mano: salen del spot y de la volatilidad del día.

Mes objetivo: el mes en curso si le quedan 10 días o más; si no, el siguiente
(así la escalera de octubre se propone desde el 21-sep y la página de Crypto
nunca se queda sin escalera el día 1).

Priors: log-normal sin deriva con σ diaria = promedio de la vol realizada a 30 y
90 días (velas 1d de Binance; Kraken si Binance no responde, porque Railway está
en EUA). Stablecoins: log-normal con deriva y vol de 30 días de DefiLlama.
Peldaños con prior entre 10 y 90 (CRITERIOS §3), mínimo 4 por escalera.

Redacción obligatoria «¿X cerrará <mes> en US$N o más?» (stablecoins: «¿Las stablecoins
cerrarán <mes> en US$N mil millones o más?», para caber en 70 caracteres): la landing
de Crypto reconoce la escalera por ella (veredikt.md §5). Las escaleras resuelven
solas con `auto_resolucion`; los rangos (multi) se resuelven a mano.
"""
from __future__ import annotations

import calendar
import math
import statistics
from datetime import date, datetime, timedelta, timezone

from app.services.resolucion.fuentes import Http
from app.services.siembra.partidos import _yaml, ints_100
from seeds.schema import QUESTION_MAX, SchemaError, cargar_texto

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
PRIOR_MIN, PRIOR_MAX, MIN_PELDANOS, MAX_PELDANOS = 10, 90, 4, 6
MIN_OPCION = 3
DIAS_MIN_MES_EN_CURSO = 10

# subcategoría, nombre, símbolo Binance, par Kraken, índice CF, nombre del índice, slug
ACTIVOS = [
    ("Bitcoin", "Bitcoin", "BTCUSDT", "XBTUSD", "BRR", "CME CF Bitcoin Reference Rate (BRR)", "btc"),
    ("Ethereum", "Ethereum", "ETHUSDT", "ETHUSD", "ETHUSD_RR", "CME CF Ether-Dollar Reference Rate (ETHUSD_RR)", "eth"),
    ("Solana", "Solana", "SOLUSDT", "SOLUSD", "SOLUSD_RR", "CME CF Solana-Dollar Reference Rate (SOLUSD_RR)", "sol"),
]
CAIDA = ("Si la fuente oficial deja de publicar el dato o cambia su metodología antes de la resolución, "
         "el equipo de VEREDIKT usará la fuente sustituta más cercana y lo anunciará en los comentarios del mercado antes de resolver.")


def _larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def _N(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def mes_objetivo(hoy: date) -> date:
    """Último día del mes cuya escalera toca proponer."""
    ultimo = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
    if (ultimo - hoy).days >= DIAS_MIN_MES_EN_CURSO:
        return ultimo
    sig = ultimo + timedelta(days=1)
    return date(sig.year, sig.month, calendar.monthrange(sig.year, sig.month)[1])


def paso_redondo(x: float) -> int:
    """El menor 1/2/2.5/5 × 10^k (entero, ≥ 1) que sea ≥ x."""
    e = 0
    while True:
        for k in (1, 2, 2.5, 5):
            v = k * 10 ** e
            if v >= x and v == int(v):
                return int(v)
        e += 1


def elegir_niveles(centro: float, sd_abs: float, prior) -> list[tuple[int, int]]:
    """[(nivel, prior %)] redondos alrededor de `centro`, con prior entre PRIOR_MIN y
    PRIOR_MAX, los MAX_PELDANOS más cercanos a 50 en orden ascendente. Si con medio
    σ de paso no salen MIN_PELDANOS, prueba con un paso más chico."""
    for div in (2, 4):
        paso = paso_redondo(sd_abs / div)
        base = round(centro / paso) * paso
        cands = [(k, round(prior(k) * 100)) for k in (base + i * paso for i in range(-8, 9)) if k > 0]
        ok = sorted((c for c in cands if PRIOR_MIN <= c[1] <= PRIOR_MAX), key=lambda c: abs(c[1] - 50))[:MAX_PELDANOS]
        if len(ok) >= MIN_PELDANOS:
            return sorted(ok)
    return []


def rangos(cortes: list[int], prior) -> tuple[list[int], list[int]]:
    """% de apertura de cada rango (suman 100). Una punta por debajo de MIN_OPCION se
    junta con el rango de al lado (CRITERIOS §3: ninguna opción listada abre en < 3)."""
    while True:
        cdf = [1 - prior(k) for k in cortes]
        pcts = ints_100([cdf[0]] + [cdf[i] - cdf[i - 1] for i in range(1, len(cdf))] + [1 - cdf[-1]])
        if len(cortes) > 1 and pcts[0] < MIN_OPCION:
            cortes = cortes[1:]
        elif len(cortes) > 1 and pcts[-1] < MIN_OPCION:
            cortes = cortes[:-1]
        else:
            return cortes, pcts


def _velas(http: Http, sym: str, kraken: str) -> tuple[list[float], str]:
    """Cierres diarios (≈91 días) y la fuente usada."""
    try:
        k = http.get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&limit=91")
        if isinstance(k, list) and len(k) > 31:
            return [float(x[4]) for x in k], "Binance"
    except RuntimeError:
        pass
    d = http.get(f"https://api.kraken.com/0/public/OHLC?pair={kraken}&interval=1440")
    serie = next(v for c, v in (d.get("result") or {}).items() if c != "last")
    return [float(x[4]) for x in serie[-91:]], "Kraken"


def _vol(cl: list[float]) -> float:
    r = [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]
    return (statistics.stdev(r) + statistics.stdev(r[-30:])) / 2


def _valida(doc: dict) -> str | None:
    try:
        specs, _ = cargar_texto(_yaml([doc]))
    except SchemaError as e:
        return "; ".join(e.errores)[:300]
    if len(specs[0].question) > QUESTION_MAX:
        return f"pregunta de {len(specs[0].question)} caracteres (máximo {QUESTION_MAX})"
    return None


def _prop(doc: dict, grupo: str, precio: str, nota: str, url: str) -> dict:
    return {"doc": doc, "grupo": grupo, "titulo": doc["question"], "cuando": doc["ends_at"],
            "precio": precio, "nota": nota, "revisar": [], "url": url}


def _activo(http: Http, activo: tuple, ultimo: date, hoy: date, T: float, excluir: set[str]) -> tuple[list[dict], list[dict]]:
    sub, nombre, sym, kraken, ind, ind_nombre, slug = activo
    mes, suf = MESES[ultimo.month - 1], f"{ABREV[ultimo.month - 1]}{ultimo.year % 100}"
    ends = f"{ultimo.isoformat()}T23:59:00Z"
    escalera_ya = any(i.startswith(f"{slug}-cierre-{suf}-") for i in excluir)
    rango_id = f"{slug}-rango-cierre-{suf}"
    if escalera_ya and rango_id in excluir:
        return [], []
    cl, fuente = _velas(http, sym, kraken)
    S, sig = cl[-1], _vol(cl)
    sd = sig * math.sqrt(T)
    prior = lambda K: _N(math.log(S / K) / sd)
    nota = f"spot US${_fmt(S)} ({fuente}), σ diaria {sig * 100:.1f}%"
    ctx = (f"{nombre} cotizaba cerca de US${_fmt(S)} en {fuente} el {_larga(hoy)}, con una volatilidad "
           f"diaria realizada de alrededor de {sig * 100:.1f}% en los últimos meses. La {ind_nombre} de CF Benchmarks es la "
           "referencia diaria de las 4:00 p.m. hora de Londres con la que se liquidan los futuros del CME; Binance publica "
           "velas diarias en UTC.")
    props, desc = [], []
    niveles = elegir_niveles(S, S * sd, prior)
    if not escalera_ya:
        if not niveles:
            desc.append({"grupo": sub, "titulo": f"Escalera de {mes} de {nombre}",
                         "motivo": f"no salen {MIN_PELDANOS} peldaños con prior entre {PRIOR_MIN} y {PRIOR_MAX}"})
        for K, p in niveles:
            doc = {
                "tipo": "binario", "id": f"{slug}-cierre-{suf}-{K}",
                "question": f"¿{nombre} cerrará {mes} en US${_fmt(K)} o más?",
                "description": f"Escalera de {mes} de {nombre}: resuelve con la referencia diaria de CF Benchmarks del {_larga(ultimo)}.",
                "category": "CRYPTO", "subcategory": sub,
                "resolution_criteria": (f"Resuelve SÍ si la {ind_nombre} del {_larga(ultimo)}, publicada por CF Benchmarks, es igual o "
                                        f"mayor a US${_fmt(K)}. Respaldo: cierre diario UTC de {sym} en Binance del {_larga(ultimo)}."),
                "resolution_source_url": "https://www.cfbenchmarks.com",
                "rules_cuerpo": (f"Resuelve SÍ si el valor de la {ind_nombre} del {_larga(ultimo)} (la referencia diaria de las 4:00 p.m. "
                                 f"hora de Londres), publicado por CF Benchmarks, es igual o mayor a US${_fmt(K)}. Se usa esa referencia "
                                 f"y no el precio de un exchange en particular; el cierre diario UTC de {sym} en Binance sirve como fuente "
                                 f"de respaldo y de verificación. {CAIDA}"),
                "context": ctx + " Esta escalera abre varios niveles con el mismo cierre para que cada quien elija su umbral.",
                "ends_at": ends, "initial_yes_price": p,
                "trending": slug == "btc" and K == niveles[len(niveles) // 2][0],
                "auto_resolucion": {"fuente": "cripto_cierre", "params": {"indice": ind, "symbol": sym},
                                    "fecha": ultimo.isoformat(), "op": ">=", "valor": K},
            }
            motivo = _valida(doc)
            if motivo:
                desc.append({"grupo": sub, "titulo": doc["question"], "motivo": motivo})
            else:
                props.append(_prop(doc, sub, f"{p}%", nota, "https://www.cfbenchmarks.com"))
    if rango_id not in excluir and niveles:
        paso = 2 * (niveles[1][0] - niveles[0][0])
        base = round(S / paso) * paso
        cortes, pcts = rangos([c for c in (base + (i - 2) * paso for i in range(5)) if c > 0], prior)
        labels = ([f"Menos de US${_fmt(cortes[0])}"] + [f"US${_fmt(cortes[i - 1])} a US${_fmt(cortes[i])}" for i in range(1, len(cortes))]
                  + [f"US${_fmt(cortes[-1])} o más"])
        keys = ([f"r_menos_{cortes[0]}"] + [f"r_{cortes[i - 1]}_{cortes[i]}" for i in range(1, len(cortes))] + [f"r_{cortes[-1]}_mas"])
        doc = {
            "tipo": "multi", "id": rango_id,
            "question": f"¿En qué rango cerrará {nombre} {mes} de {ultimo.year}?",
            "description": f"Rangos excluyentes para la referencia diaria de CF Benchmarks del {_larga(ultimo)}. Solo una opción resuelve Sí.",
            "category": "CRYPTO", "subcategory": sub,
            "resolution_criteria": (f"Gana el rango que contenga el valor de la {ind_nombre} del {_larga(ultimo)} publicado por CF Benchmarks. "
                                    f"Respaldo: cierre diario UTC de {sym} en Binance del mismo día."),
            "resolution_source_url": "https://www.cfbenchmarks.com",
            "rules": (f"Resuelve al rango que contenga el valor de la {ind_nombre} del {_larga(ultimo)} (la referencia diaria de las 4:00 p.m. "
                      "hora de Londres), publicado por CF Benchmarks. Cada rango incluye su límite inferior y excluye el superior: un valor "
                      "exactamente igual a un límite cae en el rango que empieza en ese número. Los rangos cubren todos los valores posibles, "
                      f"así que siempre gana uno. El cierre diario UTC de {sym} en Binance sirve como fuente de respaldo. {CAIDA} El mercado "
                      f"cierra el {_larga(ultimo)}. Gana exactamente un rango: cada acción del ganador paga 1 PT y las demás valen 0."),
            "context": ctx, "ends_at": ends,
            "outcomes": [{"key": k, "label": l, "pct": v} for k, l, v in zip(keys, labels, pcts)],
        }
        motivo = _valida(doc)
        if motivo:
            desc.append({"grupo": sub, "titulo": doc["question"], "motivo": motivo})
        else:
            props.append(_prop(doc, sub, "/".join(map(str, pcts)), nota, "https://www.cfbenchmarks.com"))
    return props, desc


def _stablecoins(http: Http, ultimo: date, hoy: date, excluir: set[str]) -> tuple[list[dict], list[dict]]:
    """Escalera de la capitalización de stablecoins. DefiLlama fecha cada dato a las
    00:00 UTC: el cierre del último día es el dato del día siguiente (desde = fecha)."""
    mes, suf = MESES[ultimo.month - 1], f"{ABREV[ultimo.month - 1]}{ultimo.year % 100}"
    if any(i.startswith(f"stablecoins-cierre-{suf}-") for i in excluir):
        return [], []
    sig_dia = ultimo + timedelta(days=1)
    d = http.get("https://stablecoins.llama.fi/stablecoincharts/all")
    serie = [x["totalCirculatingUSD"]["peggedUSD"] for x in d]
    L = serie[-1]
    r = [math.log(serie[i] / serie[i - 1]) for i in range(len(serie) - 30, len(serie))]
    mu, sd = statistics.mean(r), statistics.stdev(r)
    dias = (sig_dia - datetime.fromtimestamp(int(d[-1]["date"]), timezone.utc).date()).days
    m, s = math.log(L) + mu * dias, sd * math.sqrt(dias)
    prior = lambda K: 1 - _N((math.log(K * 1e9) - m) / s)   # K en miles de millones
    niveles = elegir_niveles(math.exp(m) / 1e9, math.exp(m) / 1e9 * s, prior)
    if not niveles:
        return [], [{"grupo": "Stablecoins", "titulo": f"Escalera de {mes} de stablecoins",
                     "motivo": f"no salen {MIN_PELDANOS} peldaños con prior entre {PRIOR_MIN} y {PRIOR_MAX}"}]
    nota = f"DefiLlama US${L / 1e9:,.1f} mil millones, deriva {mu * 100:.2f}%/día"
    props, desc = [], []
    for K, p in niveles:
        doc = {
            "tipo": "binario", "id": f"stablecoins-cierre-{suf}-{K}b",
            "question": f"¿Las stablecoins cerrarán {mes} en US${_fmt(K)} mil millones o más?",
            "description": f"Escalera de {mes} de stablecoins: resuelve con el dato de DefiLlama del cierre del {_larga(ultimo)}.",
            "category": "CRYPTO", "subcategory": "Stablecoins",
            "resolution_criteria": (f"Resuelve SÍ si la capitalización total en circulación de stablecoins vinculadas al dólar que publica "
                                    f"DefiLlama con fecha del {_larga(sig_dia)} (foto de las 00:00 UTC, es decir, el cierre del {ultimo.day} "
                                    f"de {mes}) es igual o mayor a US${_fmt(K)} mil millones. Respaldo: suma de la categoría stablecoins de CoinGecko."),
            "resolution_source_url": "https://defillama.com/stablecoins",
            "rules_cuerpo": (f"Resuelve SÍ si el total en circulación de stablecoins vinculadas al dólar (serie totalCirculatingUSD.peggedUSD "
                             f"de DefiLlama) con fecha del {_larga(sig_dia)} es igual o mayor a US${_fmt(K)} mil millones. DefiLlama fecha cada "
                             f"dato a las 00:00 UTC, así que el dato del {sig_dia.day} de {MESES[sig_dia.month - 1]} refleja el cierre del "
                             f"{ultimo.day} de {mes}. La suma de la categoría stablecoins de CoinGecko sirve como fuente de respaldo y de "
                             f"verificación. {CAIDA}"),
            "context": (f"DefiLlama registraba alrededor de US${L / 1e9:,.1f} mil millones en stablecoins vinculadas al dólar el "
                        f"{_larga(hoy)}, frente a US${serie[-31] / 1e9:,.1f} mil millones un mes antes. La oferta de stablecoins crece "
                        "cuando entra dinero nuevo al ecosistema cripto y se contrae cuando sale, por eso se sigue como termómetro de "
                        "liquidez del mercado."),
            "ends_at": f"{ultimo.isoformat()}T23:59:00Z", "initial_yes_price": p, "trending": False,
            "auto_resolucion": {"fuente": "stablecoins_cap", "params": {"agg": "max"}, "desde": sig_dia.isoformat(),
                                "fecha": sig_dia.isoformat(), "op": ">=", "valor": K * 1_000_000_000},
        }
        motivo = _valida(doc)
        if motivo:
            desc.append({"grupo": "Stablecoins", "titulo": doc["question"], "motivo": motivo})
        else:
            props.append(_prop(doc, "Stablecoins", f"{p}%", nota, "https://defillama.com/stablecoins"))
    return props, desc


def armar_propuestas(http: Http, ahora: datetime, excluir: set[str], existentes: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Síncrono (urllib). `excluir` = ids vigentes o ya propuestos: una escalera o un
    rango que ya existe para el mes objetivo no se vuelve a proponer."""
    hoy = ahora.date()
    ultimo = mes_objetivo(hoy)
    fix = datetime(ultimo.year, ultimo.month, ultimo.day, 15, tzinfo=timezone.utc)
    T = (fix - ahora).total_seconds() / 86400
    props, desc = [], []
    for a in ACTIVOS:
        try:
            p, d = _activo(http, a, ultimo, hoy, T, excluir)
        except (RuntimeError, ValueError, KeyError, StopIteration, statistics.StatisticsError) as e:
            p, d = [], [{"grupo": a[0], "titulo": f"Escalera de {a[1]}", "motivo": f"sin precio: {e}"[:300]}]
        props += p
        desc += d
    try:
        p, d = _stablecoins(http, ultimo, hoy, excluir)
    except (RuntimeError, ValueError, KeyError, statistics.StatisticsError) as e:
        p, d = [], [{"grupo": "Stablecoins", "titulo": "Escalera de stablecoins", "motivo": f"sin DefiLlama: {e}"[:300]}]
    return props + p, desc + d
