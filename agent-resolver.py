#!/usr/bin/env python3
"""CLI del agente de mercados: listar mercados por resolver y ejecutar resoluciones.

Sin dependencias (urllib): correr SIEMPRE con ./venv/bin/python (el python3 del sistema no tiene certificados SSL).
El token se lee de .env.agent (generarlo con generate-agent-token.py).

Comandos:
  ./venv/bin/python agent-resolver.py check-token
      Verifica que el token de .env.agent sigue siendo válido.

  ./venv/bin/python agent-resolver.py list
      Lista TODOS los mercados en pending_resolution con su detalle completo
      (criterio de resolución, fuente, normas, outcomes y precios) en JSON.

  ./venv/bin/python agent-resolver.py resolve <market_id> --resolution YES|NO
  ./venv/bin/python agent-resolver.py resolve <market_id> --outcome <outcome_key>
      Resuelve UN mercado (binario o multi). Acción IRREVERSIBLE: paga
      posiciones, escribe ledger, liquida ligas privadas y manda correos.
      Solo ejecutar con aprobación explícita de Mark.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://presagio-mx-backend-production-a30e.up.railway.app/api"
REPO = os.path.dirname(os.path.abspath(__file__))


def _token() -> str:
    path = os.path.join(REPO, ".env.agent")
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("VEREDIKT_ADMIN_TOKEN="):
                    return line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass
    sys.exit("ERROR: no hay token en .env.agent — corre: ./venv/bin/python generate-agent-token.py")


def _req(path: str, data: dict | None = None, auth: bool = False) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + _token()
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


def cmd_check_token() -> None:
    me = _req("/users/me", auth=True)
    if isinstance(me, dict) and me.get("email"):
        print(f"OK — token válido, sesión de {me['email']}")
    else:
        sys.exit(f"TOKEN INVÁLIDO: {me}\nRegenera con: ./venv/bin/python generate-agent-token.py")


def cmd_list() -> None:
    markets, offset = [], 0
    while True:
        page = _req(f"/markets?status=pending_resolution&sort=ending&limit=100&offset={offset}")
        if isinstance(page, dict):  # error
            sys.exit(f"ERROR listando mercados: {page}")
        markets.extend(page)
        if len(page) < 100:
            break
        offset += 100
    out = []
    for m in markets:
        detail = _req(f"/markets/{m['id']}")
        if isinstance(detail, dict) and detail.get("http_error"):
            detail = m  # fallback al resumen si el detalle falla
        out.append(
            {
                "id": detail.get("id"),
                "question": detail.get("question"),
                "market_type": detail.get("market_type"),
                "category": detail.get("category"),
                "subcategory": detail.get("subcategory"),
                "kind": detail.get("kind"),
                "ends_at": detail.get("ends_at"),
                "volume": detail.get("volume"),
                "num_trades": detail.get("num_trades"),
                "yes_price": detail.get("yes_price"),
                "resolution_criteria": detail.get("resolution_criteria"),
                "resolution_source_url": detail.get("resolution_source_url"),
                "rules": detail.get("rules"),
                "outcomes": [
                    {"outcome_key": o.get("outcome_key"), "label": o.get("label"), "price": o.get("price")}
                    for o in (detail.get("outcomes") or [])
                ],
            }
        )
    print(json.dumps({"total": len(out), "markets": out}, ensure_ascii=False, indent=1))


def cmd_resolve(market_id: str, resolution: str | None, outcome: str | None) -> None:
    if bool(resolution) == bool(outcome):
        sys.exit("ERROR: pasa exactamente uno: --resolution YES|NO (binario) o --outcome <key> (multi)")
    payload = {"resolution": resolution} if resolution else {"outcome_key": outcome}
    r = _req(f"/admin/markets/{market_id}/resolve", data=payload, auth=True)
    if isinstance(r, dict) and r.get("ok"):
        print(f"RESUELTO {market_id} → {r.get('resolution')} (posiciones liquidadas: {r.get('positions_settled')})")
    else:
        sys.exit(f"FALLÓ {market_id}: {json.dumps(r, ensure_ascii=False)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-token")
    sub.add_parser("list")
    pr = sub.add_parser("resolve")
    pr.add_argument("market_id")
    pr.add_argument("--resolution", choices=["YES", "NO"])
    pr.add_argument("--outcome")
    a = p.parse_args()
    if a.cmd == "check-token":
        cmd_check_token()
    elif a.cmd == "list":
        cmd_list()
    elif a.cmd == "resolve":
        cmd_resolve(a.market_id, a.resolution, a.outcome)
