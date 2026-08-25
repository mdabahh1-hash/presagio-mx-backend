"""
Backfill liquidez LMSR b=100 → b=1000 en mercados ABIERTOS (2026-08-25).

Con la economía de 10,000 PT las apuestas son 10× más grandes y b=100 hace que
una compra de 200 PT mueva el precio ~43 pts. Subir b a 1000 restaura la
sensibilidad previa (1,000 PT mueven lo que antes movían 100 PT).

Los precios actuales NO deben saltar: el precio LMSR depende de q/b, así que
las q se reescalan por k = 1000/b junto con el cambio de b:
  binarios → markets.q_yes, markets.q_no · multi → market_outcomes.q
Los precios cacheados (markets.yes_price, market_outcomes.price) quedan
intactos y la verificación recalcula el precio desde q/b para confirmarlo.

Idempotente: solo toca mercados con status='OPEN' y b <> 1000 (k se deriva del
b actual, re-ejecutar es no-op). Resueltos/cerrados no se tocan (ya no operan).

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-liquidez-b1000-2026-08-25.py'
"""
import asyncio
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

B_NEW = 1000.0


async def main() -> None:
    async with engine.begin() as conn:
        # [1] Multi primero: k usa el b viejo de markets, así que las outcomes
        #     se reescalan ANTES de tocar markets.b.
        r1 = await conn.execute(text(
            "UPDATE market_outcomes o SET q = o.q * (:bn / m.b) "
            "FROM markets m WHERE m.id = o.market_id "
            "AND m.status = 'OPEN' AND m.b <> :bn"
        ), {"bn": B_NEW})
        print(f"[1] market_outcomes.q reescaladas: {r1.rowcount} filas")

        # [2] Binarios + b: el RHS lee los valores viejos de la fila (semántica
        #     SQL), así que q y b cambian de forma consistente en un statement.
        r2 = await conn.execute(text(
            "UPDATE markets SET q_yes = q_yes * (:bn / b), q_no = q_no * (:bn / b), b = :bn "
            "WHERE status = 'OPEN' AND b <> :bn"
        ), {"bn": B_NEW})
        print(f"[2] markets actualizados a b={B_NEW:g}: {r2.rowcount}")

    # Verificación: precio recalculado desde q/b == precio cacheado (sin saltos)
    async with engine.connect() as conn:
        print("\nVerificación binarios (recalc vs cache):")
        rows = (await conn.execute(text(
            "SELECT id, b, q_yes, q_no, yes_price FROM markets "
            "WHERE status = 'OPEN' AND market_type = 'binary' ORDER BY id"
        ))).all()
        worst = 0.0
        for mid, b, qy, qn, cached in rows:
            recalc = 100.0 / (1.0 + math.exp((qn - qy) / b))
            worst = max(worst, abs(recalc - cached))
            flag = "" if abs(recalc - cached) < 0.51 else "  ⚠️"
            print(f"  {mid:48} b={b:g} cache={cached:6.2f} recalc={recalc:6.2f}{flag}")

        print("\nVerificación multi (peor delta por mercado):")
        rows = (await conn.execute(text(
            "SELECT m.id, m.b, o.outcome_key, o.q, o.price FROM markets m "
            "JOIN market_outcomes o ON o.market_id = m.id "
            "WHERE m.status = 'OPEN' ORDER BY m.id, o.outcome_key"
        ))).all()
        by_market: dict[str, list] = {}
        for mid, b, key, q, price in rows:
            by_market.setdefault(mid, []).append((b, key, q, price))
        for mid, outs in by_market.items():
            b = outs[0][0]
            denom = sum(math.exp(q / b) for _, _, q, _ in outs)
            delta = max(abs(100.0 * math.exp(q / b) / denom - price) for _, _, q, price in outs)
            worst = max(worst, delta)
            flag = "" if delta < 0.51 else "  ⚠️"
            print(f"  {mid:48} b={b:g} peor delta={delta:.2f} pts{flag}")

        n_pend = (await conn.execute(text(
            "SELECT COUNT(*) FROM markets WHERE status = 'OPEN' AND b <> :bn"
        ), {"bn": B_NEW})).scalar_one()
        print(f"\nMercados OPEN pendientes de migrar: {n_pend} · peor delta global: {worst:.2f} pts")

    await engine.dispose()


asyncio.run(main())
