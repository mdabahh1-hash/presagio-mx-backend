#!/usr/bin/env python3
"""CLI del agente de mercados: listar mercados por resolver, validar un plan de
resoluciones y ejecutarlo con bitácora.

Sin dependencias (urllib): correr SIEMPRE con ./venv/bin/python (el python3 del
sistema no tiene certificados SSL). El token se lee de .env.agent; si venció, se
regenera solo con generate-agent-token.py.

Comandos:
  ./venv/bin/python agent-resolver.py check-token
      Verifica el token de .env.agent (y lo renueva si hace falta).

  ./venv/bin/python agent-resolver.py list [--compact] [--out archivo.json]
      Lista TODOS los mercados en pending_resolution. Por default con detalle
      completo (criterio, fuente, normas, outcomes); --compact solo lo que
      necesita la investigación.

  ./venv/bin/python agent-resolver.py plan-auto --out resoluciones/AAAA-MM-DD.json [--liga "Serie A" ...]
      Arma el plan SIN LLM: cruza los 1X2 pendientes con ESPN y TheSportsDB
      (paquete resolucion/). Solo entran con confianza alta los partidos cuyo
      marcador coincide en ambas fuentes; el resto (aplazados, una sola fuente,
      accesorios de titular/gol con sugerencia de ESPN) queda en escalados.

  ./venv/bin/python agent-resolver.py check-plan resoluciones/AAAA-MM-DD.json
      Valida un plan contra el API (solo lectura): mercado sigue pendiente,
      veredicto válido para el tipo, dos fuentes de hosts distintos, confianza
      alta, evento ya cerrado. Sale con código 1 si hay errores.

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
from app.services.resolucion.validar import validar_entrada  # noqa: E402  (puro, sin BD)

CAMPOS_COMPACTOS = (
    "id", "question", "market_type", "category", "subcategory", "kind",
    "ends_at", "volume", "num_trades",
)


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


def _req(path: str, data: dict | None = None, token: str | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        API + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
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


def _auth(path: str, data: dict | None = None) -> dict | list:
    return _req(path, data=data, token=_ensure_token())


# ── list ─────────────────────────────────────────────────────────────────────

def _fetch_pending() -> list[dict]:
    markets, offset = [], 0
    while True:
        page = _req(f"/markets?status=pending_resolution&sort=ending&limit=100&offset={offset}")
        if isinstance(page, dict):
            sys.exit(f"ERROR listando mercados: {page}")
        markets.extend(page)
        if len(page) < 100:
            return markets
        offset += 100


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
    out["outcomes"] = [
        {"outcome_key": o.get("outcome_key"), "label": o.get("label"), "price": o.get("price")}
        for o in outcomes
    ]
    return out


def cmd_list(compact: bool, out_path: str | None) -> None:
    markets = _fetch_pending()
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
        if errs:
            errores[e["id"]] = errs

    print(f"\n{len(entradas)} resoluciones · {con_posiciones} con operaciones · {vol_total:.0f} PT de volumen")
    for esc in plan.get("escalados") or []:
        print(f"  ESCALADO {esc.get('id')}: {esc.get('razon')}")
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


def cmd_plan_auto(out_path: str, ligas: list[str] | None) -> None:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    from app.services.resolucion.plan import armar_plan

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
    print(f"job nocturno: última corrida {n.get('ran_at')} · último plan #{n.get('last_plan_id')} · error: {n.get('last_error')}")
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
    pp = sub.add_parser("plan-auto")
    pp.add_argument("--out", required=True)
    pp.add_argument("--liga", action="append", help="limitar a una subcategoría (repetible)")
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
    pls = sub.add_parser("planes")
    pls.add_argument("--limit", type=int, default=10)
    sub.add_parser("plan-nocturno")
    a = p.parse_args()
    if a.cmd == "check-token":
        cmd_check_token()
    elif a.cmd == "planes":
        cmd_planes(a.limit)
    elif a.cmd == "plan-nocturno":
        cmd_plan_nocturno()
    elif a.cmd == "list":
        cmd_list(a.compact, a.out)
    elif a.cmd == "plan-auto":
        cmd_plan_auto(a.out, a.liga)
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
