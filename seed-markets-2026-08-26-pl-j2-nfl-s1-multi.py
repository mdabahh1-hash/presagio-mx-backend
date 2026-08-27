"""
Seed script: 26 mercados MULTI-OPCIÓN — Premier League Jornada 2 2026-27 (10 mercados
1X2, 3 opciones) y NFL Semana 1 2026 (16 mercados ganador, 2 opciones).

Mirrors seed-markets-2026-08-27-jornada-1x2-multi.py / seed-markets-2026-06-23-multi.py
(template multi-outcome). Reusa init_qs_for_targets(targets, b) verbatim. Generalizado:
recorre una lista MARKETS de dicts con N outcomes cada uno.

Run from the backend directory (prod):
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-08-26-pl-j2-nfl-s1-multi.py'

Resolución (manual, fuera de este script): POST /admin/markets/{id}/resolve
con {outcome_key: ganador}. Empate en NFL → cancelar el mercado vía admin.
"""
import asyncio
import math
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.outcome import Outcome
from app.models.price_history import PriceHistory
from app.core.lmsr import prices_multi

B = 100.0

RC_PL = (
    "Resultado oficial al finalizar los 90 minutos más el tiempo de compensación, "
    "según acta oficial de la Premier League (premierleague.com). No cuentan "
    "prórrogas ni penales."
)
RC_NFL = (
    "Equipo ganador del partido según resultado oficial de NFL.com, incluyendo tiempo "
    "extra. Si el partido termina oficialmente empatado, el mercado se cancela vía admin "
    "(status cancelled) y se reembolsa. Si el kickoff se reprograma, ends_at se mueve al "
    "nuevo horario oficial."
)


def pl(mid, local, visitante, question, ends_at, outcomes, trending=False):
    return {
        "id": mid,
        "subcategory": "Premier League",
        "trending": trending,
        "question": question,
        "description": (
            f"Mercado 1X2 de la Jornada 2 de la Premier League 2026-27: {local} vs "
            f"{visitante}. Elige victoria local, empate o victoria visitante."
        ),
        "resolution_criteria": RC_PL,
        "ends_at": ends_at,
        "outcomes": outcomes,
    }


def nfl(mid, local, visitante, question, ends_at, outcomes, trending=False, sede=None):
    sede_txt = f" Se juega en {sede}." if sede else ""
    return {
        "id": mid,
        "subcategory": "NFL",
        "trending": trending,
        "question": question,
        "description": (
            f"Mercado de ganador de la Semana 1 de la temporada NFL 2026: {local} vs "
            f"{visitante}.{sede_txt} Solo dos opciones, el ganador entre ambos equipos."
        ),
        "resolution_criteria": RC_NFL,
        "ends_at": ends_at,
        "outcomes": outcomes,
    }


