"""Identidad del sujeto de un accesorio de jugador (columna markets.sujeto).

Un mercado de jugador (touchdown / pases de TD / fantasy en la NFL; titular /
gol en fútbol) guarda quién es el jugador sin ambigüedad:

  {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "posicion": "QB",
   "alcance": "partido", "ids": {"espn": "3918298", "cbs": "2181054"}}

El resolvedor elige el partido por `equipo` + `rival` y ubica al jugador por id
en cada fuente, nunca por nombre (caso Josh Allen / Josh Hines-Allen, Semana 1
de 2026). Los ids se buscan con red al sembrar (`identidad.py`,
`sembrar-mercados.py identificar`); aquí solo se valida la forma.

Puro (stdlib vía cruce/fuentes, sin app.config ni BD): lo importan
seeds/schema.py (`validar` sin SECRET_KEY), el PATCH admin, POST /api/markets y
validar.py.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import cruce
from .fuentes import LIGAS, UEFA_COMPETICION, deporte

CLAVES = ("jugador", "equipo", "rival", "posicion", "alcance", "ids")
FUENTES_ID = ("espn", "cbs", "uefa", "tsdb")
# "partido": un solo juego (el que se elige por equipo + rival); "temporada":
# acumulado de temporada, siempre se resuelve a mano.
ALCANCES = ("partido", "temporada")
_RE_ID = re.compile(r"^\d+$")
# host de la fuente de una entrada del plan → clave en `ids` / `sujeto_confirmado`
_HOSTS_FUENTE = {"espn.com": "espn", "cbssports.com": "cbs", "uefa.com": "uefa", "thesportsdb.com": "tsdb"}


def IDS_REQUERIDOS(liga: str | None) -> set[str]:  # noqa: N802  (nombre del plan: tabla por liga)
    """Ids obligatorios por liga: NFL ESPN + CBS (las dos fuentes de props);
    fútbol ESPN, más UEFA en sus competencias. TSDB nunca es obligatorio (no
    trae ids en alineaciones: solo confirma presencias por nombre)."""
    if not liga:
        return set()
    if deporte(liga) == "nfl":
        return {"espn", "cbs"}
    req = {"espn"}
    if liga in UEFA_COMPETICION:
        req.add("uefa")
    return req


# Sujeto gramatical que no es un jugador: "¿Se anotará un gol…?", "¿El América
# marcará…?", "¿Alguien anotará…?". Sin "lo" (Lo Celso) ni "de" (De Bruyne).
_RE_NO_JUGADOR = re.compile(
    r"^(?:se|el|la|los|las|un|una|unos|unas|ambos|ambas|alg[uú]n\w*|alguien|nadie|ning[uú]n\w*|"
    r"qui[eé]n\w*|cu[aá]l\w*|cualquier\w*|otro|otra)\b", re.I)


def _no_es_jugador(nombre: str, equipos: list[str]) -> bool:
    """El sujeto que extrajo parse_titular/parse_gol es un pronombre, artículo o
    cuantificador, o uno de los equipos de la pregunta (accesorio de equipo o de
    evento): no exige sujeto y el job lo escala como "sin regla mecánica"."""
    n = (nombre or "").strip()
    return not n or bool(_RE_NO_JUGADOR.match(n)) \
        or any(cruce.similitud(n, t) >= cruce.UMBRAL for t in equipos or [])


def spec_de_pregunta(question: str | None, liga: str | None) -> dict | None:
    """Spec del accesorio según los MISMOS parsers que usa el resolvedor para esa
    liga (plan.py): NFL → parse_prop_nfl; fútbol → parse_titular y luego
    parse_gol, descartando sujetos que no son jugadores (_no_es_jugador).
    {'tipo': 'td'|'pases_td'|'fantasy'|'titular'|'gol', 'jugador', 'umbral'?,
    'equipos'?, 'club'?, 'rival'?}. `club`/`rival` solo cuando la pregunta fija
    la orientación ("titular con X ante Y", "gol ante Y")."""
    if not liga or liga not in LIGAS:
        return None
    q = question or ""
    m = {"question": q}
    if deporte(liga) == "nfl":
        prop = cruce.parse_prop_nfl(m)
        return dict(prop) if prop else None
    tit = cruce.parse_titular(m)
    if tit and _no_es_jugador(tit["jugador"], tit["equipos"]):
        return None
    if tit:
        spec = {"tipo": "titular", **tit}
        if re.search(r"ser[aá] titular\s+con\s+", q, re.I) and len(tit["equipos"]) == 2:
            spec["club"], spec["rival"] = tit["equipos"]
        return spec
    gol = cruce.parse_gol(m)
    if gol and not _no_es_jugador(gol["jugador"], gol["equipos"]):
        spec = {"tipo": "gol", **gol}
        m2 = re.search(r"\b(ante|contra|frente a|vs\.?)\s+", q, re.I)
        if m2 and m2.group(1).lower() in ("ante", "contra", "frente a") and len(gol["equipos"]) == 1:
            spec["rival"] = gol["equipos"][0]
        return spec
    return None


def requiere_sujeto(category, tipo: str | None, liga: str | None, question: str | None) -> dict | None:
    """Spec si el mercado es un accesorio de jugador que el job resolvería solo;
    None si no. Fail-closed: basta con que la subcategoría esté en LIGAS y la
    pregunta la reconozca el parser de esa liga, sin mirar la categoría (el
    plan agrupa por subcategoría). `category` acepta NOMBRE o value del enum
    y no excluye nada; `tipo` acepta 'binario'/'binary' (None cuenta como
    binario). Los multi no llevan sujeto: el resolvedor no los trata como props."""
    del category  # firma estable para los llamadores; ver docstring
    if str(tipo or "binary").strip().lower() not in ("binary", "binario"):
        return None
    return spec_de_pregunta(question, liga)


def spec_de_mercado(m: dict) -> dict | None:
    """requiere_sujeto sobre un mercado en formato API (`mercado_a_dict`) o YAML."""
    return requiere_sujeto(m.get("category"), m.get("market_type") or m.get("tipo"),
                           m.get("subcategory"), m.get("question"))


def _id_valido(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return v >= 0
    return isinstance(v, str) and bool(_RE_ID.match(v.strip()))


def _texto(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validar_sujeto(spec: dict | None, sujeto, liga: str | None) -> list[str]:
    """Errores de forma del sujeto contra la pregunta (sin red). Vacío = válido."""
    if spec is None:
        return ["la pregunta no es un accesorio de jugador con resolución automática "
                "(touchdown / pases de TD / fantasy / titular / gol en una liga de resolucion/fuentes.py:LIGAS)"]
    if not isinstance(sujeto, dict):
        return ["sujeto debe ser un mapa {jugador, equipo, rival, posicion, alcance, ids}"]
    errs: list[str] = []
    extra = sorted(set(sujeto) - set(CLAVES))
    if extra:
        errs.append(f"claves desconocidas en sujeto: {', '.join(map(str, extra))}")
    faltan = [k for k in CLAVES if k not in sujeto]
    if faltan:
        errs.append(f"faltan claves en sujeto: {', '.join(faltan)}")

    alcance = sujeto.get("alcance")
    if "alcance" in sujeto and alcance not in ALCANCES:
        errs.append(f"alcance '{alcance}' inválido (partido | temporada)")
    obligatorios = ["jugador", "equipo", "posicion"] + ([] if alcance == "temporada" else ["rival"])
    for k in obligatorios:
        if k in sujeto and not _texto(sujeto.get(k)):
            errs.append(f"'{k}' vacío o no es texto")
    if alcance == "temporada" and sujeto.get("rival") not in (None, "") and not _texto(sujeto.get("rival")):
        errs.append("'rival' no es texto")

    jugador, equipo, rival = sujeto.get("jugador"), sujeto.get("equipo"), sujeto.get("rival")
    if _texto(jugador) and cruce.normalizar(jugador) != cruce.normalizar(spec["jugador"]):
        errs.append(f"jugador '{jugador}' no coincide con el de la pregunta '{spec['jugador']}' (debe ser idéntico)")

    if _texto(equipo) and _texto(rival) and cruce.similitud(equipo, rival) >= cruce.UMBRAL:
        errs.append(f"equipo '{equipo}' y rival '{rival}' parecen el mismo club")
    if _texto(equipo) and spec.get("club") and cruce.similitud(spec["club"], equipo) < cruce.UMBRAL:
        errs.append(f"la pregunta dice que juega con '{spec['club']}' pero sujeto.equipo es '{equipo}'")
    if _texto(rival) and spec.get("rival") and cruce.similitud(spec["rival"], rival) < cruce.UMBRAL:
        errs.append(f"la pregunta nombra al rival '{spec['rival']}' pero sujeto.rival es '{rival}'")
    lados = [x for x in (equipo, rival) if _texto(x)]
    equipos_q = spec.get("equipos") or []
    for t in equipos_q:
        if lados and max(cruce.similitud(t, x) for x in lados) < cruce.UMBRAL:
            errs.append(f"'{t}' (de la pregunta) no es ni sujeto.equipo ni sujeto.rival")
    if len(equipos_q) == 2 and _texto(equipo) and _texto(rival):
        a, b = equipos_q
        directo = min(cruce.similitud(a, equipo), cruce.similitud(b, rival))
        cruzado = min(cruce.similitud(a, rival), cruce.similitud(b, equipo))
        if max(directo, cruzado) < cruce.UMBRAL:
            errs.append(f"los equipos de la pregunta ({a} / {b}) no son {{equipo, rival}} ({equipo} / {rival})")

    ids = sujeto.get("ids")
    if "ids" in sujeto:
        if not isinstance(ids, dict):
            errs.append("ids debe ser un mapa {espn, cbs, uefa?, tsdb?}")
            ids = {}
        else:
            desconocidas = sorted(set(map(str, ids)) - set(FUENTES_ID))
            if desconocidas:
                errs.append(f"fuentes desconocidas en ids: {', '.join(desconocidas)} (válidas: {', '.join(FUENTES_ID)})")
            for k, v in ids.items():
                if v in (None, ""):
                    continue
                if not _id_valido(v):
                    errs.append(f"ids.{k} '{v}' no es un id numérico")
        for k in sorted(IDS_REQUERIDOS(liga)):
            if ids.get(k) in (None, ""):
                errs.append(f"falta ids.{k} (obligatorio en {liga}): llénalo con `sembrar-mercados.py identificar`")

    if spec.get("tipo") == "pases_td" and _texto(sujeto.get("posicion")) \
            and sujeto["posicion"].strip().upper() != "QB":
        errs.append(f"pases de TD exige posicion QB (sujeto.posicion es '{sujeto['posicion']}')")
    return errs


def normalizar_sujeto(sujeto: dict) -> dict:
    """Forma canónica para guardar: claves en orden, textos sin espacios de más,
    posición en mayúsculas, ids como string (vacíos fuera)."""
    out: dict = {}
    for k in CLAVES:
        if k not in sujeto:
            continue
        v = sujeto[k]
        if k == "ids":
            out[k] = {str(f): str(i).strip() for f, i in (v or {}).items() if i not in (None, "")} \
                if isinstance(v, dict) else v
        elif k == "posicion" and isinstance(v, str):
            out[k] = v.strip().upper()
        else:
            out[k] = v.strip() if isinstance(v, str) else v
    for k, v in sujeto.items():
        out.setdefault(k, v)  # claves desconocidas: validar_sujeto ya las rechaza
    return out


# ── defensa en profundidad: identidad confirmada en una entrada del plan ─────

def _clave_de_host(url: str) -> str | None:
    try:
        h = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return None
    for dominio, clave in _HOSTS_FUENTE.items():
        if h == dominio or h.endswith("." + dominio):
            return clave
    return None


def _es_su_equipo(nombre, suj: dict) -> bool:
    """`nombre` es sujeto.equipo (≥ UMBRAL) y se parece más a él que al rival:
    un sujeto_confirmado con el equipo y el rival cruzados no pasa."""
    n = str(nombre or "")
    if not n.strip():
        return False
    s_eq = cruce.similitud(n, suj["equipo"])
    s_riv = cruce.similitud(n, suj["rival"]) if _texto(suj.get("rival")) else 0.0
    return s_eq >= cruce.UMBRAL and s_eq > s_riv


def errores_identidad(detalle: dict, entrada: dict) -> list[str]:
    """Errores de identidad de una entrada del plan contra el mercado (formato
    API). Aplica solo a accesorios de jugador (`spec_de_mercado`):
    - el mercado debe tener `sujeto` válido;
    - la entrada debe traer `sujeto_confirmado` con el equipo del sujeto (y el
      mismo jugador si lo nombra; fuera de CANCELAR es obligatorio);
    - CANCELAR: basta el equipo (el partido se identificó por equipo);
    - si no, fuente_1/fuente_2 incluyen cada fuente de IDS_REQUERIDOS(liga)
      (NFL ESPN + CBS; UEFA ESPN + UEFA; resto ESPN): TheSportsDB y `manual`
      solo acompañan a los ids obligatorios;
    - y por cada fuente: espn/cbs/uefa exigen `sujeto_confirmado[clave].id`
      igual a `sujeto.ids[clave]`, el mismo equipo y (sanity check) un nombre
      compatible; thesportsdb, nombre idéntico y equipo; un host fuera del mapa
      exige `manual {equipo, nota}`.
    Lo llama validar.validar_entrada: protege check-plan, proponer_plan y
    aplicar_plan, también sobre planes guardados antes de existir el sujeto.
    """
    spec = spec_de_mercado(detalle)
    if spec is None:
        return []
    suj = detalle.get("sujeto")
    if not suj:
        return ["accesorio de jugador sin sujeto en el mercado: cargar el sujeto (agent-resolver.py sujetos) antes de resolver"]
    liga = detalle.get("subcategory")
    errs = [f"sujeto del mercado inválido: {x}" for x in validar_sujeto(spec, suj, liga)]
    if errs:
        return errs

    sc = entrada.get("sujeto_confirmado")
    if not isinstance(sc, dict):
        return ["mercado con sujeto: la entrada no trae sujeto_confirmado (identidad por fuente)"]
    cancelar = str(entrada.get("veredicto") or "").strip() == "CANCELAR"
    if not _es_su_equipo(sc.get("equipo"), suj):
        errs.append(f"sujeto_confirmado.equipo '{sc.get('equipo')}' ≠ sujeto.equipo '{suj['equipo']}'")
    if (not cancelar or _texto(sc.get("jugador"))) \
            and cruce.normalizar(str(sc.get("jugador") or "")) != cruce.normalizar(suj["jugador"]):
        errs.append(f"sujeto_confirmado.jugador '{sc.get('jugador')}' ≠ sujeto.jugador '{suj['jugador']}'")
    if cancelar:
        return errs

    ids = suj.get("ids") or {}
    # Las fuentes con id obligatorio de la liga tienen que estar entre las dos
    # de la entrada: TheSportsDB (por nombre) y `manual` solo acompañan, nunca
    # sustituyen un id obligatorio (NFL: ESPN + CBS; UEFA: ESPN + UEFA).
    claves = {_clave_de_host(str(entrada.get(c) or "")) for c in ("fuente_1", "fuente_2")}
    for k in sorted(IDS_REQUERIDOS(liga) - claves):
        errs.append(f"{liga} exige confirmar la identidad por id en {k}: ninguna fuente es de {k} "
                    "(TheSportsDB o una fuente manual no sustituyen un id obligatorio)")
    for campo in ("fuente_1", "fuente_2"):
        url = str(entrada.get(campo) or "")
        clave = _clave_de_host(url)
        if clave is None:
            manual = sc.get("manual")
            if not isinstance(manual, dict) or not _texto(manual.get("nota")) \
                    or not _es_su_equipo(manual.get("equipo"), suj):
                errs.append(f"{campo} ({url or 'vacía'}) no es ESPN/CBS/UEFA/TheSportsDB: "
                            "sujeto_confirmado.manual {equipo, nota} obligatorio")
            continue
        fila = sc.get(clave)
        if not isinstance(fila, dict):
            errs.append(f"{campo} es de {clave} pero sujeto_confirmado no trae '{clave}'")
            continue
        if not _es_su_equipo(fila.get("equipo"), suj):
            errs.append(f"sujeto_confirmado.{clave}.equipo '{fila.get('equipo')}' ≠ sujeto.equipo '{suj['equipo']}'")
        if clave == "tsdb":
            if cruce.normalizar(str(fila.get("nombre") or "")) != cruce.normalizar(suj["jugador"]):
                errs.append(f"sujeto_confirmado.tsdb.nombre '{fila.get('nombre')}' ≠ '{suj['jugador']}'")
            continue
        esperado = ids.get(clave)
        if not esperado:
            errs.append(f"el sujeto no tiene ids.{clave}: no se puede confirmar la identidad en {clave}")
            continue
        if str(fila.get("id") or "").strip() != str(esperado).strip():
            errs.append(f"sujeto_confirmado.{clave}.id '{fila.get('id')}' ≠ sujeto.ids.{clave} '{esperado}'")
        nombre = str(fila.get("nombre") or "")
        # sanity check junto al id (nunca en su lugar): mismo criterio que localizar_jugador
        if nombre and not (cruce._persona_coincide(suj["jugador"], nombre) or cruce.normalizar(nombre) == cruce.normalizar(suj["jugador"])):
            errs.append(f"sujeto_confirmado.{clave}.nombre '{nombre}' no es {suj['jugador']}")
    return errs


def texto_identidad(sc) -> str:
    """Identidad confirmada en una línea (correo, página de aprobación, CLI):
    'Josh Allen · Buffalo Bills · BUF@HOU · ESPN 3918298 · CBS 2181054'.
    Cadena vacía si la entrada no trae `sujeto_confirmado`."""
    if not isinstance(sc, dict) or not (sc.get("jugador") or sc.get("equipo")):
        return ""
    partes = [str(sc.get("jugador") or "?"), str(sc.get("equipo") or "?")]
    if sc.get("partido"):
        partes.append(str(sc["partido"]))
    for clave, nombre in (("espn", "ESPN"), ("cbs", "CBS"), ("uefa", "UEFA")):
        fila = sc.get(clave)
        if isinstance(fila, dict) and fila.get("id"):
            partes.append(f"{nombre} {fila['id']}")
    if isinstance(sc.get("tsdb"), dict):
        partes.append("TheSportsDB por nombre exacto")
    manual = sc.get("manual")
    if isinstance(manual, dict) and manual.get("nota"):
        partes.append(f"manual: {manual['nota']}")
    if len(partes) == 2 + bool(sc.get("partido")):
        partes.append("sin id confirmado en ninguna fuente")
    return " · ".join(partes)
