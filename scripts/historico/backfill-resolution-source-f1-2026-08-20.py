"""
Backfill resolution_source_url (2026-08-20) — piloto F1.

Pone el enlace a la fuente oficial que decide el resultado en los 3 mercados
abiertos del GP de Países Bajos 2026 (Zandvoort, 23 ago):
  - checo-puntos-gp-paises-bajos-26          (binario)
  - f1-paisesbajos-2026-piloto-ganador       (multi)
  - f1-paisesbajos-2026-escuderia-ganadora   (multi)

Fuente: página oficial de resultados de carreras F1 2026 (formula1.com),
la misma que citan los resolution_criteria. Idempotente, seguro de re-ejecutar.

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-resolution-source-f1-2026-08-20.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import bindparam, text
from app.database import engine

SCHEMA_STMTS = [
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS resolution_source_url VARCHAR(500)",
]

F1_RESULTS_URL = "https://www.formula1.com/en/results/2026/races"

ZANDVOORT_IDS = [
    "checo-puntos-gp-paises-bajos-26",
    "f1-paisesbajos-2026-piloto-ganador",
    "f1-paisesbajos-2026-escuderia-ganadora",
]


async def main() -> None:
    async with engine.begin() as conn:
        for s in SCHEMA_STMTS:
            await conn.execute(text(s))
        print("[0] columna resolution_source_url garantizada")

        r = await conn.execute(
            text(
                "UPDATE markets SET resolution_source_url = :url WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"url": F1_RESULTS_URL, "ids": ZANDVOORT_IDS},
        )
        print(f"[1] F1 Zandvoort → {r.rowcount} filas con {F1_RESULTS_URL}")

    # Verificación (conexión nueva para leer lo confirmado)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, resolution_source_url FROM markets WHERE id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": ZANDVOORT_IDS},
            )
        ).all()
        print("\nVerificación:")
        for mid, url in rows:
            print(f"  {mid:45} {url or '(sin url)'}")

    await engine.dispose()


asyncio.run(main())
