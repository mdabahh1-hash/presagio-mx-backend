"""
Backfill de subcategorías (2026-08-19) + fusión de Boxeo/Motor en Deportes.

Qué hace (idempotente, seguro de re-ejecutar):
  0. Garantiza la columna markets.subcategory + índice (mismas sentencias que
     app.database.migrate_columns, por si corre antes del deploy del backend).
  1. Fútbol multi (81): subcategoría por prefijo de slug, solo category=DEPORTES:
       mx- → Liga MX · pl- → Premier League · laliga- → LaLiga · sa- → Serie A
       bl- → Bundesliga · l1- → Ligue 1 · lp- → Liga Portugal · mls- → MLS
  2. F1: prefijo f1- + ids explícitos de Checo → subcategoría F1.
  3. Leagues Cup: 3 ids explícitos → subcategoría Leagues Cup.
  4. category BOXEO → category DEPORTES + subcategoría Boxeo.
  5. category MOTOR  → category DEPORTES + subcategoría F1.
  6. Política: morena-2027, cdmx-alcalde, xochitl-2030 → subcategoría Elecciones
     (alcalde-metepec-legal, ya resuelto y no electoral, se deja sin subcategoría).

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-subcategorias-2026-08-19.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import bindparam, text
from app.database import engine

SCHEMA_STMTS = [
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS subcategory VARCHAR(50)",
    "CREATE INDEX IF NOT EXISTS ix_markets_subcategory ON markets (subcategory)",
]

LEAGUE_PREFIXES = [
    ("mx-", "Liga MX"),
    ("pl-", "Premier League"),
    ("laliga-", "LaLiga"),
    ("sa-", "Serie A"),
    ("bl-", "Bundesliga"),
    ("l1-", "Ligue 1"),
    ("lp-", "Liga Portugal"),
    ("mls-", "MLS"),
    ("f1-", "F1"),
]

F1_EXTRA_IDS = ["checo-puntos-gp-paises-bajos-26"]

LEAGUES_CUP_IDS = [
    "monterrey-semis-leagues-cup-26",
    "america-semis-leagues-cup-26",
    "liga-mx-gana-leagues-cup-26",
]

ELECCIONES_IDS = ["morena-2027", "cdmx-alcalde", "xochitl-2030"]


async def main() -> None:
    async with engine.begin() as conn:
        for s in SCHEMA_STMTS:
            await conn.execute(text(s))
        print("[0] columna subcategory + índice garantizados")

        for prefix, sub in LEAGUE_PREFIXES:
            r = await conn.execute(
                text(
                    "UPDATE markets SET subcategory = :sub "
                    "WHERE category = 'DEPORTES' AND id LIKE :pat"
                ),
                {"sub": sub, "pat": f"{prefix}%"},
            )
            print(f"[1] {sub:15} ← id {prefix}*  → {r.rowcount} filas")

        r = await conn.execute(
            text("UPDATE markets SET subcategory = 'F1' WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": F1_EXTRA_IDS},
        )
        print(f"[2] F1 (ids Checo extra) → {r.rowcount} filas")

        r = await conn.execute(
            text("UPDATE markets SET subcategory = 'Leagues Cup' WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": LEAGUES_CUP_IDS},
        )
        print(f"[3] Leagues Cup → {r.rowcount} filas")

        r = await conn.execute(
            text(
                "UPDATE markets SET category = 'DEPORTES', subcategory = 'Boxeo' "
                "WHERE category = 'BOXEO'"
            )
        )
        print(f"[4] Boxeo → Deportes/Boxeo → {r.rowcount} filas")

        r = await conn.execute(
            text(
                "UPDATE markets SET category = 'DEPORTES', subcategory = 'F1' "
                "WHERE category = 'MOTOR'"
            )
        )
        print(f"[5] Motor → Deportes/F1 → {r.rowcount} filas")

        r = await conn.execute(
            text("UPDATE markets SET subcategory = 'Elecciones' WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": ELECCIONES_IDS},
        )
        print(f"[6] Elecciones → {r.rowcount} filas")

    # Verificación (conexión nueva para leer lo confirmado)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT category, COALESCE(subcategory, '(sin subcategoría)') AS sub, COUNT(*) "
                    "FROM markets WHERE status = 'OPEN' "
                    "GROUP BY category, sub ORDER BY category, COUNT(*) DESC"
                )
            )
        ).all()
        print("\nMercados ABIERTOS por categoría/subcategoría:")
        for cat, sub, n in rows:
            print(f"  {cat:20} {sub:20} {n}")

        missing = (
            await conn.execute(
                text(
                    "SELECT id, question FROM markets "
                    "WHERE status = 'OPEN' AND category = 'DEPORTES' AND subcategory IS NULL"
                )
            )
        ).all()
        if missing:
            print("\n⚠️  Deportes abiertos SIN subcategoría (revisar):")
            for mid, q in missing:
                print(f"  {mid} | {q[:70]}")
        else:
            print("\n✓ Todos los Deportes abiertos tienen subcategoría")

    await engine.dispose()


asyncio.run(main())
