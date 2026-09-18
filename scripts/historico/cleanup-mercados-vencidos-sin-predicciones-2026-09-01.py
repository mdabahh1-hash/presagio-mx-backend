"""
Limpieza de mercados vencidos SIN predicciones (2026-09-01).

Borra (hard delete) los mercados que ya cerraron y siguen sin resolver
(status OPEN o PENDING_RESOLUTION con ends_at < NOW()) y que no tienen NINGUNA
actividad: num_trades = 0, volume = 0 y cero filas en trades, positions,
league_predictions y league_cycle_markets. Sin trades no hay posiciones ni
ledger que reconciliar, por eso se borran en vez de marcarlos CANCELLED.

Se llevan consigo sus filas hijas: price_history (la fila inicial de la
siembra), market_outcomes (multi) y comments (un comentario no es una
predicción; el conteo se reporta). Ninguna FK a markets tiene ON DELETE
CASCADE, así que el borrado va hijos → padre en UNA transacción; cualquier
conteo inesperado levanta RuntimeError y hace rollback de todo.

Los mercados vencidos CON actividad se listan pero NO se tocan: hay que
resolverlos en /admin.

Dry-run por default; APPLY=1 ejecuta. Re-ejecutable: selecciona por criterio
en cada corrida (útil tras cada jornada de seeds 1X2). En APPLY el reporte y
los borrados corren en la misma transacción con los mercados bajo
FOR UPDATE, así nada se cuela entre leer y borrar.

PREREQUISITO: tener desplegado el guard de app/services/seed.py (solo siembra
con la tabla vacía). Con el sembrador viejo, cualquier id de sus listas que se
borre (p. ej. fed-recorte) resucita en el siguiente arranque; el script marca
con "⚠️ seed" los candidatos afectados.

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python cleanup-mercados-vencidos-sin-predicciones-2026-09-01.py'
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python cleanup-mercados-vencidos-sin-predicciones-2026-09-01.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import bindparam, text
from app.database import engine
from app.services.seed import JUNE_2026_MARKETS, SEED_MARKETS

APPLY = os.getenv("APPLY") == "1"
SEED_IDS = {d["id"] for d in JUNE_2026_MARKETS + SEED_MARKETS}

EXPIRED = "m.status IN ('OPEN', 'PENDING_RESOLUTION') AND m.ends_at < NOW()"
SIN_ACTIVIDAD = (
    "m.num_trades = 0 AND m.volume = 0"
    " AND NOT EXISTS (SELECT 1 FROM trades t WHERE t.market_id = m.id)"
    " AND NOT EXISTS (SELECT 1 FROM positions p WHERE p.market_id = m.id)"
    " AND NOT EXISTS (SELECT 1 FROM league_predictions lp WHERE lp.market_id = m.id)"
    " AND NOT EXISTS (SELECT 1 FROM league_cycle_markets lcm WHERE lcm.market_id = m.id)"
)

CANDIDATES_SQL = f"""
SELECT m.id, m.status::text AS status, m.market_type, m.subcategory, m.ends_at,
       (SELECT COUNT(*) FROM market_outcomes o WHERE o.market_id = m.id) AS n_outcomes,
       (SELECT COUNT(*) FROM price_history ph WHERE ph.market_id = m.id) AS n_history,
       (SELECT COUNT(*) FROM comments c WHERE c.market_id = m.id) AS n_comments
FROM markets m
WHERE {EXPIRED} AND {SIN_ACTIVIDAD}
ORDER BY m.ends_at, m.id
"""

EXCLUDED_SQL = f"""
SELECT m.id, m.status::text AS status, m.ends_at, m.num_trades, m.volume,
       (SELECT COUNT(*) FROM trades t WHERE t.market_id = m.id) AS n_trades,
       (SELECT COUNT(*) FROM positions p WHERE p.market_id = m.id) AS n_positions,
       (SELECT COUNT(*) FROM league_predictions lp WHERE lp.market_id = m.id) AS n_picks,
       (SELECT COUNT(*) FROM league_cycle_markets lcm WHERE lcm.market_id = m.id) AS n_cycles
