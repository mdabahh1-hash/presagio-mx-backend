"""
Backfill saldo de bienvenida 1,000 → 10,000 PT (2026-08-25).

Acredita +DELTA PT a TODOS los usuarios existentes y registra una fila
points_ledger reason='adjustment' por usuario, en UNA sola transacción.

DELTA=9000 → todos quedan como si hubieran empezado con 10,000 PT: el P&L
all-time del leaderboard (points + invertido − NEW_USER_POINTS) no cambia al
subir NEW_USER_POINTS a 10,000, y el chart de puntos (walk-back sobre el
ledger) muestra el abono en su fecha real.

Idempotente: aborta si ya existe cualquier fila reason='adjustment'.

Correr contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-welcome-10k-2026-08-25.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

DELTA = 9000.0


async def main() -> None:
    async with engine.begin() as conn:
        # [0] Guard de idempotencia
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM points_ledger WHERE reason = 'adjustment'"
        ))).scalar_one()
        if n:
            print(f"ABORT: ya existen {n} filas reason='adjustment' — backfill ya corrió.")
            return

        # [1] Ledger primero: fija el conjunto exacto de usuarios beneficiados
        r1 = await conn.execute(text(
            "INSERT INTO points_ledger (user_id, delta, reason, created_at) "
            "SELECT id, :d, 'adjustment', NOW() FROM users"
        ), {"d": DELTA})
        print(f"[1] ledger: {r1.rowcount} filas 'adjustment' de +{DELTA:g} PT")

        # [2] Saldos: exactamente el mismo conjunto (la tx ve sus propios inserts),
        #     así un alta a mitad del script jamás recibe medio ajuste.
        r2 = await conn.execute(text(
            "UPDATE users SET points = points + :d WHERE id IN "
            "(SELECT user_id FROM points_ledger WHERE reason = 'adjustment')"
        ), {"d": DELTA})
        print(f"[2] users.points: {r2.rowcount} filas +{DELTA:g} PT")

        if r1.rowcount != r2.rowcount:
            raise RuntimeError(f"Mismatch ledger={r1.rowcount} vs users={r2.rowcount} → rollback")

    # Verificación (conexión nueva para leer lo confirmado)
    async with engine.connect() as conn:
        total, suma = (await conn.execute(text(
            "SELECT COUNT(*), COALESCE(SUM(delta), 0) FROM points_ledger WHERE reason = 'adjustment'"
        ))).one()
        missing = (await conn.execute(text(
            "SELECT COUNT(*) FROM users WHERE id NOT IN "
            "(SELECT user_id FROM points_ledger WHERE reason = 'adjustment')"
        ))).scalar_one()
        print(f"\nVerificación: {total} ajustes (Σ {suma:g} PT); usuarios sin ajuste: {missing}")
        rows = (await conn.execute(text(
            "SELECT id, username, points FROM users ORDER BY id LIMIT 20"
        ))).all()
        for uid, uname, pts in rows:
            print(f"  {uid:4} {uname:24} {pts:10.2f} PT")

    await engine.dispose()


asyncio.run(main())
