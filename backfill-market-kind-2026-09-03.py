"""
Backfill markets.kind (2026-09-03).

Tercer nivel del rail de Deportes: deporte → liga (subcategory) → tipo (kind).
  - 'partido'   : ganador del juego (1X2 de fútbol, ganador NFL)
  - 'accesorio' : todo lo demás (props de jugador, titulares, premios, futuros, fantasy)

Regla, solo para category = 'DEPORTES' y subcategory en SPLIT_SUBS (ligas de
fútbol + NFL):
  partido   = market_type = 'multi' AND (
                outcome_keys == {local, empate, visitante}          -- 1X2
                OR (id ~ '^nfl-<equipo>-<equipo>-s<n>-<año>$' AND 2 outcomes)
              )
  accesorio = el resto
F1, Boxeo, mercados sin subcategory y MUNDIAL_2026 se dejan en NULL a
propósito (no tienen la división en el frontend).

Idempotente: solo escribe donde kind IS NULL. Dry-run por default; APPLY=1
escribe; FORCE=1 primero resetea kind en DEPORTES y reclasifica todo.
Garantiza la columna con ADD COLUMN IF NOT EXISTS para poder correr antes
del deploy que la crea en el boot (app.database.migrate_columns).

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-market-kind-2026-09-03.py'
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-market-kind-2026-09-03.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

APPLY = os.environ.get("APPLY") == "1"
FORCE = os.environ.get("FORCE") == "1"

SCHEMA_STMTS = [
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS kind VARCHAR(20)",
    "CREATE INDEX IF NOT EXISTS ix_markets_kind ON markets (kind)",
]

# Debe coincidir con SPORT_GROUPS['Fútbol'] + 'NFL' del frontend (src/lib/categories.ts).
FOOTBALL = [
    "Liga MX", "Leagues Cup", "Premier League", "LaLiga", "Serie A", "Bundesliga",
    "Ligue 1", "Liga Portugal", "MLS", "Champions League", "Saudi Pro League",
]
SPLIT_SUBS = FOOTBALL + ["NFL"]

NFL_MATCH_RE = r"^nfl-[a-z0-9]+-[a-z0-9]+-s\d+-\d{4}$"

# m.* = markets. Un partido es multi con salidas 1X2 exactas, o un ganador NFL
# (id de partido y exactamente 2 salidas).
PARTIDO_WHERE = """
    m.category = 'DEPORTES'
    AND m.market_type = 'multi'
    AND m.subcategory = ANY(:subs)
    AND (
        (SELECT array_agg(o.outcome_key ORDER BY o.outcome_key)
           FROM market_outcomes o WHERE o.market_id = m.id)
        = ARRAY['empate', 'local', 'visitante']::varchar[]
        OR (
            m.id ~ :nfl_re
            AND (SELECT count(*) FROM market_outcomes o WHERE o.market_id = m.id) = 2
        )
    )
"""
ACCESORIO_WHERE = """
    m.category = 'DEPORTES'
    AND m.subcategory = ANY(:subs)
"""
PARAMS = {"subs": SPLIT_SUBS, "nfl_re": NFL_MATCH_RE}


async def breakdown(conn, title: str) -> None:
    rows = (await conn.execute(text("""
        SELECT subcategory, kind, count(*) AS n
          FROM markets
         WHERE category = 'DEPORTES'
         GROUP BY subcategory, kind
         ORDER BY subcategory NULLS LAST, kind NULLS LAST
    """))).all()
    print(f"\n{title}")
    for sub, kind, n in rows:
        print(f"  {str(sub):20} {str(kind):10} {n:4}")


async def main() -> None:
    print(f"Modo: {'APPLY' if APPLY else 'DRY-RUN'}{' + FORCE' if FORCE else ''}")
    async with engine.begin() as conn:
        for s in SCHEMA_STMTS:
            await conn.execute(text(s))
        print("[0] columna markets.kind garantizada")

        await breakdown(conn, "Estado actual (subcategory / kind / n):")

        # Preview de lo que se escribiría (respetando kind IS NULL salvo FORCE)
        null_clause = "" if FORCE else " AND m.kind IS NULL"
        n_partido = (await conn.execute(
            text(f"SELECT count(*) FROM markets m WHERE {PARTIDO_WHERE}{null_clause}"), PARAMS
        )).scalar()
        n_acc = (await conn.execute(
            text(f"SELECT count(*) FROM markets m WHERE {ACCESORIO_WHERE}{null_clause}"), PARAMS
        )).scalar() - n_partido
        print(f"\n[1] partido   → {n_partido} filas")
        print(f"[2] accesorio → {n_acc} filas")

        ids = (await conn.execute(
            text(f"SELECT m.id FROM markets m WHERE {PARTIDO_WHERE}{null_clause} ORDER BY m.id"), PARAMS
        )).scalars().all()
        print("    partidos:", ", ".join(ids) if ids else "(ninguno)")

        if not APPLY:
            print("\nDry-run: nada escrito. Repite con APPLY=1 para aplicar.")
            await engine.dispose()
            return

        if FORCE:
            r = await conn.execute(text("UPDATE markets SET kind = NULL WHERE category = 'DEPORTES'"))
            print(f"\nFORCE: kind reseteado en {r.rowcount} mercados de DEPORTES")

        r1 = await conn.execute(
            text(f"UPDATE markets m SET kind = 'partido' WHERE {PARTIDO_WHERE} AND m.kind IS NULL"), PARAMS
        )
        r2 = await conn.execute(
            text(f"UPDATE markets m SET kind = 'accesorio' WHERE {ACCESORIO_WHERE} AND m.kind IS NULL"), PARAMS
        )
        print(f"\nAplicado: partido={r1.rowcount} accesorio={r2.rowcount}")

    async with engine.connect() as conn:
        await breakdown(conn, "Estado final (subcategory / kind / n):")
        n_null = (await conn.execute(
            text("SELECT count(*) FROM markets WHERE category = 'DEPORTES' AND subcategory = ANY(:subs) AND kind IS NULL"),
            {"subs": SPLIT_SUBS},
        )).scalar()
        print(f"\nVerificación: {n_null} mercados de fútbol/NFL sin kind (esperado 0)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
