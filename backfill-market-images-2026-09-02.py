"""
Backfill markets.image_url (2026-09-02).

Asigna una imagen cuadrada a cada mercado, en este orden de prioridad:
  1. MARKET_IMAGES  — por id (escudos, fotos; lote específico, vacío al inicio)
  2. SUB_IMAGES     — por subcategoría (liga/competencia) donde image_url IS NULL
  3. CAT_IMAGES     — por categoría (nombre del enum) donde image_url IS NULL

Las rutas son relativas al frontend (public/img/markets/...); el frontend
también tiene este mismo fallback estático, así que el script solo hace
persistente lo que ya se ve. Idempotente. Dry-run por default; APPLY=1 escribe;
FORCE=1 reescribe también los que ya tienen imagen (solo niveles 2 y 3).

Correr contra prod:
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-market-images-2026-09-02.py'
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
    "ALTER TABLE markets ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)",
]

# id → ruta. Segundo lote (escudos por partido, fotos de personas).
MARKET_IMAGES: dict[str, str] = {}

SUB_IMAGES: dict[str, str] = {
    "Liga MX": "/img/markets/sub/liga-mx.svg",
    "Leagues Cup": "/img/markets/sub/leagues-cup.svg",
    "Premier League": "/img/markets/sub/premier-league.svg",
    "LaLiga": "/img/markets/sub/laliga.svg",
    "Serie A": "/img/markets/sub/serie-a.svg",
    "Bundesliga": "/img/markets/sub/bundesliga.svg",
    "Ligue 1": "/img/markets/sub/ligue-1.svg",
    "Liga Portugal": "/img/markets/sub/liga-portugal.svg",
    "MLS": "/img/markets/sub/mls.svg",
    "Champions League": "/img/markets/sub/champions-league.svg",
    "Saudi Pro League": "/img/markets/sub/saudi-pro-league.svg",
    "NFL": "/img/markets/sub/nfl.svg",
    "F1": "/img/markets/sub/f1.svg",
    "Boxeo": "/img/markets/sub/boxeo.svg",
    "Elecciones": "/img/markets/sub/elecciones.svg",
}

# La BD guarda el NOMBRE del enum MarketCategory.
CAT_IMAGES: dict[str, str] = {
    "DEPORTES": "/img/markets/cat/deportes.svg",
    "POLITICA_MX": "/img/markets/cat/politica.svg",
    "ECONOMIA": "/img/markets/cat/economia.svg",
    "CRYPTO": "/img/markets/cat/crypto.svg",
    "TECH": "/img/markets/cat/tech.svg",
    "GLOBAL": "/img/markets/cat/global.svg",
    "MERCADOS_GLOBALES": "/img/markets/cat/mercados-globales.svg",
    "MEXICO": "/img/markets/cat/mexico.svg",
    "CLIMA": "/img/markets/cat/clima.svg",
    "ENTRETENIMIENTO": "/img/markets/cat/entretenimiento.svg",
    "MUNDIAL_2026": "/img/markets/cat/deportes.svg",
    "BOXEO": "/img/markets/sub/boxeo.svg",
    "MOTOR": "/img/markets/sub/f1.svg",
}


async def main() -> None:
    print(f"Modo: {'APPLY' if APPLY else 'DRY-RUN'}{' + FORCE' if FORCE else ''}")
    async with engine.begin() as conn:
        for s in SCHEMA_STMTS:
            await conn.execute(text(s))
        print("[0] columna image_url garantizada")

        null_clause = "" if FORCE else " AND image_url IS NULL"

        # Conteos previos (dry-run informativo)
        for mid, path in MARKET_IMAGES.items():
            n = (await conn.execute(text("SELECT COUNT(*) FROM markets WHERE id = :id"), {"id": mid})).scalar()
            print(f"[1] {mid:45} → {path} ({n} fila)")
        for sub, path in SUB_IMAGES.items():
            n = (await conn.execute(
                text(f"SELECT COUNT(*) FROM markets WHERE subcategory = :s{null_clause}"), {"s": sub}
            )).scalar()
            print(f"[2] {sub:20} → {path} ({n} filas)")
        for cat, path in CAT_IMAGES.items():
            n = (await conn.execute(
                text(f"SELECT COUNT(*) FROM markets WHERE category = :c{null_clause}"), {"c": cat}
            )).scalar()
            print(f"[3] {cat:20} → {path} ({n} filas)")

        if not APPLY:
            print("\nDry-run: nada escrito. Repite con APPLY=1 para aplicar.")
            return

        total = 0
        for mid, path in MARKET_IMAGES.items():
            r = await conn.execute(text("UPDATE markets SET image_url = :p WHERE id = :id"), {"p": path, "id": mid})
            total += r.rowcount
        for sub, path in SUB_IMAGES.items():
            r = await conn.execute(
                text(f"UPDATE markets SET image_url = :p WHERE subcategory = :s{null_clause}"), {"p": path, "s": sub}
            )
            total += r.rowcount
        for cat, path in CAT_IMAGES.items():
            r = await conn.execute(
                text(f"UPDATE markets SET image_url = :p WHERE category = :c{null_clause}"), {"p": path, "c": cat}
            )
            total += r.rowcount
        print(f"\nAplicado: {total} filas actualizadas")

    async with engine.connect() as conn:
        n_null = (await conn.execute(text("SELECT COUNT(*) FROM markets WHERE image_url IS NULL"))).scalar()
        n_all = (await conn.execute(text("SELECT COUNT(*) FROM markets"))).scalar()
        print(f"Verificación: {n_all - n_null}/{n_all} mercados con image_url")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
