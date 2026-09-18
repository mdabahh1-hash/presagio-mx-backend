"""
Backfill markets.rules (Normas), markets.context (Contexto del mercado) y
markets.resolution_source_url (fuente oficial) para los mercados activos (2026-09-04).

El contenido está redactado por mercado en el paquete `market_content/` (298
entradas al 4 de septiembre de 2026). Este script:
  1. Garantiza las columnas (ADD COLUMN IF NOT EXISTS) para poder correr antes
     del deploy que las crea en el boot (app.database.migrate_columns).
  2. Verifica cobertura: todo mercado OPEN/PENDING_RESOLUTION debe tener entrada;
     si falta alguno, aborta (salvo ALLOW_MISSING=1).
  3. Verifica calidad local (market_content.check): toda entrada sin URL abre
     sus Normas con "Cómo se resuelve:".
  4. Escribe rules/context donde rules IS NULL (FORCE=1 reescribe) y
     resolution_source_url solo donde esté NULL (nunca pisa una URL existente).

Dry-run por default; APPLY=1 escribe; FORCE=1 reescribe rules/context.

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-normas-contexto-fuente-2026-09-04.py'
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-normas-contexto-fuente-2026-09-04.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine
from market_content import ALL, check

APPLY = os.environ.get("APPLY") == "1"
FORCE = os.environ.get("FORCE") == "1"
ALLOW_MISSING = os.environ.get("ALLOW_MISSING") == "1"

SCHEMA_STMTS = [
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS rules TEXT",
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS context TEXT",
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS resolution_source_url VARCHAR(500)",
]

ACTIVE = "status IN ('OPEN', 'PENDING_RESOLUTION')"


async def resumen(conn, title: str) -> None:
    rows = (await conn.execute(text(f"""
        SELECT category,
               count(*) AS n,
               count(*) FILTER (WHERE rules IS NOT NULL AND context IS NOT NULL) AS con_texto,
               count(resolution_source_url) AS con_url
          FROM markets
         WHERE {ACTIVE}
         GROUP BY category ORDER BY category
    """))).all()
    print(f"\n{title}")
    print(f"  {'categoría':20} {'activos':>8} {'con texto':>10} {'con url':>8}")
    for cat, n, t, u in rows:
        print(f"  {cat:20} {n:8} {t:10} {u:8}")


async def main() -> None:
    print(f"Modo: {'APPLY' if APPLY else 'DRY-RUN'}{' + FORCE' if FORCE else ''}")
    print(f"Entradas redactadas: {len(ALL)}")

    problems = check()
    if problems:
        print("\nProblemas de calidad en market_content (no se escribe nada):")
        for p in problems:
            print("  -", p)
        await engine.dispose()
        sys.exit(1)
    print("[0] market_content.check(): OK")

    async with engine.begin() as conn:
        for s in SCHEMA_STMTS:
            await conn.execute(text(s))
        print("[1] columnas rules / context / resolution_source_url garantizadas")

        await resumen(conn, "Estado actual:")

        activos = (await conn.execute(
            text(f"SELECT id, resolution_source_url, rules FROM markets WHERE {ACTIVE} ORDER BY id")
        )).all()
        ids_activos = {r[0] for r in activos}
        faltan = sorted(ids_activos - set(ALL))
        sobran = sorted(set(ALL) - ids_activos)
        print(f"\n[2] activos en BD: {len(ids_activos)} · sin entrada redactada: {len(faltan)} · entradas sin mercado activo: {len(sobran)}")
        if faltan:
            print("    FALTAN:", ", ".join(faltan))
        if sobran:
            print("    (resueltos/borrados, se ignoran):", ", ".join(sobran))
        if faltan and not ALLOW_MISSING:
            print("\nCobertura incompleta: agrega las entradas o corre con ALLOW_MISSING=1.")
            await engine.dispose()
            sys.exit(1)

        # Preview
        a_escribir = [r for r in activos if r[0] in ALL and (FORCE or r[2] is None)]
        url_nueva = [r for r in activos if r[0] in ALL and r[1] is None and ALL[r[0]]["source_url"]]
        sin_url = sorted(mid for mid in ids_activos if mid in ALL and not ALL[mid]["source_url"])
        print(f"\n[3] rules/context a escribir: {len(a_escribir)} · URLs nuevas: {len(url_nueva)} · quedarán sin URL (con 'Cómo se resuelve'): {len(sin_url)}")
        print("    sin URL:", ", ".join(sin_url) if sin_url else "(ninguno)")

        if not APPLY:
            print("\nDry-run: nada escrito. Repite con APPLY=1 para aplicar.")
            await engine.dispose()
            return

        n_txt = n_url = 0
        for mid, _url, _rules in activos:
            if mid not in ALL:
                continue
            e = ALL[mid]
            if FORCE or _rules is None:
                r = await conn.execute(
                    text("UPDATE markets SET rules = :r, context = :c WHERE id = :id"),
                    {"r": e["rules"], "c": e["context"], "id": mid},
                )
                n_txt += r.rowcount
            if e["source_url"]:
                r = await conn.execute(
                    text("UPDATE markets SET resolution_source_url = :u WHERE id = :id AND resolution_source_url IS NULL"),
                    {"u": e["source_url"], "id": mid},
                )
                n_url += r.rowcount
        print(f"\nAplicado: rules/context={n_txt} · resolution_source_url={n_url}")

    async with engine.connect() as conn:
        await resumen(conn, "Estado final:")
        n_null = (await conn.execute(text(
            f"SELECT count(*) FROM markets WHERE {ACTIVE} AND (rules IS NULL OR context IS NULL)"
        ))).scalar()
        sin_url_db = (await conn.execute(text(
            f"SELECT id FROM markets WHERE {ACTIVE} AND resolution_source_url IS NULL ORDER BY id"
        ))).scalars().all()
        print(f"\nVerificación: {n_null} activos sin rules/context (esperado 0)")
        print(f"              {len(sin_url_db)} activos sin URL (esperado {len(sin_url)}):", ", ".join(sin_url_db) or "(ninguno)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
