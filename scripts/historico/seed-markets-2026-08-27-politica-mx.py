"""
Seed script: 7 mercados BINARIOS (sí/no) de política y economía MX — agosto 2026
(T-MEC, PEF 2027, INE, elección federal 2027).

Mirrors app/services/seed.py (convención binaria: SELECT previo, init_q_for_price, PriceHistory).
Run from the backend directory (prod):
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-08-27-politica-mx.py'

Resolución: manual vía endpoint admin de resolución, tras los cómputos/publicaciones oficiales.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr

MARKETS = [
    {
        "id": "tmec-extension-16-anos-2026",
        "question": "¿El T-MEC será extendido por otros 16 años durante 2026?",
        "description": "En la revisión conjunta del 1 de julio de 2026 EEUU rechazó la extensión y se activaron revisiones anuales hasta 2036, pero el tratado permite acordar la extensión por 16 años en cualquier momento. Resuelve sobre lo que ocurra antes del 31 de diciembre de 2026.",
        "category": MarketCategory.ECONOMIA,
        "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si México, Estados Unidos y Canadá confirman oficialmente antes de las 23:59 del 31 de diciembre de 2026 (hora CDMX) la extensión del T-MEC por 16 años adicionales prevista en el artículo 34.7. Fuente: comunicados oficiales de la Secretaría de Economía, USTR y Global Affairs Canada. Cualquier otro resultado resuelve NO.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 6.0,   # calibrado: EEUU ya rechazó la extensión el 1 jul 2026
        "trending": True,
    },
    {
        "id": "pef-2027-aprobacion-15-nov",
        "question": "¿La Cámara de Diputados aprobará el Presupuesto de Egresos 2027 antes del 15 de noviembre?",
        "description": "La ley fija el 15 de noviembre como fecha límite para aprobar el PEF del año siguiente. Con mayoría calificada de Morena y aliados, históricamente se aprueba a tiempo, pero ha habido sesiones maratónicas de último minuto.",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si la votación final del PEF 2027 en el pleno de la Cámara de Diputados ocurre antes de las 23:59 del 15 de noviembre de 2026, hora CDMX. Fuente: Gaceta Parlamentaria y comunicados oficiales de la Cámara de Diputados. Resuelve NO si la votación ocurre después de esa hora o no ocurre.",
        "ends_at": datetime(2026, 11, 16, 5, 59, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 90.0,  # estimación: mayoría oficialista, cumplimiento casi siempre en plazo
        "trending": False,
    },
    {
        "id": "ine-presupuesto-2027-menor",
        "question": "¿El INE recibirá menos presupuesto en 2027 que en 2026?",
        "description": "Compara la asignación nominal aprobada al INE en el PEF 2027 contra los $21,837,221,581 MXN autorizados para 2026. 2027 es año de elección federal concurrente con 17 gubernaturas, lo que normalmente eleva el presupuesto, pero la Cámara suele recortar la solicitud del instituto y hay reforma electoral en curso.",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si la asignación nominal total aprobada al INE en el PEF 2027 publicado en el DOF es inferior a $21,837,221,581 MXN. Resuelve NO si es igual o superior. Fuente: PEF 2027 publicado en el Diario Oficial de la Federación.",
        "ends_at": datetime(2026, 11, 16, 5, 59, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 22.0,  # estimación: año electoral suele subir el gasto nominal del INE
        "trending": False,
    },
    {
        "id": "participacion-federal-2027-60",
        "question": "¿La participación en la elección federal de 2027 superará el 60%?",
        "description": "Elección intermedia del 6 de junio de 2027, concurrente con 17 gubernaturas. La intermedia de 2021 tuvo participación de alrededor de 52%, así que superar 60% requeriría un salto histórico.",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Elecciones",
        "resolution_criteria": "Resuelve SÍ si el cómputo oficial definitivo del INE para la elección federal de diputados de 2027 registra una participación nacional superior al 60.00%. Fuente: cómputos distritales definitivos del INE.",
        "ends_at": datetime(2027, 6, 6, 14, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 15.0,  # estimación: intermedia 2021 rondó 52%
        "trending": True,
    },
    {
        "id": "morena-250-diputados-2027",
        "question": "¿Morena obtendrá al menos 250 diputados federales en 2027?",
        "description": "Se renuevan las 500 diputaciones el 6 de junio de 2027. El umbral es que Morena por sí solo, sin contar PVEM ni PT, alcance la mitad de la Cámara. La reforma electoral en discusión durante 2026 podría cambiar las reglas de asignación.",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Elecciones",
        "resolution_criteria": "Resuelve SÍ si la asignación definitiva de diputaciones federales 2027, validada por el INE y en su caso el TEPJF, otorga al partido Morena 250 o más de los 500 escaños. Cuenta solo la bancada asignada a Morena en la constancia oficial, no la de sus aliados.",
        "ends_at": datetime(2027, 6, 6, 14, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 50.0,  # estimación: en 2024 Morena solo obtuvo ~236 curules propias
        "trending": True,
    },
    {
        "id": "coalicion-morena-334-diputados-2027",
        "question": "¿Morena, PVEM y PT alcanzarán juntos 334 diputados federales en 2027?",
        "description": "334 escaños equivalen a las dos terceras partes de la Cámara, el umbral para reformas constitucionales. La coalición hoy supera ese número y competirá aliada en casi todo el país, pero las intermedias suelen desgastar al oficialismo.",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Elecciones",
        "resolution_criteria": "Resuelve SÍ si la suma de las diputaciones federales asignadas de forma definitiva a Morena, PVEM y PT tras la elección de 2027, validada por el INE y en su caso el TEPJF, es igual o mayor a 334 de 500. Fuente: constancias oficiales de asignación.",
        "ends_at": datetime(2027, 6, 6, 14, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 58.0,  # estimación: hoy tienen supermayoría pero el umbral es exigente
        "trending": True,
    },
    {
        "id": "morena-10-gubernaturas-2027",
        "question": "¿Morena o sus coaliciones ganarán al menos 10 de las 17 gubernaturas de 2027?",
        "description": "El 6 de junio de 2027 se renuevan 17 gubernaturas. Morena ya gobierna 12 de esos estados y su coalición con PVEM y PT competirá en 16 de las 17 entidades.",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Elecciones",
        "resolution_criteria": "Resuelve SÍ si los cómputos oficiales definitivos, validados por los OPLE y en su caso los tribunales electorales, dan el triunfo a candidaturas de Morena o de coaliciones que incluyan a Morena en 10 o más de las 17 gubernaturas disputadas el 6 de junio de 2027.",
        "ends_at": datetime(2027, 6, 6, 14, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 82.0,  # estimación: gobierna 12 de los 17 estados en juego
        "trending": True,
    },
]


async def main() -> None:
    inserted = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        for m in MARKETS:
            exists = await db.execute(select(Market).where(Market.id == m["id"]))
            if exists.scalar_one_or_none():
                print(f"  SKIP   {m['id']} (already exists)")
                skipped += 1
                continue

            # Nunca sembrar un mercado ya cerrado: si fue borrado a propósito
            # (cleanup-mercados-vencidos-sin-predicciones-*), no debe resucitar.
            if m["ends_at"] < datetime.now(timezone.utc):
                print(f"  SKIP   {m['id']} (ya vencido: {m['ends_at']:%Y-%m-%d %H:%M} UTC; no se siembran mercados cerrados)")
                skipped += 1
                continue

            b = m["b"]
            initial_price = m["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, b)
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, b)

            market = Market(
                id=m["id"],
                question=m["question"],
                description=m["description"],
                category=m["category"],
                subcategory=m.get("subcategory"),
                resolution_criteria=m["resolution_criteria"],
                ends_at=m["ends_at"],
                b=b,
                q_yes=q_yes,
                q_no=q_no,
                yes_price=yes_price_val,
                volume=0.0,
                num_trades=0,
                status=MarketStatus.OPEN,
                trending=m.get("trending", False),
                market_type="binary",
            )
            db.add(market)
            db.add(PriceHistory(
                market_id=market.id,
                yes_price=yes_price_val,
                volume_snapshot=0.0,
            ))
            inserted += 1
            print(f"  INSERT {m['id']}  yes_price={yes_price_val:.2f}%  b={b}  category={m['category'].name}")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MARKETS)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
