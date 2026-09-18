"""Genera un Markdown con TODOS los mercados activos de VEREDIKT (OPEN + PENDING)
leyendo la API pública de producción. No necesita credenciales ni Railway.

Uso:
  python3 export-contexto-agente.py > contexto-mercados-veredikt.md

Salida: secciones por categoría → subcategoría (· Partidos / · Accesorios) →
lista ordenada por fecha de cierre con tipo, cierre (hora CDMX), precios y id.
Pensado para pegarse en la carpeta de contexto de un agente.
"""
import collections
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://presagio-mx-backend-production-a30e.up.railway.app/api/markets"
CDMX = timezone(timedelta(hours=-6))
CAT_ORDER = ["Deportes", "Política", "Global", "México", "Economía", "Mercados Globales",
             "Crypto", "Tech", "Entretenimiento", "Clima"]


def fetch_all() -> list[dict]:
    rows, offset = [], 0
    while True:
        with urllib.request.urlopen(f"{API}?status=active&limit=100&offset={offset}&sort=ending") as r:
            page = json.load(r)
        rows += page
        if len(page) < 100:
            return rows
        offset += 100


def fmt(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CDMX).strftime("%d-%b-%Y %H:%M")


def main() -> None:
    rows = fetch_all()
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["category"], r.get("subcategory") or "", r.get("kind") or "")].append(r)

    n_open = sum(1 for r in rows if r["status"] == "open")
    out = [f"# Mercados activos de VEREDIKT — {datetime.now(CDMX):%Y-%m-%d %H:%M} CDMX",
           f"\nTotal activos: {len(rows)} (abiertos: {n_open}, por resolverse: {len(rows) - n_open}). "
           f"Binarios: {sum(1 for r in rows if r['market_type'] == 'binary')}, "
           f"multi: {sum(1 for r in rows if r['market_type'] == 'multi')}.\n"]
    cats = CAT_ORDER + sorted({k[0] for k in groups} - set(CAT_ORDER))
    for cat in cats:
        keys = [k for k in groups if k[0] == cat]
        if not keys:
            continue
        out.append(f"\n## {cat} ({sum(len(groups[k]) for k in keys)} mercados)\n")
        for k in sorted(keys, key=lambda k: (k[1], k[2])):
            title = k[1] or "General"
            if k[2]:
                title += " · " + ("Partidos" if k[2] == "partido" else "Accesorios")
            items = sorted(groups[k], key=lambda r: r["ends_at"])
            out.append(f"\n**{title}** ({len(items)})\n")
            for r in items:
                st = "" if r["status"] == "open" else " [POR RESOLVERSE]"
                if r["market_type"] == "multi":
                    outs = sorted(r["outcomes"], key=lambda o: -o["price"])
                    px = " / ".join(f"{o['label']} {o['price']:.0f}%" for o in outs[:3])
                    if len(outs) > 3:
                        px += f" (+{len(outs) - 3} más)"
                    kind_txt = f"multi {len(outs)} salidas"
                else:
                    px, kind_txt = f"SÍ {r['yes_price']:.0f}%", "binario"
                vol = f", vol {r['volume']:.0f} PT" if r["volume"] > 0 else ""
                out.append(f"- {r['question']}{st} — {kind_txt}; cierra {fmt(r['ends_at'])}; {px}{vol}. id: `{r['id']}`")
    sys.stdout.write("\n".join(out) + "\n")
    print(f"{len(rows)} mercados activos", file=sys.stderr)


if __name__ == "__main__":
    main()
