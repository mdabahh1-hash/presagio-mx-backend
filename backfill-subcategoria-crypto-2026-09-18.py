"""
Backfill de subcategoría en los mercados Crypto ya sembrados (2026-09-18).

Los 12 mercados Crypto de prod tienen subcategory NULL; la landing de Crypto
(veredikt-mx, components/crypto) los agrupa por subcategoría. Mapeo fijo abajo;
cripto-cap-4t-2026 y cinco-criptos-100b-2026 se quedan sin subcategoría ("Otros").
Solo toca filas de category CRYPTO con subcategory NULL (idempotente).

Guarda de la escalera: la landing arma la escalera del mes agrupando binarios de
la misma subcategoría con ends_at idéntico. Los mercados de aquí no pasan por
tests/test_escaleras_crypto.py (no están en el YAML), así que si alguno cerrara
el mismo instante que una escalera nueva se colaría en ella. El dry-run imprime
ends_at de cada uno y marca CHOCA; con un choque sale con código 1 y no escribe.

Dry-run por defecto; APPLY=1 escribe.
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-subcategoria-crypto-2026-09-18.py'
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-subcategoria-crypto-2026-09-18.py'
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

APPLY = os.environ.get("APPLY") == "1"

MAPEO = {
    "bitcoin-150k": "Bitcoin",
    "btc-cierre-100k-2026": "Bitcoin",
    "btc-cierre-diario-60k-2026": "Bitcoin",
    "btc-dominancia-60-2026": "Bitcoin",
    "btc-toca-120k-2026": "Bitcoin",
    "eth-cierre-3000-2026": "Ethereum",
    "sol-cierre-150-2026": "Solana",
    "stablecoins-350b-2026": "Stablecoins",
    "ley-estructura-mercado-cripto-2026": "Regulación",
    "eeuu-compra-bitcoin-2026": "Regulación",
}

# Cierre de las escaleras sembradas en mercados-pendientes.yaml (sep-2026)
CIERRE_ESCALERA = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)


async def main() -> int:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, subcategory, ends_at, market_type, status FROM markets "
            "WHERE category = 'CRYPTO' ORDER BY ends_at, id"
        ))).all()

    choques = 0
    pendientes = []
    print(f"{'id':38} {'subcategoría':14} {'ends_at (UTC)':20} tipo    estado")
    for id_, sub, ends_at, mtype, status in rows:
        nueva = MAPEO.get(id_)
        destino = sub or nueva
        ends_utc = ends_at if ends_at.tzinfo else ends_at.replace(tzinfo=timezone.utc)
        marca = ""
        if destino and ends_utc == CIERRE_ESCALERA:
            marca = "  CHOCA"
            choques += 1
        if sub is None and nueva:
            pendientes.append(id_)
            etiqueta = f"-> {nueva}"
        else:
            etiqueta = sub or "(sin)"
        print(f"{id_:38} {etiqueta:14} {ends_utc:%Y-%m-%d %H:%M}     {mtype:7} {status}{marca}")

    faltan = sorted(set(MAPEO) - {r[0] for r in rows})
    if faltan:
        print(f"\nIds del mapeo que no existen en la BD: {faltan}")
    print(f"\n{len(pendientes)} mercados recibirían subcategoría; {choques} choques con la escalera ({CIERRE_ESCALERA:%Y-%m-%d %H:%M} UTC).")

    if choques:
        print("CHOCA: revisar antes de aplicar. No se escribe nada.")
        await engine.dispose()
        return 1
    if not APPLY:
        print("Dry-run. Correr con APPLY=1 para escribir.")
        await engine.dispose()
        return 0

    async with engine.begin() as conn:
        n = 0
        for id_ in pendientes:
            r = await conn.execute(text(
                "UPDATE markets SET subcategory = :sub "
                "WHERE id = :id AND category = 'CRYPTO' AND subcategory IS NULL"
            ), {"sub": MAPEO[id_], "id": id_})
            n += r.rowcount
    print(f"Actualizados: {n}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
