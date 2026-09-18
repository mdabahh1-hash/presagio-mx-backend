"""
Seed script: 17 mercados BINARIOS (sí/no) de titularidad — jornada 28-31 ago 2026
(LaLiga J3, Premier League J2).

Mirrors app/services/seed.py (convención binaria: SELECT previo, init_q_for_price, PriceHistory).
Run from the backend directory (prod):
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-08-27-titulares.py'
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

B = 100.0

RESOLUTION_TEMPLATE = (
    "Resuelve SÍ si {jugador} aparece en el once inicial oficial publicado por su club para {partido}. "
    "Resuelve NO si no aparece en el once titular, aunque entre como suplente o no participe. El mercado "
    "cierra cuando el club publique oficialmente su alineación. Si el partido se pospone antes de iniciar, "
    "el mercado permanece abierto hasta que se juegue. Si se abandona, se espera la decisión oficial de la liga."
)

# ends_at = kickoff oficial verificado (26 ago 2026) menos 75 minutos (publicación aprox. de alineación).
MARKETS = [
    # ── LaLiga J3 ──
    {"id": "laliga-titular-bernardo-silva-j3", "jugador": "Bernardo Silva", "partido": "Real Madrid vs Málaga",
     "question": "¿Bernardo Silva será titular en Real Madrid vs Málaga?",
     "description": "Bernardo Silva llegó al Real Madrid este verano y pelea por un sitio en la medular blanca. El Madrid recibe al recién ascendido Málaga en el Bernabéu el 30 de agosto (15:00Z) por la jornada 3 de LaLiga.",
     "ends_at": "2026-08-30T13:45:00Z", "subcategory": "LaLiga", "initial_yes_price": 68.0, "trending": False},
    {"id": "laliga-titular-arda-guler-j3", "jugador": "Arda Güler", "partido": "Real Madrid vs Málaga",
     "question": "¿Arda Güler será titular en Real Madrid vs Málaga?",
     "description": "Arda Güler se ha consolidado como pieza creativa del Real Madrid, pero la rotación ante rivales menores es habitual. El Madrid recibe al Málaga en el Bernabéu el 30 de agosto (15:00Z), jornada 3 de LaLiga.",
     "ends_at": "2026-08-30T13:45:00Z", "subcategory": "LaLiga", "initial_yes_price": 70.0, "trending": True},
    {"id": "laliga-titular-julian-alvarez-j3", "jugador": "Julián Álvarez", "partido": "Sevilla vs Atlético de Madrid",
     "question": "¿Julián Álvarez será titular en Sevilla vs Atlético de Madrid?",
     "description": "Julián Álvarez es la referencia ofensiva del Atlético de Madrid de Simeone. El Atlético visita el Sánchez-Pizjuán el 29 de agosto (19:30Z) por la jornada 3 de LaLiga.",
     "ends_at": "2026-08-29T18:15:00Z", "subcategory": "LaLiga", "initial_yes_price": 82.0, "trending": True},
    {"id": "laliga-titular-dani-olmo-j3", "jugador": "Dani Olmo", "partido": "Barcelona vs Rayo Vallecano",
     "question": "¿Dani Olmo será titular en Barcelona vs Rayo Vallecano?",
     "description": "Dani Olmo compite por la mediapunta del Barcelona en una plantilla con mucha competencia. El Barça recibe al Rayo Vallecano el 31 de agosto (19:30Z), jornada 3 de LaLiga.",
     "ends_at": "2026-08-31T18:15:00Z", "subcategory": "LaLiga", "initial_yes_price": 60.0, "trending": False},
    {"id": "laliga-titular-kounde-j3", "jugador": "Jules Koundé", "partido": "Barcelona vs Rayo Vallecano",
     "question": "¿Jules Koundé será titular en Barcelona vs Rayo Vallecano?",
     "description": "Jules Koundé es el lateral derecho titular habitual del Barcelona, aunque su estado físico tras el parón siempre es incógnita. El Barça recibe al Rayo Vallecano el 31 de agosto (19:30Z), jornada 3 de LaLiga.",
     "ends_at": "2026-08-31T18:15:00Z", "subcategory": "LaLiga", "initial_yes_price": 80.0, "trending": False},

    # ── Premier League J2 ──
    {"id": "pl-titular-merino-j2", "jugador": "Mikel Merino", "partido": "Aston Villa vs Arsenal",
     "question": "¿Mikel Merino será titular en Aston Villa vs Arsenal?",
     "description": "Mikel Merino alterna entre el mediocampo y la delantera del Arsenal según las necesidades de Arteta. El Arsenal visita Villa Park el 31 de agosto (19:00Z) por la jornada 2 de la Premier League.",
     "ends_at": "2026-08-31T17:45:00Z", "subcategory": "Premier League", "initial_yes_price": 55.0, "trending": False},
    {"id": "pl-titular-havertz-j2", "jugador": "Kai Havertz", "partido": "Aston Villa vs Arsenal",
     "question": "¿Kai Havertz será titular en Aston Villa vs Arsenal?",
     "description": "Kai Havertz pelea por el puesto de delantero centro del Arsenal tras los fichajes ofensivos del club. El Arsenal visita Villa Park el 31 de agosto (19:00Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-31T17:45:00Z", "subcategory": "Premier League", "initial_yes_price": 60.0, "trending": False},
    {"id": "pl-titular-yoro-j2", "jugador": "Leny Yoro", "partido": "Manchester United vs Ipswich Town",
     "question": "¿Leny Yoro será titular en Manchester United vs Ipswich Town?",
     "description": "Leny Yoro es uno de los centrales jóvenes en los que apuesta el Manchester United. Los Red Devils reciben al recién ascendido Ipswich Town en Old Trafford el 30 de agosto (15:30Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-30T14:15:00Z", "subcategory": "Premier League", "initial_yes_price": 65.0, "trending": False},
    {"id": "pl-titular-tielemans-j2", "jugador": "Youri Tielemans", "partido": "Manchester United vs Ipswich Town",
     "question": "¿Youri Tielemans será titular en Manchester United vs Ipswich Town?",
     "description": "Youri Tielemans se incorporó al Manchester United para dar equilibrio al mediocampo. El United recibe al Ipswich Town en Old Trafford el 30 de agosto (15:30Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-30T14:15:00Z", "subcategory": "Premier League", "initial_yes_price": 70.0, "trending": False},
    {"id": "pl-titular-porro-j2", "jugador": "Pedro Porro", "partido": "Tottenham vs Newcastle",
     "question": "¿Pedro Porro será titular en Tottenham vs Newcastle?",
     "description": "Pedro Porro es el lateral derecho de referencia del Tottenham. Los Spurs reciben al Newcastle el 29 de agosto (16:30Z) por la jornada 2 de la Premier League.",
     "ends_at": "2026-08-29T15:15:00Z", "subcategory": "Premier League", "initial_yes_price": 70.0, "trending": False},
    {"id": "pl-titular-tonali-j2", "jugador": "Sandro Tonali", "partido": "Tottenham vs Newcastle",
     "question": "¿Sandro Tonali será titular en Tottenham vs Newcastle?",
     "description": "Sandro Tonali es el motor del mediocampo del Newcastle. Las Urracas visitan al Tottenham el 29 de agosto (16:30Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-29T15:15:00Z", "subcategory": "Premier League", "initial_yes_price": 75.0, "trending": False},
    {"id": "pl-titular-elliot-anderson-j2", "jugador": "Elliot Anderson", "partido": "Crystal Palace vs Manchester City",
     "question": "¿Elliot Anderson será titular en Crystal Palace vs Manchester City?",
     "description": "Elliot Anderson llegó al Manchester City como uno de los fichajes destacados del verano para el mediocampo de Guardiola. El City visita Selhurst Park el 28 de agosto (19:00Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-28T17:45:00Z", "subcategory": "Premier League", "initial_yes_price": 65.0, "trending": False},
    {"id": "pl-titular-kovacic-j2", "jugador": "Mateo Kovačić", "partido": "Crystal Palace vs Manchester City",
     "question": "¿Mateo Kovačić será titular en Crystal Palace vs Manchester City?",
     "description": "Mateo Kovačić compite por un puesto en un mediocampo del Manchester City muy poblado. El City visita al Crystal Palace en Selhurst Park el 28 de agosto (19:00Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-28T17:45:00Z", "subcategory": "Premier League", "initial_yes_price": 55.0, "trending": False},
    {"id": "pl-titular-gakpo-j2", "jugador": "Cody Gakpo", "partido": "Liverpool vs Nottingham Forest",
     "question": "¿Cody Gakpo será titular en Liverpool vs Nottingham Forest?",
     "description": "Cody Gakpo se disputa la banda izquierda del Liverpool con los refuerzos ofensivos del club. Los Reds reciben al Nottingham Forest en Anfield el 29 de agosto (11:30Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-29T10:15:00Z", "subcategory": "Premier League", "initial_yes_price": 60.0, "trending": False},
    {"id": "pl-titular-isak-j2", "jugador": "Alexander Isak", "partido": "Liverpool vs Nottingham Forest",
     "question": "¿Alexander Isak será titular en Liverpool vs Nottingham Forest?",
     "description": "Alexander Isak es el delantero centro de referencia del Liverpool. Los Reds reciben al Nottingham Forest en Anfield el 29 de agosto (11:30Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-29T10:15:00Z", "subcategory": "Premier League", "initial_yes_price": 75.0, "trending": True},
    {"id": "pl-titular-reece-james-j2", "jugador": "Reece James", "partido": "Chelsea vs Brighton",
     "question": "¿Reece James será titular en Chelsea vs Brighton?",
     "description": "Reece James, capitán del Chelsea, suele ser gestionado con cuidado por su historial de lesiones. Los Blues reciben al Brighton en Stamford Bridge el 30 de agosto (13:00Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-30T11:45:00Z", "subcategory": "Premier League", "initial_yes_price": 60.0, "trending": False},
    {"id": "pl-titular-pedro-neto-j2", "jugador": "Pedro Neto", "partido": "Chelsea vs Brighton",
     "question": "¿Pedro Neto será titular en Chelsea vs Brighton?",
     "description": "Pedro Neto compite por las bandas del Chelsea en un ataque con muchas alternativas. Los Blues reciben al Brighton en Stamford Bridge el 30 de agosto (13:00Z), jornada 2 de la Premier League.",
     "ends_at": "2026-08-30T11:45:00Z", "subcategory": "Premier League", "initial_yes_price": 65.0, "trending": False},
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

            initial_price = m["initial_yes_price"] / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, B)
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, B)
            ends_at = datetime.fromisoformat(m["ends_at"].replace("Z", "+00:00"))

            # Nunca sembrar un mercado ya cerrado: si fue borrado a propósito
            # (cleanup-mercados-vencidos-sin-predicciones-*), no debe resucitar.
            if ends_at < datetime.now(timezone.utc):
                print(f"  SKIP   {m['id']} (ya vencido: ends_at={m['ends_at']}; no se siembran mercados cerrados)")
                skipped += 1
                continue

            market = Market(
                id=m["id"],
                question=m["question"],
                description=m["description"],
                category=MarketCategory.DEPORTES,
                subcategory=m.get("subcategory"),
                resolution_criteria=RESOLUTION_TEMPLATE.format(jugador=m["jugador"], partido=m["partido"]),
                ends_at=ends_at,
                b=B,
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
            print(f"  INSERT {m['id']}  yes_price={yes_price_val:.2f}%  b={B}  ends_at={m['ends_at']}")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MARKETS)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
