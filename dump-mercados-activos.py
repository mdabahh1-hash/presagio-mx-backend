"""
Dump de solo lectura de los mercados activos (OPEN + PENDING_RESOLUTION) a JSON.

Base para redactar Normas / Contexto / fuente de resolución por mercado
(ver market_content/ y backfill-normas-contexto-fuente-2026-09-04.py).

Correr contra prod (escribe el JSON a stdout):
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python dump-mercados-activos.py' > mercados-activos.json
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine


async def main() -> None:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT m.id, m.question, m.description, m.category, m.subcategory, m.kind,
                   m.market_type, m.resolution_criteria, m.resolution_source_url,
                   m.status, m.ends_at, m.created_at,
                   COALESCE((SELECT json_agg(json_build_object('key', o.outcome_key, 'label', o.label) ORDER BY o.id)
                               FROM market_outcomes o WHERE o.market_id = m.id), '[]'::json) AS outcomes
              FROM markets m
             WHERE m.status IN ('OPEN', 'PENDING_RESOLUTION')
             ORDER BY m.category, m.subcategory NULLS LAST, m.ends_at, m.id
        """))).mappings().all()
    await engine.dispose()
    out = []
    for r in rows:
        d = dict(r)
        d["ends_at"] = d["ends_at"].isoformat()
        d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print(file=sys.stderr)
    print(f"{len(out)} mercados activos", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