# outcomes: (outcome_key, label, pct)
MARKETS = [
    # ── PREMIER LEAGUE JORNADA 2 ──
    pl("pl-palace-city-j2-2627", "Crystal Palace", "Manchester City",
       "¿Cómo termina Crystal Palace vs Manchester City? (Premier League J2)",
       "2026-08-28T19:00:00Z",
       [("crystal-palace", "🦅 Crystal Palace", 18), ("empate", "🤝 Empate", 23), ("man-city", "🔵 Manchester City", 59)],
       trending=True),
    pl("pl-liverpool-forest-j2-2627", "Liverpool", "Nottingham Forest",
       "¿Cómo termina Liverpool vs Nottingham Forest? (Premier League J2)",
       "2026-08-29T11:30:00Z",
       [("liverpool", "🔴 Liverpool", 64), ("empate", "🤝 Empate", 20), ("forest", "🌳 Nottingham Forest", 16)]),
    pl("pl-bournemouth-everton-j2-2627", "Bournemouth", "Everton",
       "¿Cómo termina Bournemouth vs Everton? (Premier League J2)",
       "2026-08-29T14:00:00Z",
       [("bournemouth", "🍒 Bournemouth", 46), ("empate", "🤝 Empate", 27), ("everton", "🔷 Everton", 27)]),
    pl("pl-coventry-hull-j2-2627", "Coventry City", "Hull City",
       "¿Cómo termina Coventry City vs Hull City? (Premier League J2)",
       "2026-08-29T14:00:00Z",
       [("coventry", "🩵 Coventry City", 51), ("empate", "🤝 Empate", 27), ("hull", "🐯 Hull City", 22)]),
    pl("pl-tottenham-newcastle-j2-2627", "Tottenham", "Newcastle",
       "¿Cómo termina Tottenham vs Newcastle? (Premier League J2)",
       "2026-08-29T16:30:00Z",
       [("tottenham", "⚪ Tottenham", 43), ("empate", "🤝 Empate", 26), ("newcastle", "⚫ Newcastle", 31)]),
    pl("pl-chelsea-brighton-j2-2627", "Chelsea", "Brighton",
       "¿Cómo termina Chelsea vs Brighton? (Premier League J2)",
       "2026-08-30T13:00:00Z",
       [("chelsea", "🔵 Chelsea", 50), ("empate", "🤝 Empate", 24), ("brighton", "🕊️ Brighton", 26)]),
    pl("pl-leeds-brentford-j2-2627", "Leeds United", "Brentford",
       "¿Cómo termina Leeds United vs Brentford? (Premier League J2)",
       "2026-08-30T13:00:00Z",
       [("leeds", "⚪ Leeds United", 37), ("empate", "🤝 Empate", 28), ("brentford", "🐝 Brentford", 35)]),
    pl("pl-sunderland-fulham-j2-2627", "Sunderland", "Fulham",
       "¿Cómo termina Sunderland vs Fulham? (Premier League J2)",
       "2026-08-30T13:00:00Z",
       [("sunderland", "🔴 Sunderland", 39), ("empate", "🤝 Empate", 28), ("fulham", "⚪ Fulham", 33)]),
    pl("pl-manutd-ipswich-j2-2627", "Manchester United", "Ipswich Town",
       "¿Cómo termina Manchester United vs Ipswich Town? (Premier League J2)",
       "2026-08-30T15:30:00Z",
       [("man-utd", "😈 Manchester United", 68), ("empate", "🤝 Empate", 19), ("ipswich", "🚜 Ipswich Town", 13)]),
    pl("pl-villa-arsenal-j2-2627", "Aston Villa", "Arsenal",
       "¿Cómo termina Aston Villa vs Arsenal? (Premier League J2)",
       "2026-08-31T19:00:00Z",
       [("aston-villa", "🦁 Aston Villa", 15), ("empate", "🤝 Empate", 22), ("arsenal", "🔴 Arsenal", 63)],
       trending=True),

    # ── NFL SEMANA 1 ──
    nfl("nfl-patriots-seahawks-s1-2026", "Patriots", "Seahawks",
        "¿Quién gana Patriots vs Seahawks? (NFL Semana 1, revancha del Super Bowl)",
        "2026-09-10T00:20:00Z",
        [("patriots", "🇺🇸 Patriots", 36), ("seahawks", "🦅 Seahawks", 64)], trending=True),
    nfl("nfl-49ers-rams-s1-2026", "49ers", "Rams",
        "¿Quién gana 49ers vs Rams? (NFL Semana 1, Melbourne)",
        "2026-09-11T00:35:00Z",
        [("49ers", "⛏️ 49ers", 42), ("rams", "🐏 Rams", 58)], trending=True, sede="Melbourne, Australia"),
    nfl("nfl-bears-panthers-s1-2026", "Bears", "Panthers",
        "¿Quién gana Bears vs Panthers? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("bears", "🐻 Bears", 55), ("panthers", "🐈‍⬛ Panthers", 45)]),
    nfl("nfl-bucs-bengals-s1-2026", "Buccaneers", "Bengals",
        "¿Quién gana Buccaneers vs Bengals? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("buccaneers", "☠️ Buccaneers", 36), ("bengals", "🐅 Bengals", 64)]),
    nfl("nfl-saints-lions-s1-2026", "Saints", "Lions",
        "¿Quién gana Saints vs Lions? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("saints", "⚜️ Saints", 27), ("lions", "🦁 Lions", 73)]),
    nfl("nfl-bills-texans-s1-2026", "Bills", "Texans",
        "¿Quién gana Bills vs Texans? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("bills", "🦬 Bills", 51), ("texans", "🤠 Texans", 49)]),
    nfl("nfl-ravens-colts-s1-2026", "Ravens", "Colts",
        "¿Quién gana Ravens vs Colts? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("ravens", "🐦‍⬛ Ravens", 62), ("colts", "🐎 Colts", 38)]),
    nfl("nfl-browns-jaguars-s1-2026", "Browns", "Jaguars",
        "¿Quién gana Browns vs Jaguars? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("browns", "🟤 Browns", 29), ("jaguars", "🐆 Jaguars", 71)]),
    nfl("nfl-falcons-steelers-s1-2026", "Falcons", "Steelers",
        "¿Quién gana Falcons vs Steelers? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("falcons", "🪶 Falcons", 39), ("steelers", "🔨 Steelers", 61)]),
    nfl("nfl-jets-titans-s1-2026", "Jets", "Titans",
        "¿Quién gana Jets vs Titans? (NFL Semana 1)",
        "2026-09-13T17:00:00Z",
        [("jets", "✈️ Jets", 40), ("titans", "🔱 Titans", 60)]),
    nfl("nfl-cardinals-chargers-s1-2026", "Cardinals", "Chargers",
        "¿Quién gana Cardinals vs Chargers? (NFL Semana 1)",
        "2026-09-13T20:25:00Z",
        [("cardinals", "🐦 Cardinals", 17), ("chargers", "⚡ Chargers", 83)]),
    nfl("nfl-dolphins-raiders-s1-2026", "Dolphins", "Raiders",
        "¿Quién gana Dolphins vs Raiders? (NFL Semana 1)",
        "2026-09-13T20:25:00Z",
        [("dolphins", "🐬 Dolphins", 38), ("raiders", "🏴‍☠️ Raiders", 62)]),
    nfl("nfl-packers-vikings-s1-2026", "Packers", "Vikings",
        "¿Quién gana Packers vs Vikings? (NFL Semana 1)",
        "2026-09-13T20:25:00Z",
        [("packers", "🧀 Packers", 53), ("vikings", "⚔️ Vikings", 47)]),
    nfl("nfl-commanders-eagles-s1-2026", "Commanders", "Eagles",
        "¿Quién gana Commanders vs Eagles? (NFL Semana 1)",
        "2026-09-13T20:25:00Z",
        [("commanders", "🎖️ Commanders", 33), ("eagles", "🦅 Eagles", 67)]),
    nfl("nfl-cowboys-giants-s1-2026", "Cowboys", "Giants",
        "¿Quién gana Cowboys vs Giants? (NFL Semana 1, Sunday Night Football)",
        "2026-09-14T00:20:00Z",
        [("cowboys", "⭐ Cowboys", 54), ("giants", "🗽 Giants", 46)], trending=True),
    nfl("nfl-broncos-chiefs-s1-2026", "Broncos", "Chiefs",
        "¿Quién gana Broncos vs Chiefs? (NFL Semana 1, Monday Night Football)",
        "2026-09-15T00:15:00Z",
        [("broncos", "🐴 Broncos", 42), ("chiefs", "🏹 Chiefs", 58)], trending=True),
]


def init_qs_for_targets(targets: dict[str, float], b: float) -> dict[str, float]:
    """
    Return q_dict such that prices_multi(q_dict, b) ≈ targets (percentages summing to 100).
    Formula: q_i = b * log(p_i) + constant  — constant cancels in the softmax.
    We set q_i = b * log(p_i / p_ref) where p_ref = 1/N (uniform).
    (Mirrored verbatim from seed-markets-2026-06-23-multi.py.)
    """
    n = len(targets)
    p_ref = 1.0 / n  # uniform probability
    q = {}
    for key, pct in targets.items():
        p = pct / 100.0
        q[key] = b * math.log(p / p_ref)
    return q


async def main() -> None:
    inserted = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        for m in MARKETS:
            mid = m["id"]

            total_pct = sum(pct for _, _, pct in m["outcomes"])
            if abs(total_pct - 100) > 1e-6:
                print(f"  WARNING {mid}: las pct suman {total_pct}, no 100")

            result = await db.execute(select(Market).where(Market.id == mid))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {mid} (already exists)")
                skipped += 1
                continue

            ends_at = datetime.fromisoformat(m["ends_at"].replace("Z", "+00:00"))

            market = Market(
                id=mid,
                question=m["question"],
                description=m["description"],
                category=MarketCategory.DEPORTES,
                subcategory=m.get("subcategory"),
                resolution_criteria=m["resolution_criteria"],
                ends_at=ends_at,
                b=B,
                status=MarketStatus.OPEN,
                trending=m["trending"],
                market_type="multi",
            )
            db.add(market)
            await db.flush()

            targets = {key: float(pct) for key, _, pct in m["outcomes"]}
            q_dict = init_qs_for_targets(targets, B)
            check_prices = prices_multi(q_dict, B)

            for key, label, target_pct in m["outcomes"]:
                existing = await db.execute(
                    select(Outcome).where(Outcome.market_id == mid, Outcome.outcome_key == key)
                )
                if existing.scalar_one_or_none() is not None:
                    print(f"    SKIP outcome {key} (already exists)")
                    continue
                db.add(Outcome(
                    market_id=market.id,
                    outcome_key=key,
                    label=label,
                    q=q_dict[key],
                    price=float(target_pct),
                ))
                print(f"    outcome: {label:32s} price={target_pct:.1f}%  lmsr_check={check_prices[key]:.2f}%")

            db.add(PriceHistory(market_id=market.id, yes_price=0.0, volume_snapshot=0.0))

            inserted += 1
            print(f"  INSERT {mid} (multi, {m['subcategory']}, b={B}, trending={m['trending']}, n={len(m['outcomes'])})")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MARKETS)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