FROM markets m
WHERE {EXPIRED} AND NOT ({SIN_ACTIVIDAD})
ORDER BY m.ends_at, m.id
"""

STATUS_SQL = "SELECT status::text, COUNT(*) FROM markets GROUP BY 1 ORDER BY 1"

# Orden hijos → padre (ninguna FK tiene ON DELETE CASCADE). El segundo campo es
# el rowcount esperado: un int fijo, o la clave del conteo tomado bajo el lock.
CHILD_DELETES = (
    ("league_predictions", 0),
    ("league_cycle_markets", 0),
    ("comments", "n_comments"),
    ("price_history", "n_history"),
    ("positions", 0),
    ("trades", 0),
    ("market_outcomes", "n_outcomes"),
)
SUM_KEYS = ("n_outcomes", "n_history", "n_comments")


def _in_ids(sql: str):
    return text(sql).bindparams(bindparam("ids", expanding=True))


async def _report(conn, lock: bool) -> list:
    """Imprime excluidos y candidatos; devuelve las filas candidatas."""
    excluded = (await conn.execute(text(EXCLUDED_SQL))).mappings().all()
    print(f"\n[0] Vencidos CON actividad (NO se tocan, resolver en /admin): {len(excluded)}")
    if excluded:
        print(f"    {'id':48} {'status':19} {'ends_at':16} {'trades':>6} {'pos':>4} {'picks':>5} {'ciclos':>6}")
        for r in excluded:
            print(f"    {r['id'][:48]:48} {r['status']:19} {r['ends_at']:%Y-%m-%d %H:%M} "
                  f"{r['n_trades']:>6} {r['n_positions']:>4} {r['n_picks']:>5} {r['n_cycles']:>6}")

    sql = CANDIDATES_SQL + (" FOR UPDATE OF m" if lock else "")
    rows = (await conn.execute(text(sql))).mappings().all()
    print(f"\n[1] Candidatos a borrar (vencidos, sin resolver, sin actividad): {len(rows)}")
    if rows:
        print(f"    {'id':48} {'status':19} {'tipo':6} {'subcat':16} {'ends_at':16} {'out':>3} {'hist':>4} {'com':>3}")
        for r in rows:
            flag = "  ⚠️ seed" if r["id"] in SEED_IDS else ""
            print(f"    {r['id'][:48]:48} {r['status']:19} {r['market_type']:6} {(r['subcategory'] or '-')[:16]:16} "
                  f"{r['ends_at']:%Y-%m-%d %H:%M} {r['n_outcomes']:>3} {r['n_history']:>4} {r['n_comments']:>3}{flag}")
        tot = {k: sum(r[k] for r in rows) for k in SUM_KEYS}
        print(f"    Total: {len(rows)} mercados · {tot['n_outcomes']} outcomes · "
              f"{tot['n_history']} price_history · {tot['n_comments']} comments")
        overlap = sorted({r["id"] for r in rows} & SEED_IDS)
        if overlap:
            print(f"    ⚠️ En listas de app/services/seed.py: {', '.join(overlap)} — requiere el guard "
                  "de seed_markets() desplegado; si no, resucitan en el siguiente arranque.")
    return rows


async def main() -> None:
    print(f"MODO: {'APPLY' if APPLY else 'DRY-RUN (APPLY=1 para ejecutar)'}")
    ids: list[str] = []

    if not APPLY:
        async with engine.connect() as conn:
            await _report(conn, lock=False)
        print("\nDRY-RUN: no se borró nada.")
    else:
        async with engine.begin() as conn:
            rows = await _report(conn, lock=True)
            ids = [r["id"] for r in rows]
            if not ids:
                print("\nNada que borrar.")
            else:
                expected = {k: sum(r[k] for r in rows) for k in SUM_KEYS}
                step = 2
                for table, exp in CHILD_DELETES:
                    want = exp if isinstance(exp, int) else expected[exp]
                    r = await conn.execute(_in_ids(f"DELETE FROM {table} WHERE market_id IN :ids"), {"ids": ids})
                    print(f"[{step}] {table}: {r.rowcount} filas borradas (esperado {want})")
                    if r.rowcount != want:
                        raise RuntimeError(f"{table}: borradas {r.rowcount} ≠ esperado {want} → rollback")
                    step += 1
                r = await conn.execute(_in_ids(
                    "DELETE FROM markets WHERE id IN :ids "
                    "AND status IN ('OPEN', 'PENDING_RESOLUTION') AND num_trades = 0"
                ), {"ids": ids})
                print(f"[{step}] markets: {r.rowcount} filas borradas (esperado {len(ids)})")
                if r.rowcount != len(ids):
                    raise RuntimeError(f"markets: borradas {r.rowcount} ≠ esperado {len(ids)} → rollback")
                print("\nIds borrados:\n  " + " ".join(ids))

    # Verificación (conexión nueva para leer lo confirmado)
    async with engine.connect() as conn:
        print("\nVerificación:")
        for s, n in (await conn.execute(text(STATUS_SQL))).all():
            print(f"  {s:20} {n}")
        remaining = (await conn.execute(text(
            f"SELECT COUNT(*) FROM markets m WHERE {EXPIRED} AND {SIN_ACTIVIDAD}"
        ))).scalar_one()
        expired_total = (await conn.execute(text(
            f"SELECT COUNT(*) FROM markets m WHERE {EXPIRED}"
        ))).scalar_one()
        print(f"  Candidatos restantes: {remaining} · vencidos sin resolver con actividad: {expired_total - remaining}")
        if ids:
            still = (await conn.execute(
                _in_ids("SELECT COUNT(*) FROM markets WHERE id IN :ids"), {"ids": ids}
            )).scalar_one()
            print(f"  Ids borrados que siguen existiendo: {still}" + ("" if still == 0 else "  ⚠️"))

    await engine.dispose()


asyncio.run(main())
