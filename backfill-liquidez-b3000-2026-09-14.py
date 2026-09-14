"""
Backfill liquidez LMSR → b=3000 en mercados OPEN y PENDING_RESOLUTION (2026-09-14).

Dos problemas:
  - Los mercados sembrados entre el 26-ago y el 4-sep con scripts viejos
    quedaron en b=100/150/50 (después del backfill b1000 del 25-ago): ahí una
    apuesta de 1,000 PT lleva un binario de 50% a 100%.
  - Aun con b=1000, 1,000 PT mueven 50→82%. El estándar nuevo es b=3000
    (1,000 PT: 50→64%), igual que seeds/plantillas.py:B_DEFAULT.

Los precios actuales NO saltan: el precio LMSR depende de q/b, así que las q se
reescalan por k = 3000/b junto con el cambio de b:
  binarios → markets.q_yes, markets.q_no · multi → market_outcomes.q
Las posiciones (shares) no cambian. Idempotente (solo toca b <> 3000).

Dry-run por defecto; APPLY=1 escribe.
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-liquidez-b3000-2026-09-14.py'
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-liquidez-b3000-2026-09-14.py'
"""
import asyncio
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

B_NEW = 3000.0
APPLY = os.environ.get("APPLY") == "1"
ACTIVOS = "('OPEN', 'PENDING_RESOLUTION')"


async def main() -> None:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT b, market_type, COUNT(*), COUNT(*) FILTER (WHERE num_trades > 0) "
            f"FROM markets WHERE status IN {ACTIVOS} AND b <> :bn "
            f"GROUP BY b, market_type ORDER BY b"
        ), {"bn": B_NEW})).all()
        print(f"Mercados activos a migrar a b={B_NEW:g}:")
        for b, mtype, n, con_trades in rows:
            print(f"  b={b:>6g}  {mtype:6}  {n:4} mercados  ({con_trades} con trades)")
        if not rows:
            print("  ninguno")

    if not APPLY:
        print("\nDry-run. Correr con APPLY=1 para escribir.")
        await engine.dispose()
        return

    async with engine.begin() as conn:
        # [1] Multi primero: k usa el b viejo de markets, así que las outcomes
        #     se reescalan ANTES de tocar markets.b.
        r1 = await conn.execute(text(
            "UPDATE market_outcomes o SET q = o.q * (:bn / m.b) "
            f"FROM markets m WHERE m.id = o.market_id "
            f"AND m.status IN {ACTIVOS} AND m.b <> :bn"
        ), {"bn": B_NEW})
        print(f"\n[1] market_outcomes.q reescaladas: {r1.rowcount} filas")

        # [2] Binarios + b: el RHS lee los valores viejos de la fila (semántica
        #     SQL), así que q y b cambian de forma consistente en un statement.
        r2 = await conn.execute(text(
            "UPDATE markets SET q_yes = q_yes * (:bn / b), q_no = q_no * (:bn / b), b = :bn "
            f"WHERE status IN {ACTIVOS} AND b <> :bn"
        ), {"bn": B_NEW})
        print(f"[2] markets actualizados a b={B_NEW:g}: {r2.rowcount}")

    # Verificación: precio recalculado desde q/b == precio cacheado (sin saltos)
    async with engine.connect() as conn:
        worst = 0.0
        rows = (await conn.execute(text(
            f"SELECT id, b, q_yes, q_no, yes_price FROM markets "
            f"WHERE status IN {ACTIVOS} AND market_type = 'binary' ORDER BY id"
        ))).all()
        for mid, b, qy, qn, cached in rows:
            delta = abs(100.0 / (1.0 + math.exp((qn - qy) / b)) - cached)
            worst = max(worst, delta)
            if delta >= 0.51:
                print(f"  ⚠️ {mid} b={b:g} cache={cached:.2f} delta={delta:.2f}")

        rows = (await conn.execute(text(
            "SELECT m.id, m.b, o.q, o.price FROM markets m "
            "JOIN market_outcomes o ON o.market_id = m.id "
            f"WHERE m.status IN {ACTIVOS} ORDER BY m.id"
        ))).all()
        by_market: dict[str, list] = {}
        for mid, b, q, price in rows:
            by_market.setdefault(mid, []).append((b, q, price))
        for mid, outs in by_market.items():
            b = outs[0][0]
            denom = sum(math.exp(q / b) for _, q, _ in outs)
            delta = max(abs(100.0 * math.exp(q / b) / denom - price) for _, q, price in outs)
            worst = max(worst, delta)
            if delta >= 0.51:
                print(f"  ⚠️ {mid} (multi) b={b:g} peor delta={delta:.2f} pts")

        n_pend = (await conn.execute(text(
            f"SELECT COUNT(*) FROM markets WHERE status IN {ACTIVOS} AND b <> :bn"
        ), {"bn": B_NEW})).scalar_one()
        print(f"\nPendientes de migrar: {n_pend} · peor delta global: {worst:.2f} pts")

    await engine.dispose()


asyncio.run(main())
