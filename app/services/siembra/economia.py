"""Generador de Economía para el agente de siembra (sin LLM): decisión de Banxico,
decisión de la Fed e inflación mensual.

Decisiones de tasa (Mark, 24-sep-2026): un multi por reunión, «¿Qué hará Banxico
con la tasa el 5 de noviembre?», opciones Baja / Sin cambio / Sube, como
Polymarket. Se resuelven a mano (las recetas solo aplican a binarios).
  - Fed: fecha del calendario oficial (federalreserve.gov); precio de Polymarket
    contrastado con Kalshi (> 15 puntos o una sola fuente → «revisar»).
  - Banxico: fecha y precio de Polymarket, única fuente de apuestas → siempre
    «revisar: una sola fuente». Sin evento en Polymarket, no se propone.
  Ventana: la decisión cae entre 7 días (plazo mínimo de un multi, CRITERIOS §5) y
  60 días después. Ninguna opción abre en menos de 3%.

Inflación (Mark): binario «¿La inflación anual de octubre será menor a 3.25%?» con
el umbral en el último dato publicado (SIE de Banxico, SP30578) y prior 50 como
estimación, porque no hay mercado de apuestas de la inflación mexicana. Cierra el
día 6 del mes siguiente a las 23:59 CDMX, antes de que el INEGI publique (lo hace
entre el 7 y el 10), y se resuelve con la receta `inflacion_anual`.

No se repite nada: una decisión o un mes que ya tiene mercado vigente (con este
formato o con el binario «sin cambio» de antes) se salta.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone

from app.config import settings
from app.services.resolucion.fuentes import Http
from app.services.siembra.cripto import MESES, ABREV, _larga, _valida

VENTANA_MIN_D, VENTANA_MAX_D = 7, 60
MIN_OPCION = 3
UMBRAL_REVISAR = 15
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BANXICO_URL = ("https://www.banxico.org.mx/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria/"
               "anuncios-politica-monetaria-t.html")
INEGI_URL = "https://www.inegi.org.mx/temas/inpc/"
_MES_EN = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
OPCIONES = [("baja", "⬇️ Baja la tasa"), ("mantiene", "⏸️ Sin cambio"), ("sube", "⬆️ Sube la tasa")]


def _suf(d: date) -> str:
    return f"{ABREV[d.month - 1]}{d.year % 100}"


def pct_min(ps: list[float], minimo: int = MIN_OPCION) -> list[int]:
    """Enteros que suman 100 con cada opción ≥ `minimo` (CRITERIOS §3)."""
    t = sum(ps)
    raw = [max(minimo, p / t * 100) for p in ps]
    extra = sum(raw) - 100
    grandes = [i for i, v in enumerate(raw) if v > minimo]
    for i in grandes:  # lo que se le dio a las chicas se le quita a las grandes, en proporción
        raw[i] -= extra * (raw[i] - minimo) / sum(raw[j] - minimo for j in grandes)
    out = [int(v) for v in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[: 100 - sum(out)]:
        out[i] += 1
    return out


def _bucket(titulo: str) -> str | None:
    t = titulo.lower()
    if "no change" in t or "maintain" in t:
        return "mantiene"
    if "decrease" in t or "cut" in t:
        return "baja"
    if "increase" in t or "hike" in t:
        return "sube"
    return None


def polymarket_decisiones(http: Http, banco: str) -> dict[date, dict]:
    """{fecha de la decisión: {probs: {baja, mantiene, sube}, url, volumen}} de los
    eventos abiertos «<banco> Decision in <Mes>?» de Polymarket (gamma API, sin llave).
    La fecha sale del endDate (el de la Fed viene a las 03:59Z del día siguiente)."""
    data = http.get(f"https://gamma-api.polymarket.com/public-search?q={urllib.parse.quote(banco + ' decision')}")
    out: dict[date, dict] = {}
    for e in data.get("events") or []:
        if e.get("closed") or not re.match(rf"^{re.escape(banco)} decision in \w+\??$", e.get("title", ""), re.I):
            continue
        dia = (datetime.fromisoformat(e["endDate"].replace("Z", "+00:00")) - timedelta(hours=6)).date()
        probs = {"baja": 0.0, "mantiene": 0.0, "sube": 0.0}
        for m in e.get("markets") or []:
            b = _bucket(m.get("groupItemTitle") or m.get("question") or "")
            precios = m.get("outcomePrices")
            if b and precios:
                probs[b] += float(json.loads(precios)[0] if isinstance(precios, str) else precios[0])
        if sum(probs.values()) > 0.5:
            out[dia] = {"probs": probs, "url": f"https://polymarket.com/event/{e.get('slug', '')}",
                        "volumen": float(e.get("volume") or 0)}
    return out


def kalshi_fed(http: Http, decision: date) -> dict | None:
    """Probabilidades de Kalshi (KXFEDDECISION-AAMES) de la reunión de ese mes;
    precio medio entre bid y ask (último precio si no hay libro)."""
    ticker = f"KXFEDDECISION-{decision:%y}{decision.strftime('%b').upper()}"
    try:
        data = http.get(f"https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker={ticker}")
    except RuntimeError:
        return None
    probs = {"baja": 0.0, "mantiene": 0.0, "sube": 0.0}
    for m in data.get("markets") or []:
        suf = m.get("ticker", "").rsplit("-", 1)[-1]
        b = "mantiene" if suf == "H0" else "baja" if suf.startswith("C") else "sube" if suf.startswith("H") else None
        bid, ask = m.get("yes_bid_dollars"), m.get("yes_ask_dollars")
        p = (float(bid) + float(ask)) / 2 if bid and ask and float(ask) > 0 else float(m.get("last_price_dollars") or 0)
        if b:
            probs[b] += p
    return probs if sum(probs.values()) > 0.5 else None


def fomc_fechas(http: Http) -> list[date]:
    """Segundo día de cada reunión del FOMC según el calendario oficial."""
    h = http.get_text(FED_URL)
    out: list[date] = []
    partes = re.split(r"(\d{4}) FOMC Meetings", h)
    for anio, seg in zip(partes[1::2], partes[2::2]):
        for mes, dias in re.findall(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<', seg, re.S):
            m = _MES_EN.get(mes.split("/")[-1].strip()[:3].lower())
            d = re.findall(r"\d+", dias)
            if m and d:
                out.append(date(int(anio), m, int(d[-1])))
    return sorted(set(out))


def banxico_oportuno(http: Http, serie: str) -> tuple[date, float] | None:
    """Último dato de una serie del SIE (SF61745 tasa objetivo, SP30578 inflación anual)."""
    if not settings.BANXICO_TOKEN:
        return None
    data = http.get(f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{serie}/datos/oportuno?token={settings.BANXICO_TOKEN}")
    x = ((((data.get("bmx") or {}).get("series") or [{}])[0].get("datos")) or [None])[0]
    if not x:
        return None
    return datetime.strptime(x["fecha"], "%d/%m/%Y").date(), float(x["dato"].replace(",", ""))


def _ya_tiene(excluir: set[str], prefijo: str, suf: str) -> bool:
    return any(i.startswith(prefijo) and suf in i for i in excluir)


def _decision_doc(banco: str, dia: date, pct: list[int], contexto: str) -> dict:
    fed = banco == "fed"
    nombre = "la Fed" if fed else "Banxico"
    quien = "el Comité Federal de Mercado Abierto (FOMC) de la Reserva Federal" if fed else "la Junta de Gobierno del Banco de México"
    tasa = "el rango objetivo de la tasa de fondos federales" if fed else "el objetivo para la Tasa de Interés Interbancaria a un día"
    hora = "a las 2:00 p.m. hora del Este de EUA" if fed else "a las 13:00 (hora de la Ciudad de México)"
    fuente = FED_URL if fed else BANXICO_URL
    return {
        "tipo": "multi", "id": f"{banco}-decision-{_suf(dia)}",
        "question": f"¿Qué hará {nombre} con la tasa el {dia.day} de {MESES[dia.month - 1]}?",
        "description": f"Decisión de política monetaria de {nombre} del {_larga(dia)}: baja, sin cambio o sube respecto a la tasa vigente el día anterior.",
        "category": "ECONOMIA", "subcategory": "Fed / tasas EE.UU." if fed else "Tasas Banxico",
        "resolution_criteria": (f"Gana «Baja» si {quien} reduce {tasa} en su anuncio del {_larga(dia)}, «Sube» si lo aumenta y "
                                "«Sin cambio» si lo deja igual, sin importar la magnitud del movimiento."),
        "resolution_source_url": fuente,
        "rules": (f"Se compara {tasa} vigente el día anterior con el que anuncie {quien} el {_larga(dia)} {hora}. "
                  "Gana «Baja la tasa» si el anuncio la reduce, «Sube la tasa» si la aumenta y «Sin cambio» si la deja en el mismo "
                  "nivel, sin importar la magnitud. Una decisión extraordinaria antes de esa fecha no resuelve el mercado: solo cuenta "
                  f"el anuncio programado del {_larga(dia)}. Si el anuncio se pospone o se cancela, el mercado se cancela y las "
                  f"posiciones se reembolsan. Fuente: el comunicado oficial en {urllib.parse.urlparse(fuente).netloc}. El mercado cierra "
                  "antes del anuncio. Gana exactamente una opción: cada acción de la ganadora paga 1 PT y las demás valen 0."),
        "context": contexto,
        "ends_at": f"{dia.isoformat()}T{'17:55' if fed else '18:30'}:00Z",
        "outcomes": [{"key": k, "label": l, "pct": v} for (k, l), v in zip(OPCIONES, pct)],
    }


def _txt_probs(p: dict) -> str:
    return f"{p['baja'] * 100:.0f}% baja, {p['mantiene'] * 100:.0f}% sin cambio y {p['sube'] * 100:.0f}% sube"


def _prop(doc: dict, grupo: str, precio: str, nota: str, url: str, revisar: list[str]) -> dict:
    return {"doc": doc, "grupo": grupo, "titulo": doc["question"], "cuando": doc["ends_at"],
            "precio": precio, "nota": nota, "revisar": revisar, "url": url}


def _decisiones(http: Http, hoy: date, excluir: set[str]) -> tuple[list[dict], list[dict]]:
    props, desc = [], []
    en_ventana = lambda d: VENTANA_MIN_D <= (d - hoy).days <= VENTANA_MAX_D

    # Fed: fecha oficial, Polymarket + Kalshi
    poly_fed = polymarket_decisiones(http, "Fed")
    fed_tasa = None
    for dia in [d for d in fomc_fechas(http) if en_ventana(d)]:
        if _ya_tiene(excluir, "fed-", _suf(dia)):
            continue
        poly = next((v for k, v in poly_fed.items() if abs((k - dia).days) <= 1), None)
        kal = kalshi_fed(http, dia)
        if not poly and not kal:
            desc.append({"grupo": "Fed / tasas EE.UU.", "titulo": f"Decisión de la Fed del {_larga(dia)}",
                         "motivo": "ni Polymarket ni Kalshi tienen precio"})
            continue
        base, revisar = (poly or {}).get("probs") or kal, []
        if poly and kal:
            dif = max(abs(poly["probs"][k] - kal[k]) for k in kal) * 100
            if dif > UMBRAL_REVISAR:
                revisar.append(f"Polymarket y Kalshi difieren {dif:.0f} puntos")
        else:
            revisar.append(f"una sola fuente ({'Polymarket' if poly else 'Kalshi'})")
        if fed_tasa is None:
            fed_tasa = _fed_rango(http)
        ctx = (f"{fed_tasa} Las apuestas de Polymarket" if fed_tasa else "Las apuestas de Polymarket") + \
              (f" daban {_txt_probs(poly['probs'])}" if poly else " no tenían precio") + \
              (f" y las de Kalshi {_txt_probs(kal)}" if kal else "") + \
              f" para la reunión del {_larga(dia)}, según sus precios del {_larga(hoy)}. La Reserva Federal anuncia a las 2:00 p.m. hora del Este."
        doc = _decision_doc("fed", dia, pct_min([base[k] for k, _ in OPCIONES]), ctx)
        nota = "Kalshi " + "/".join(f"{kal[k] * 100:.0f}" for k, _ in OPCIONES) if kal and poly else ""
        motivo = _valida(doc)
        if motivo:
            desc.append({"grupo": doc["subcategory"], "titulo": doc["question"], "motivo": motivo})
        else:
            props.append(_prop(doc, doc["subcategory"], "/".join(str(o["pct"]) for o in doc["outcomes"]),
                               nota or "Polymarket", (poly or {}).get("url") or FED_URL, revisar))

    # Banxico: fecha y precio de Polymarket (una sola fuente → revisar)
    tasa = banxico_oportuno(http, "SF61745")
    for dia, poly in sorted(polymarket_decisiones(http, "Bank of Mexico").items()):
        if not en_ventana(dia) or _ya_tiene(excluir, "banxico-", _suf(dia)):
            continue
        ctx = ((f"La tasa objetivo de Banxico estaba en {tasa[1]:.2f}% al {_larga(tasa[0])} (SIE, serie SF61745). " if tasa else "")
               + f"Las apuestas de Polymarket daban {_txt_probs(poly['probs'])} para la decisión del {_larga(dia)}, según sus precios "
               f"del {_larga(hoy)}. Banxico anuncia sus decisiones a las 13:00, hora de la Ciudad de México.")
        doc = _decision_doc("banxico", dia, pct_min([poly["probs"][k] for k, _ in OPCIONES]), ctx)
        motivo = _valida(doc)
        if motivo:
            desc.append({"grupo": doc["subcategory"], "titulo": doc["question"], "motivo": motivo})
        else:
            props.append(_prop(doc, doc["subcategory"], "/".join(str(o["pct"]) for o in doc["outcomes"]),
                               f"Polymarket (volumen US${poly['volumen']:,.0f})", poly["url"], ["una sola fuente (Polymarket)"]))
    return props, desc


def _fed_rango(http: Http) -> str | None:
    """«La Fed tenía su rango en 3.75–4.00 %…» con el último dato de FRED DFEDTARU (sin llave)."""
    try:
        filas = [l.split(",") for l in http.get_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU").splitlines()[1:]]
        f, v = next((f, float(v)) for f, v in reversed(filas) if v not in (".", ""))
        return f"La Fed tenía su rango objetivo en {v - 0.25:.2f}–{v:.2f}% al {_larga(date.fromisoformat(f))} (FRED, DFEDTARU)."
    except (RuntimeError, StopIteration, ValueError):
        return None


def _inflacion(http: Http, ahora: datetime, excluir: set[str]) -> tuple[list[dict], list[dict]]:
    ultimo = banxico_oportuno(http, "SP30578")
    if not ultimo:
        return [], [{"grupo": "Inflación (INPC)", "titulo": "Inflación mensual", "motivo": "sin el último dato (falta BANXICO_TOKEN o el SIE no respondió)"}]
    fecha_dato, valor = ultimo
    mes = date(ahora.year, ahora.month, 1)
    for _ in range(3):  # el primer mes cuyo mercado aún no existe y cierra entre 3 y 45 días
        sig = (mes + timedelta(days=32)).replace(day=1)
        cierre = datetime(sig.year, sig.month, 7, 5, 59, tzinfo=timezone.utc)   # día 6, 23:59 CDMX
        dias = (cierre - ahora).days
        if 3 <= dias <= 45 and not _ya_tiene(excluir, "inflacion-", _suf(mes)):
            break
        mes = sig
    else:
        return [], []
    umbral = round(valor * 20) / 20   # múltiplo de 0.05 más cercano al último dato
    nombre_mes, mes_pub = MESES[mes.month - 1], MESES[sig.month - 1]
    u = f"{umbral:.2f}"
    doc = {
        "tipo": "binario", "id": f"inflacion-{_suf(mes)}-menor-{int(round(umbral * 100))}",
        "question": f"¿La inflación anual de {nombre_mes} será menor a {u}%?",
        "description": (f"Resuelve SÍ si la inflación general anual de {nombre_mes} de {mes.year} que publique el INEGI en {mes_pub} "
                        f"es menor a {u} %; NO si es {u} % o mayor."),
        "category": "ECONOMIA", "subcategory": "Inflación (INPC)",
        "resolution_criteria": (f"Cifra de «inflación general anual» del boletín del INPC de {nombre_mes} de {mes.year} (INEGI), con dos "
                                f"decimales. Menor a {u} = SÍ; {u} o mayor = NO."),
        "resolution_source_url": INEGI_URL,
        "rules_cuerpo": (f"Cuenta únicamente la variación anual del Índice Nacional de Precios al Consumidor (INPC) general del mes completo "
                         f"de {nombre_mes} de {mes.year}, tal como la publique el INEGI en su boletín de {mes_pub}, con dos decimales. Resuelve "
                         f"SÍ si esa cifra es menor a {u} %. Resuelve NO si es {u} % o mayor. No cuentan la inflación quincenal, la subyacente "
                         f"ni revisiones posteriores a la primera publicación. Si el INEGI no publica la cifra a más tardar el 25 de {mes_pub} "
                         f"de {sig.year}, el mercado se cancela y se reembolsa."),
        "rules_como": (f"Cómo se resuelve: con el boletín del INPC de {nombre_mes} de {mes.year} del INEGI (inegi.org.mx) y la serie SP30578 "
                       "(variación anual del INPC) del SIE de Banxico, que republica la misma cifra."),
        "context": (f"La última inflación general anual publicada fue de {valor:.2f} % (dato de {MESES[fecha_dato.month - 1]} de "
                    f"{fecha_dato.year}; INEGI, republicado en el SIE de Banxico, serie SP30578). Este mercado pregunta si la de "
                    f"{nombre_mes} quedará por debajo de {u} %. El INEGI suele publicar el dato mensual entre el 7 y el 10 del mes "
                    f"siguiente; el mercado cierra antes, el 6 de {mes_pub}."),
        "ends_at": cierre.strftime("%Y-%m-%dT%H:%M:%SZ"), "initial_yes_price": 50, "trending": False,
        "auto_resolucion": {"fuente": "inflacion_anual", "params": {"periodo": f"{mes:%Y-%m}"}, "op": "<", "valor": umbral},
    }
    motivo = _valida(doc)
    if motivo:
        return [], [{"grupo": "Inflación (INPC)", "titulo": doc["question"], "motivo": motivo}]
    return [_prop(doc, "Inflación (INPC)", "50%", f"estimación: umbral en el último dato ({valor:.2f}%)", INEGI_URL, [])], []


def armar_propuestas(http: Http, ahora: datetime, excluir: set[str], existentes: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Síncrono (urllib). Cada bloque que truena sale en descartes y no tumba al otro."""
    props, desc = [], []
    for nombre, fn in (("Tasas", lambda: _decisiones(http, ahora.date(), excluir)),
                       ("Inflación (INPC)", lambda: _inflacion(http, ahora, excluir))):
        try:
            p, d = fn()
        except (RuntimeError, ValueError, KeyError, TypeError) as e:
            p, d = [], [{"grupo": nombre, "titulo": "(bloque completo)", "motivo": f"falló: {e}"[:300]}]
        props += p
        desc += d
    return props, desc
