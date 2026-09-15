#!/usr/bin/env python3
"""CLI del agente de mercados: listar mercados por resolver, validar un plan de
resoluciones y ejecutarlo con bitácora.

Sin dependencias (urllib): correr SIEMPRE con ./venv/bin/python (el python3 del
sistema no tiene certificados SSL). El token se lee de .env.agent; si venció, se
regenera solo con generate-agent-token.py.

Comandos:
  ./venv/bin/python agent-resolver.py check-token
      Verifica el token de .env.agent (y lo renueva si hace falta).

  ./venv/bin/python agent-resolver.py list [--compact] [--out archivo.json] [--sin-deportes] [--categoria X]
      Lista TODOS los mercados en pending_resolution. Por default con detalle
      completo (criterio, fuente, normas, outcomes, auto_resolucion); --compact
      solo lo que necesita la investigación. --sin-deportes para la skill
      resolver-no-deportivos.

  ./venv/bin/python agent-resolver.py recetas recetas-AAAA-MM-DD.yaml [--apply] [--only ID ...]
      Escribe recetas de resolución mecánica (auto_resolucion, ver
      app/services/resolucion/recetas.py) en mercados ya sembrados, vía PATCH.
      Sin --apply solo valida.

  ./venv/bin/python agent-resolver.py sujetos-generar --out resoluciones/sujetos-AAAA-MM-DD.yaml [--only ID ...]
      Backfill de identidad (solo lectura: GET al API y a ESPN/CBS/UEFA). Para
      los accesorios de jugador activos (open + pending_resolution) arma
      `sujeto` desde market_content (nfl.py:PROPS, futbol_accesorios.py) o el
      sujeto que ya tenga el mercado, y busca los ids por fuente con
      identidad.buscar_ids (nombre idéntico y único en el plantel del equipo,
      nunca fuzzy). Escribe un YAML id → sujeto con los que pasaron; los que
      fallan van como comentario y el comando sale con código 1. Revisar a mano.

  ./venv/bin/python agent-resolver.py sujetos resoluciones/sujetos-AAAA-MM-DD.yaml [--apply] [--only ID ...]
      Escribe `sujeto` (identidad del jugador: equipo, rival, posición,
      alcance, ids por fuente) en mercados ya sembrados, vía PATCH. Sin --apply
      solo valida (validar_sujeto contra la pregunta del mercado) e imprime.
      --apply escribe en PRODUCCIÓN: solo con OK de Mark.

  ./venv/bin/python agent-resolver.py plan-auto --out resoluciones/AAAA-MM-DD.json [--liga "Serie A" ...]
      Arma el plan SIN LLM: cruza los 1X2 pendientes con ESPN y TheSportsDB
      (paquete resolucion/). Solo entran con confianza alta los partidos cuyo
      marcador coincide en ambas fuentes; el resto (aplazados, una sola fuente)
      queda en escalados. Accesorios de jugador (props NFL, titular/gol): el
      partido sale de sujeto.equipo + rival y el jugador se ubica por id; sin
      sujeto o con cualquier duda de identidad, escalado sin sugerencia.

  ./venv/bin/python agent-resolver.py check-plan resoluciones/AAAA-MM-DD.json
      Valida un plan contra el API (solo lectura): mercado sigue pendiente,
      veredicto válido para el tipo, dos fuentes de hosts distintos, confianza
      alta, evento ya cerrado y, en accesorios de jugador, sujeto en el mercado
      y `sujeto_confirmado` con los mismos ids por fuente (imprime la
      identidad). Sale con código 1 si hay errores.

  ./venv/bin/python agent-resolver.py proponer resoluciones/AAAA-MM-DD.json [--only ID ...]
      Flujo normal desde 2026-09-12: valida el plan (check-plan) y lo sube al
      servidor como ResolutionPlan pendiente (origen=agente). Mark recibe el
      mismo correo que el nocturno, con tabla, fuentes y botón "Revisar y
      aprobar"; nada se resuelve hasta que él confirma. El resultado queda en
      el plan del servidor (`planes`). No escribe log.jsonl.

  ./venv/bin/python agent-resolver.py apply resoluciones/AAAA-MM-DD.json --yes [--only ID ...]
      Respaldo, solo si Mark lo pide expresamente en el chat: ejecuta el plan
      directo (tras check-plan). IRREVERSIBLE: paga posiciones, escribe
      ledger, liquida ligas privadas y manda correos. Cada resultado se anexa a
      resoluciones/log.jsonl; los ya registrados con ok=true se saltan, así que
      se puede re-ejecutar tras un fallo parcial. --yes solo con aprobación
      explícita de Mark.

  ./venv/bin/python agent-resolver.py resolve <market_id> --resolution YES|NO
  ./venv/bin/python agent-resolver.py resolve <market_id> --outcome <outcome_key>
      Resuelve UN mercado a mano (también irreversible, también con aprobación).

  ./venv/bin/python agent-resolver.py cancel <market_id>
      Cancela UN mercado (reembolsa shares*avg_cost, anula picks de ligas).
      En un plan, el veredicto "CANCELAR" hace lo mismo (aplazado fuera de
      ventana, empate en NFL). Que un jugador no participó nunca se da por
      hecho: el job lo escala y Mark lo confirma a mano.

  ./venv/bin/python agent-resolver.py patch <market_id> --json '{...}'
      Edita un mercado no resuelto: {"status":"open","ends_at":"…Z"} reabre un
      aplazado con su nueva fecha; también question, rules, context y
      outcome_labels {"local":"🏠 D.C. United"}.

  ./venv/bin/python agent-resolver.py planes [--limit N]
  ./venv/bin/python agent-resolver.py plan-nocturno
      Planes del job nocturno del servidor (status, resumen) y disparo manual.
      El plan se aprueba desde el enlace del correo, no desde aquí.

Formato del plan (JSON):
  {"generado": "2026-09-09T20:00:00Z",
   "resoluciones": [{"id": "...", "veredicto": "YES|NO|<outcome_key>",
                     "resultado": "Bayern 3-0 Schalke", "fuente_1": "https://...",
                     "fuente_2": "https://...", "confianza": "alta"}],
   "escalados": [{"id": "...", "razon": "..."}]}
  Accesorios de jugador: cada resolución lleva además
   "sujeto_confirmado": {"jugador": "Josh Allen", "equipo": "Buffalo Bills", "partido": "BUF@HOU",
                         "espn": {"id": "3918298", "nombre": "Josh Allen", "equipo": "Buffalo Bills"},
                         "cbs": {"id": "2181054", "nombre": "Josh Allen", "equipo": "Buffalo Bills"}}
   con un bloque por host de fuente (espn/cbs/uefa: id = sujeto.ids; thesportsdb:
   "tsdb" con nombre y equipo; otro host: "manual": {"equipo", "nota"}). CANCELAR
   solo exige el equipo.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

API = "https://presagio-mx-backend-production-a30e.up.railway.app/api"
REPO = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(REPO, ".env.agent")
LOG_FILE = os.path.join(REPO, "resoluciones", "log.jsonl")

sys.path.insert(0, REPO)
from app.services.resolucion.sujeto import texto_identidad  # noqa: E402  (puro, sin BD)
from app.services.resolucion.validar import validar_entrada  # noqa: E402  (puro, sin BD)

CAMPOS_COMPACTOS = (
    "id", "question", "market_type", "category", "subcategory", "kind",
    "ends_at", "volume", "num_trades",
)
CATEGORIA_DEPORTES = "Deportes"  # value del enum que devuelve el API


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _read_token() -> str | None:
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith("VEREDIKT_ADMIN_TOKEN="):
                    return line.strip().split("=", 1)[1] or None
    except FileNotFoundError:
        pass
    return None


def _req(path: str, data: dict | None = None, token: str | None = None, method: str | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        API + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)
        except Exception:
            detail = {"raw": e.read().decode(errors="replace")}
        return {"http_error": e.code, "detail": detail}


def _token_valido(token: str | None) -> bool:
    if not token:
        return False
    me = _req("/users/me", token=token)
    return isinstance(me, dict) and bool(me.get("email"))


def _ensure_token() -> str:
    """Devuelve un token válido; si el de .env.agent falta o venció, lo regenera."""
    token = _read_token()
    if _token_valido(token):
        return token
    print("Token ausente o vencido; regenerando con generate-agent-token.py…", file=sys.stderr)
    r = subprocess.run(
        [sys.executable, os.path.join(REPO, "generate-agent-token.py")],
        cwd=REPO, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"ERROR regenerando el token:\n{r.stdout}{r.stderr}")
    token = _read_token()
    if not _token_valido(token):
        sys.exit("ERROR: el token regenerado no fue aceptado por producción.")
    return token


def _auth(path: str, data: dict | None = None, method: str | None = None) -> dict | list:
    return _req(path, data=data, token=_ensure_token(), method=method)


# ── list ─────────────────────────────────────────────────────────────────────

def _fetch_markets(status: str) -> list[dict]:
    """Listado público paginado; status 'active' = open + pending_resolution."""
    markets, offset = [], 0
    while True:
        page = _req(f"/markets?status={status}&sort=ending&limit=100&offset={offset}")
        if isinstance(page, dict):
            sys.exit(f"ERROR listando mercados: {page}")
        markets.extend(page)
        if len(page) < 100:
            return markets
        offset += 100


def _fetch_pending() -> list[dict]:
    return _fetch_markets("pending_resolution")


def _detail(m: dict) -> dict:
    d = _req(f"/markets/{m['id']}")
    return m if isinstance(d, dict) and d.get("http_error") else d


def _proyectar(detail: dict, compact: bool) -> dict:
    out = {k: detail.get(k) for k in CAMPOS_COMPACTOS}
    outcomes = detail.get("outcomes") or []
    if compact:
        out["outcome_keys"] = [o.get("outcome_key") for o in outcomes]
        return out
    out["yes_price"] = detail.get("yes_price")
    out["resolution_criteria"] = detail.get("resolution_criteria")
    out["resolution_source_url"] = detail.get("resolution_source_url")
    out["rules"] = detail.get("rules")
    out["auto_resolucion"] = detail.get("auto_resolucion")
    out["sujeto"] = detail.get("sujeto")  # identidad del jugador (accesorios); la usa plan-auto
    out["outcomes"] = [
        {"outcome_key": o.get("outcome_key"), "label": o.get("label"), "price": o.get("price")}
        for o in outcomes
    ]
    return out


def cmd_list(compact: bool, out_path: str | None, sin_deportes: bool = False, categoria: str | None = None) -> None:
    markets = _fetch_pending()
    if sin_deportes:
        markets = [m for m in markets if m.get("category") != CATEGORIA_DEPORTES]
    if categoria:
        markets = [m for m in markets if (m.get("category") or "").lower() == categoria.lower()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        details = list(pool.map(_detail, markets))
    out = {"total": len(details), "markets": [_proyectar(d, compact) for d in details]}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if out_path:
        with open(out_path, "w") as f:
            f.write(text + "\n")
        print(f"{len(details)} mercados pendientes → {out_path}")
    else:
        print(text)


# ── plan ─────────────────────────────────────────────────────────────────────

def _cargar_plan(path: str) -> dict:
    with open(path) as f:
        plan = json.load(f)
    if not isinstance(plan.get("resoluciones"), list) or not plan["resoluciones"]:
        sys.exit("ERROR: el plan no tiene 'resoluciones'")
    ids = [r.get("id") for r in plan["resoluciones"]]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        sys.exit(f"ERROR: ids duplicados en el plan: {sorted(dup)}")
    return plan


def _detalles(ids: list[str]) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(ids, pool.map(lambda i: _req(f"/markets/{i}"), ids)))


def check_plan(path: str, only: list[str] | None = None) -> tuple[list[dict], dict[str, dict]]:
    """Valida el plan e imprime la tabla. Devuelve (entradas válidas, detalles)
    o termina el proceso con código 1 si hay errores."""
    plan = _cargar_plan(path)
    entradas = plan["resoluciones"]
    if only:
        faltan = set(only) - {e.get("id") for e in entradas}
        if faltan:
            sys.exit(f"ERROR: --only incluye ids que no están en el plan: {sorted(faltan)}")
        entradas = [e for e in entradas if e.get("id") in set(only)]
    detalles = _detalles([e["id"] for e in entradas])
    ahora = datetime.now(timezone.utc)

    errores: dict[str, list[str]] = {}
    vol_total, con_posiciones = 0.0, 0
    print(f"{'id':<42} {'veredicto':<10} {'vol':>7} {'ops':>4}  resultado")
    for e in entradas:
        d = detalles.get(e["id"]) or {}
        errs = validar_entrada(e, d, ahora)
        vol = float(d.get("volume") or 0)
        ops = int(d.get("num_trades") or 0)
        vol_total += vol
        con_posiciones += 1 if ops > 0 else 0
        marca = "✗" if errs else " "
        print(f"{marca}{e['id']:<41} {str(e.get('veredicto')):<10} {vol:>7.0f} {ops:>4}  {e.get('resultado', '')}")
        ident = texto_identidad(e.get("sujeto_confirmado"))
        if ident:
            print(f"{'':<42} identidad: {ident}")
        if errs:
            errores[e["id"]] = errs

    print(f"\n{len(entradas)} resoluciones · {con_posiciones} con operaciones · {vol_total:.0f} PT de volumen")
    for esc in plan.get("escalados") or []:
        print(f"  ESCALADO {esc.get('id')}: {esc.get('razon')}")
        ident = texto_identidad(esc.get("sujeto_confirmado"))
        if ident:
            print(f"    identidad: {ident}")
    if errores:
        print(f"\n{len(errores)} mercado(s) con errores:")
        for mid, errs in errores.items():
            for err in errs:
                print(f"  ✗ {mid}: {err}")
        sys.exit(1)
    print("\ncheck-plan OK: sin errores.")
    return entradas, detalles


# ── apply / resolve ───────────────────────────────────────────────────────────

def _payload(entrada: dict, detalle: dict) -> dict:
    v = entrada["veredicto"]
    return {"outcome_key": v} if detalle.get("market_type") == "multi" else {"resolution": v}


def _ya_resueltos_en_log() -> set[str]:
    hechos: set[str] = set()
    try:
        with open(LOG_FILE) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok"):
                    hechos.add(row.get("id"))
    except FileNotFoundError:
        pass
    return hechos


def _log(row: dict) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_apply(path: str, yes: bool, only: list[str] | None) -> None:
    entradas, detalles = check_plan(path, only)
    if not yes:
        sys.exit("\nNo se ejecutó nada: falta --yes (solo con aprobación explícita de Mark).")

    token = _ensure_token()
    hechos = _ya_resueltos_en_log()
    ok, saltados, fallidos, posiciones = [], [], [], 0
    for e in entradas:
        mid = e["id"]
        if mid in hechos:
            saltados.append(mid)
            print(f"SALTADO {mid} (ya está en el log como resuelto)")
            continue
        if e["veredicto"] == "CANCELAR":
            r = _req(f"/admin/markets/{mid}/cancel", data={}, token=token)
            if isinstance(r, dict) and r.get("ok"):
                r["positions_settled"] = r.get("positions_refunded", 0)
        else:
            r = _req(f"/admin/markets/{mid}/resolve", data=_payload(e, detalles[mid]), token=token)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "plan": os.path.basename(path),
            "id": mid,
            "veredicto": e["veredicto"],
            "resultado": e.get("resultado"),
            "fuente_1": e.get("fuente_1"),
            "fuente_2": e.get("fuente_2"),
            "volume": detalles[mid].get("volume"),
            "num_trades": detalles[mid].get("num_trades"),
            "respuesta": r,
        }
        ya = isinstance(r, dict) and (r.get("detail") or {}).get("code") == "MARKET_ALREADY_RESOLVED"
        if isinstance(r, dict) and r.get("ok"):
            row["ok"] = True
            n = int(r.get("positions_settled") or 0)
            posiciones += n
            ok.append(mid)
            print(f"RESUELTO {mid} → {r.get('resolution')} (posiciones liquidadas: {n})")
        elif ya:
            row["ok"] = True
            row["nota"] = "ya estaba resuelto"
            saltados.append(mid)
            print(f"YA RESUELTO {mid} (MARKET_ALREADY_RESOLVED)")
        else:
            row["ok"] = False
            fallidos.append((mid, r))
            print(f"FALLÓ {mid}: {json.dumps(r, ensure_ascii=False)}")
        _log(row)

    print(f"\nResueltos: {len(ok)} · posiciones liquidadas: {posiciones} · saltados: {len(saltados)} · fallidos: {len(fallidos)}")
    for mid, r in fallidos:
        print(f"  ✗ {mid}: {json.dumps(r, ensure_ascii=False)}")
    if fallidos:
        sys.exit(1)


def cmd_proponer(path: str, only: list[str] | None) -> None:
    """Sube el plan al servidor para aprobación por correo (no resuelve nada)."""
    entradas, _ = check_plan(path, only)
    plan = _cargar_plan(path)
    body = {
        "resoluciones": entradas,
        "escalados": plan.get("escalados") or [],
        "nota": f"{os.path.basename(path)}" + (f" (--only {' '.join(only)})" if only else ""),
    }
    r = _auth("/admin/resolucion/planes/proponer", data=body)
    if isinstance(r, dict) and r.get("id") and r.get("status") == "pending":
        s = r.get("resumen") or {}
        print(f"\nPlan #{r['id']} propuesto · correo enviado a Mark · {s.get('resoluciones', 0)} resoluciones "
              f"({s.get('con_operaciones', 0)} con operaciones, {s.get('volumen', 0)} PT) · {s.get('escalados', 0)} escalados")
        print("Nada se resolvió: Mark aprueba desde el enlace del correo. Verifica luego con: agent-resolver.py planes")
        return
    detail = (r.get("detail") or {}) if isinstance(r, dict) else {}
    if detail.get("code") == "PLAN_INVALIDO":
        print(f"\nEl servidor rechazó el plan: {detail.get('message')}")
        for mid, errs in (detail.get("errores") or {}).items():
            for err in errs:
                print(f"  ✗ {mid}: {err}")
        sys.exit(1)
    sys.exit(f"ERROR: {json.dumps(r, ensure_ascii=False)}")


def cmd_resolve(market_id: str, resolution: str | None, outcome: str | None) -> None:
    if bool(resolution) == bool(outcome):
        sys.exit("ERROR: pasa exactamente uno: --resolution YES|NO (binario) o --outcome <key> (multi)")
    payload = {"resolution": resolution} if resolution else {"outcome_key": outcome}
    r = _auth(f"/admin/markets/{market_id}/resolve", data=payload)
    _log({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": None, "id": market_id, "veredicto": resolution or outcome,
        "respuesta": r, "ok": bool(isinstance(r, dict) and r.get("ok")),
    })
    if isinstance(r, dict) and r.get("ok"):
        print(f"RESUELTO {market_id} → {r.get('resolution')} (posiciones liquidadas: {r.get('positions_settled')})")
    else:
        sys.exit(f"FALLÓ {market_id}: {json.dumps(r, ensure_ascii=False)}")


def cmd_cancel(market_id: str) -> None:
    """Cancela UN mercado a mano (reembolsa; irreversible; con aprobación)."""
    r = _auth(f"/admin/markets/{market_id}/cancel", data={})
    _log({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": None, "id": market_id, "veredicto": "CANCELAR",
        "respuesta": r, "ok": bool(isinstance(r, dict) and r.get("ok")),
    })
    if isinstance(r, dict) and r.get("ok"):
        print(f"CANCELADO {market_id} (posiciones reembolsadas: {r.get('positions_refunded')}, {r.get('refunded')} PT)")
    else:
        sys.exit(f"FALLÓ {market_id}: {json.dumps(r, ensure_ascii=False)}")


def cmd_patch(market_id: str, raw_json: str) -> None:
    """Edita un mercado no resuelto (PATCH /admin/markets/{id}): reabrir con
    nueva fecha, pregunta, normas, contexto, etiquetas de outcomes."""
    try:
        body = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: --json inválido: {e}")
    r = _auth(f"/admin/markets/{market_id}", data=body, method="PATCH")
    if isinstance(r, dict) and r.get("ok"):
        print(f"EDITADO {market_id}: {', '.join(r.get('cambios') or [])} → status {r.get('status')} · cierre {r.get('ends_at')}")
    else:
        sys.exit(f"FALLÓ {market_id}: {json.dumps(r, ensure_ascii=False)}")


def _cargar_mapa(path: str, que: str) -> dict:
    """YAML/JSON con un mapa id → valor (recetas, sujetos)."""
    with open(path) as f:
        raw = f.read()
    if path.endswith(".json"):
        mapa = json.loads(raw)
    else:
        import yaml  # PyYAML ya es dependencia del sembrador

        mapa = yaml.safe_load(raw) or {}
    if not isinstance(mapa, dict):
        sys.exit(f"ERROR: el archivo debe ser un mapa id → {que}")
    return mapa


def cmd_recetas(path: str, apply: bool, only: list[str] | None) -> None:
    """Aplica recetas (id → auto_resolucion) de un YAML/JSON a mercados existentes
    vía PATCH. Sin --apply solo valida e imprime."""
    from app.services.resolucion.recetas import validar_receta

    recetas = _cargar_mapa(path, "receta")
    ids = [i for i in recetas if not only or i in set(only)]
    detalles = _detalles(ids)
    errores = 0
    for mid in ids:
        r = recetas[mid]
        d = detalles.get(mid) or {}
        if not d or d.get("http_error"):
            print(f"✗ {mid}: no existe en el API"); errores += 1; continue
        errs = validar_receta(r, d.get("market_type") or "binary")
        if errs:
            print(f"✗ {mid}: {'; '.join(errs)}"); errores += 1; continue
        estado = "ya tiene receta" if d.get("auto_resolucion") else "sin receta"
        print(f"  {mid:<40} {r.get('fuente'):<20} {estado}")
    if errores:
        sys.exit(f"\n{errores} receta(s) con errores; no se aplicó nada.")
    if not apply:
        print(f"\n{len(ids)} recetas válidas. Corre con --apply para escribirlas (PATCH /admin/markets/{{id}}).")
        return
    ok = 0
    for mid in ids:
        resp = _auth(f"/admin/markets/{mid}", data={"auto_resolucion": recetas[mid]}, method="PATCH")
        if isinstance(resp, dict) and resp.get("ok"):
            ok += 1
            print(f"APLICADA {mid}")
        else:
            print(f"FALLÓ {mid}: {json.dumps(resp, ensure_ascii=False)}")
    print(f"\n{ok}/{len(ids)} recetas aplicadas.")


# ── sujetos (identidad del jugador en accesorios ya sembrados) ───────────────

def _bases_market_content() -> dict[str, tuple[dict, str | None]]:
    """id → (sujeto base {jugador, equipo, rival, alcance}, kickoff ISO) desde el
    contenido redactado de cada accesorio: nfl.py:PROPS y futbol_accesorios.py.
    Sin posicion ni ids: los llena identidad.buscar_ids."""
    import re

    from app.services.resolucion.cruce import UMBRAL, similitud
    from market_content import futbol_accesorios as fa
    from market_content import nfl

    bases: dict[str, tuple[dict, str | None]] = {}
    for mid, _tipo, jugador, equipo, rival, kickoff, _ctx in nfl.PROPS:
        bases[mid] = ({"jugador": jugador, "equipo": equipo, "rival": rival, "alcance": "partido"}, kickoff)
    for mid, jugador, club, rival, fecha, _ctx in fa.UCL_TITULARES + fa.UCL_GOLES:
        bases[mid] = ({"jugador": jugador, "equipo": club, "rival": rival, "alcance": "partido"}, fecha)
    for mid, jugador, club, partido, _fuente, cierre, _ventana, _url, _ctx in fa.LIGA_TITULARES:
        # "Sevilla vs. Atlético de Madrid (Jornada 3 …)": el rival es el lado que no es el club
        lados = [x.strip() for x in re.sub(r"\s*\(.*\)\s*$", "", partido).split(" vs. ")]
        rivales = [x for x in lados if similitud(x, club) < UMBRAL]
        base = {"jugador": jugador, "equipo": club, "alcance": "partido"}
        if len(lados) == 2 and len(rivales) == 1:
            base["rival"] = rivales[0]
        bases[mid] = (base, cierre)
    return bases


def _fecha_iso(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None


def cmd_sujetos_generar(out_path: str, only: list[str] | None) -> None:
    """Arma el YAML id → sujeto de los accesorios de jugador activos (solo
    lectura: GET al API y a ESPN/CBS/UEFA). Los que fallan van comentados y el
    comando sale con código 1; nada se escribe en el API."""
    import yaml

    from app.services.resolucion import identidad
    from app.services.resolucion.fuentes import Http
    from app.services.resolucion.sujeto import spec_de_mercado, validar_sujeto

    # status=active (open + pending_resolution): _fetch_pending no vería los
    # accesorios que todavía no cierran.
    activos = [m for m in _fetch_markets("active") if spec_de_mercado(m)]
    if only:
        faltan = set(only) - {m["id"] for m in activos}
        if faltan:
            sys.exit(f"ERROR: --only incluye ids que no son accesorios de jugador activos: {sorted(faltan)}")
        activos = [m for m in activos if m["id"] in set(only)]
    if not activos:
        print("Ningún accesorio de jugador activo: no se escribe nada.")
        return
    detalles = _detalles([m["id"] for m in activos])
    bases = _bases_market_content()
    http = Http()
    ok: dict[str, dict] = {}
    fallidos: dict[str, tuple[dict, list[str]]] = {}
    for m in activos:
        mid = m["id"]
        d = detalles.get(mid) or {}
        if d.get("http_error"):
            fallidos[mid] = ({}, [f"detalle no disponible en el API: {d}"])
            continue
        liga, spec = d.get("subcategory"), spec_de_mercado(d)
        contenido, kickoff = bases.get(mid, (None, None))
        if isinstance(d.get("sujeto"), dict) and d["sujeto"]:
            base, origen = dict(d["sujeto"]), "sujeto actual del mercado (se re-verifica)"
        elif contenido:
            base, origen = dict(contenido), "market_content"
        else:
            fallidos[mid] = ({}, ["sin base en market_content ni sujeto en el mercado: escribir jugador, equipo, rival "
                                  "y alcance a mano y correr `sujetos` con ese YAML"])
            continue
        fecha = _fecha_iso(kickoff) or _fecha_iso(d.get("ends_at"))
        sujeto, errores, avisos = identidad.buscar_ids(http, liga, base, fecha)
        if not errores:
            errores = validar_sujeto(spec, sujeto, liga)
        for a in avisos:
            print(f"  aviso {mid}: {a}")
        if errores:
            fallidos[mid] = (sujeto, errores)
            print(f"✗ {mid} ({origen}): {'; '.join(errores)}")
            continue
        ok[mid] = sujeto
        ids_txt = " · ".join(f"{k.upper()} {v}" for k, v in sujeto["ids"].items())
        print(f"✓ {mid:<40} {sujeto['jugador']} ({sujeto['equipo']} vs {sujeto.get('rival')}, {sujeto['posicion']}) {ids_txt}")

    lineas = [
        f"# Sujetos (identidad del jugador) de accesorios activos: agent-resolver.py sujetos-generar, "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "# Ids buscados por nombre idéntico y único en el plantel del equipo (identidad.buscar_ids, nunca fuzzy).",
        "# Revisar a mano → agent-resolver.py sujetos <este archivo> (dry-run) → --apply solo con OK de Mark.",
        "",
    ]
    for mid, s in ok.items():
        lineas.append(yaml.safe_dump({mid: s}, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip())
        lineas.append("")
    if fallidos:
        lineas.append("# ── con errores: NO se aplican; corregir la base y volver a generar, o escribirlos a mano ──")
        for mid, (s, errores) in fallidos.items():
            lineas.append(f"# {mid}:")
            lineas += [f"#   error: {e}" for e in errores]
            if s:
                lineas += [f"#   {x}" for x in yaml.safe_dump(s, allow_unicode=True, sort_keys=False).rstrip().splitlines()]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lineas).rstrip() + "\n")
    print(f"\n{len(ok)} sujetos listos · {len(fallidos)} con errores → {out_path} ({http.consultas} consultas)")
    if fallidos:
        sys.exit(1)


def cmd_sujetos(path: str, apply: bool, only: list[str] | None) -> None:
    """Escribe `sujeto` (id → sujeto de un YAML/JSON) en mercados existentes vía
    PATCH. Sin --apply solo valida (validar_sujeto contra la pregunta actual del
    mercado) e imprime. `{}` borra el sujeto. El PATCH vuelve a validar."""
    from app.services.resolucion.sujeto import normalizar_sujeto, spec_de_mercado, validar_sujeto

    sujetos = _cargar_mapa(path, "sujeto")
    if only:
        faltan = set(only) - set(sujetos)
        if faltan:
            sys.exit(f"ERROR: --only incluye ids que no están en el archivo: {sorted(faltan)}")
    ids = [i for i in sujetos if not only or i in set(only)]
    detalles = _detalles(ids)
    cuerpos: dict[str, dict] = {}
    errores = 0
    for mid in ids:
        s = sujetos[mid]
        d = detalles.get(mid) or {}
        if not d or d.get("http_error"):
            print(f"✗ {mid}: no existe en el API"); errores += 1; continue
        if d.get("status") not in ("open", "pending_resolution"):
            print(f"✗ {mid}: status '{d.get('status')}' (solo mercados sin resolver)"); errores += 1; continue
        if s == {}:
            cuerpos[mid] = {}
            print(f"  {mid:<40} BORRAR sujeto" + ("" if d.get("sujeto") else " (ya no tiene)"))
            continue
        if not isinstance(s, dict):
            print(f"✗ {mid}: el sujeto debe ser un mapa"); errores += 1; continue
        s = normalizar_sujeto(s)
        errs = validar_sujeto(spec_de_mercado(d), s, d.get("subcategory"))
        if errs:
            print(f"✗ {mid}: {'; '.join(errs)}"); errores += 1; continue
        actual = d.get("sujeto")
        estado = "sin sujeto" if not actual else ("igual al actual" if actual == s else "REEMPLAZA el actual")
        ids_txt = " · ".join(f"{k.upper()} {v}" for k, v in s["ids"].items())
        print(f"  {mid:<40} {s['jugador']} ({s['equipo']} vs {s.get('rival')}, {s['posicion']}, {s['alcance']}) {ids_txt} · {estado}")
        cuerpos[mid] = s
    if errores:
        sys.exit(f"\n{errores} sujeto(s) con errores; no se aplicó nada.")
    if not apply:
        print(f"\n{len(ids)} sujetos válidos. Corre con --apply para escribirlos (PATCH /admin/markets/{{id}}; PRODUCCIÓN, solo con OK de Mark).")
        return
    ok = 0
    for mid in ids:
        resp = _auth(f"/admin/markets/{mid}", data={"sujeto": cuerpos[mid]}, method="PATCH")
        if isinstance(resp, dict) and resp.get("ok"):
            ok += 1
            print(f"APLICADO {mid}")
        else:
            print(f"FALLÓ {mid}: {json.dumps(resp, ensure_ascii=False)}")
    print(f"\n{ok}/{len(ids)} sujetos aplicados.")
    if ok < len(ids):
        sys.exit(1)


def cmd_plan_auto(out_path: str, ligas: list[str] | None, desde: str | None = None) -> None:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    from app.services.resolucion.plan import armar_plan

    if desde:
        # Replay: listado guardado con `list --out` (detalle completo), p. ej.
        # para reproducir el armado sobre mercados ya resueltos.
        with open(desde) as f:
            data = json.load(f)
        details = data if isinstance(data, list) else data.get("markets") or data.get("mercados") or []
    else:
        markets = _fetch_pending()
        with ThreadPoolExecutor(max_workers=8) as pool:
            details = [_proyectar(d, compact=False) for d in pool.map(_detail, markets)]
    plan = armar_plan(details, solo_ligas=set(ligas) if ligas else None)
    plan["escalados"].sort(key=lambda e: (-(e.get("volume") or 0), e["id"]))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    res, esc = plan["resoluciones"], plan["escalados"]
    con_sug = [e for e in esc if e.get("veredicto_sugerido")]
    print(f"{len(details)} pendientes → {len(res)} resoluciones con doble fuente, {len(esc)} escalados "
          f"({len(con_sug)} con veredicto sugerido) → {out_path}")
    for e in esc:
        sug = f" sugerido={e['veredicto_sugerido']}" if e.get("veredicto_sugerido") else ""
        print(f"  ESCALADO {e['id']} (vol {e.get('volume', 0)}):{sug} {e['razon']}")


def cmd_planes(limit: int) -> None:
    """Planes del servidor (job nocturno) con su status y resumen."""
    r = _auth(f"/admin/resolucion/planes?limit={limit}")
    if isinstance(r, dict) and r.get("http_error"):
        sys.exit(f"ERROR: {json.dumps(r, ensure_ascii=False)}")
    n = r.get("nightly", {})
    horas = ", ".join(f"{h:02d}:00" for h in (n.get("horas_utc") or [])) or "?"
    print(f"job de resolución: corre a las {horas} UTC · última corrida {n.get('ran_at')} · último plan #{n.get('last_plan_id')} · error: {n.get('last_error')}")
    for p in r.get("planes", []):
        s = p.get("resumen") or {}
        res = p.get("resultado") or {}
        extra = f" → resueltos {len(res.get('resueltos', []))}, fallidos {len(res.get('fallidos', []))}" if res else ""
        print(f"#{p['id']:<4} {p['status']:<9} {p['created_at'][:16]}  {s.get('resoluciones', 0)} res · {s.get('escalados', 0)} esc · {s.get('volumen', 0)} PT{extra}")


def cmd_plan_nocturno() -> None:
    """Dispara en el servidor la armada de un plan (en segundo plano)."""
    r = _auth("/admin/resolucion/planes", data={})
    if isinstance(r, dict) and r.get("started"):
        print("Plan nocturno disparado en el servidor. En unos minutos llega el correo; revisa con: agent-resolver.py planes")
    else:
        sys.exit(f"ERROR: {json.dumps(r, ensure_ascii=False)}")


def cmd_check_token() -> None:
    token = _ensure_token()
    me = _req("/users/me", token=token)
    print(f"OK — token válido, sesión de {me['email']}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-token")
    pl = sub.add_parser("list")
    pl.add_argument("--compact", action="store_true")
    pl.add_argument("--out")
    pl.add_argument("--sin-deportes", action="store_true", help="solo mercados fuera de Deportes")
    pl.add_argument("--categoria", help="solo esta categoría (valor del API, p. ej. 'Política')")
    prc = sub.add_parser("recetas", help="aplicar recetas auto_resolucion (id → receta) a mercados existentes")
    prc.add_argument("archivo")
    prc.add_argument("--apply", action="store_true")
    prc.add_argument("--only", nargs="+")
    psg = sub.add_parser("sujetos-generar", help="armar el YAML id → sujeto de los accesorios de jugador activos (solo lectura)")
    psg.add_argument("--out", required=True, help="p. ej. resoluciones/sujetos-AAAA-MM-DD.yaml")
    psg.add_argument("--only", nargs="+")
    psj = sub.add_parser("sujetos", help="escribir sujeto (id → sujeto) en mercados existentes vía PATCH")
    psj.add_argument("archivo")
    psj.add_argument("--apply", action="store_true", help="escribe en PRODUCCIÓN (solo con OK de Mark)")
    psj.add_argument("--only", nargs="+")
    pp = sub.add_parser("plan-auto")
    pp.add_argument("--out", required=True)
    pp.add_argument("--liga", action="append", help="limitar a una subcategoría (repetible)")
    pp.add_argument("--desde", help="replay: listado JSON guardado con `list --out` en vez de los pendientes del API")
    pc = sub.add_parser("check-plan")
    pc.add_argument("plan")
    pc.add_argument("--only", nargs="+")
    ppr = sub.add_parser("proponer")
    ppr.add_argument("plan")
    ppr.add_argument("--only", nargs="+")
    pa = sub.add_parser("apply")
    pa.add_argument("plan")
    pa.add_argument("--yes", action="store_true", help="ejecutar de verdad (solo con aprobación de Mark)")
    pa.add_argument("--only", nargs="+")
    pr = sub.add_parser("resolve")
    pr.add_argument("market_id")
    pr.add_argument("--resolution", choices=["YES", "NO"])
    pr.add_argument("--outcome")
    pcx = sub.add_parser("cancel")
    pcx.add_argument("market_id")
    ppt = sub.add_parser("patch")
    ppt.add_argument("market_id")
    ppt.add_argument("--json", required=True, help='p. ej. \'{"status":"open","ends_at":"2026-10-24T23:30:00Z"}\'')
    pls = sub.add_parser("planes")
    pls.add_argument("--limit", type=int, default=10)
    sub.add_parser("plan-nocturno")
    a = p.parse_args()
    if a.cmd == "check-token":
        cmd_check_token()
    elif a.cmd == "cancel":
        cmd_cancel(a.market_id)
    elif a.cmd == "patch":
        cmd_patch(a.market_id, a.json)
    elif a.cmd == "planes":
        cmd_planes(a.limit)
    elif a.cmd == "plan-nocturno":
        cmd_plan_nocturno()
    elif a.cmd == "list":
        cmd_list(a.compact, a.out, a.sin_deportes, a.categoria)
    elif a.cmd == "recetas":
        cmd_recetas(a.archivo, a.apply, a.only)
    elif a.cmd == "sujetos-generar":
        cmd_sujetos_generar(a.out, a.only)
    elif a.cmd == "sujetos":
        cmd_sujetos(a.archivo, a.apply, a.only)
    elif a.cmd == "plan-auto":
        cmd_plan_auto(a.out, a.liga, a.desde)
    elif a.cmd == "check-plan":
        check_plan(a.plan, a.only)
    elif a.cmd == "proponer":
        cmd_proponer(a.plan, a.only)
    elif a.cmd == "apply":
        cmd_apply(a.plan, a.yes, a.only)
    elif a.cmd == "resolve":
        cmd_resolve(a.market_id, a.resolution, a.outcome)


if __name__ == "__main__":
    main()
