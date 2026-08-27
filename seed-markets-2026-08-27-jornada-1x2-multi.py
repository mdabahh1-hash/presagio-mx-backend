"""
Seed script: 71 mercados MULTI-OPCIÓN 1X2 de fútbol (local/empate/visitante).
LaLiga J3, Ligue 1 J2, Bundesliga J1, Liga Portugal J4,
(Premier League J2 retirado el 2026-08-26 — ver seed-markets-2026-08-26-pl-j2-nfl-s1-multi.py),
Liga MX J6, MLS J23 y Serie A J2 — jornada del 28 al 31 de agosto de 2026.

Mirrors seed-markets-2026-08-19-futbol-multi.py / seed-markets-2026-06-23-multi.py
(template multi-outcome). Reusa init_qs_for_targets(targets, b) verbatim.

Run from the backend directory (prod):
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-08-27-jornada-1x2-multi.py'

Resolución (manual, fuera de este script): POST /admin/markets/{id}/resolve
con outcome_key 'local', 'empate' o 'visitante'.
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

B_DEFAULT = 100.0
B_TRENDING = 150.0

RESOLUTION_CRITERIA = (
    "Resuelve con el resultado oficial al final de los 90 minutos más tiempo de "
    "compensación según la liga. No cuenta prórroga ni penales. Si el partido se "
    "pospone antes de iniciar, el mercado permanece abierto hasta que se juegue. "
    "Si se abandona, se espera la decisión oficial de la liga."
)

# (id, subcategory, local, visitante, ends_at_utc_kickoff, pct_local, pct_empate, pct_visitante, trending)
MATCHES = [
    # LaLiga
    ("laliga-racing-elche-j3",         "LaLiga", "Racing de Santander", "Elche",              "2026-08-28T17:00:00Z", 43, 28, 29, False),
    ("laliga-alaves-villarreal-j3",    "LaLiga", "Alavés",              "Villarreal",         "2026-08-28T19:30:00Z", 31, 27, 42, False),
    ("laliga-levante-betis-j3",        "LaLiga", "Levante",             "Real Betis",         "2026-08-29T15:00:00Z", 29, 28, 43, False),
    ("laliga-realsociedad-espanyol-j3","LaLiga", "Real Sociedad",       "Espanyol",           "2026-08-29T17:00:00Z", 51, 26, 23, False),
    ("laliga-sevilla-atletico-j3",     "LaLiga", "Sevilla",             "Atlético de Madrid", "2026-08-29T19:30:00Z", 27, 28, 45, True),
    ("laliga-realmadrid-malaga-j3",    "LaLiga", "Real Madrid",         "Málaga",             "2026-08-30T15:00:00Z", 83, 11,  6, True),
    ("laliga-deportivo-valencia-j3",   "LaLiga", "Deportivo",           "Valencia",           "2026-08-30T17:30:00Z", 37, 30, 33, False),
    ("laliga-celta-athletic-j3",       "LaLiga", "Celta",               "Athletic Club",      "2026-08-30T19:30:00Z", 36, 28, 36, False),  # est
    ("laliga-osasuna-getafe-j3",       "LaLiga", "Osasuna",             "Getafe",             "2026-08-31T17:30:00Z", 40, 30, 30, False),  # est
    ("laliga-barcelona-rayo-j3",       "LaLiga", "Barcelona",           "Rayo Vallecano",     "2026-08-31T19:30:00Z", 78, 14,  8, True),   # est

    # Ligue 1
    ("l1-lille-psg-j2",                "Ligue 1", "Lille",       "Paris Saint-Germain", "2026-08-28T18:45:00Z", 21, 24, 55, True),
    ("l1-strasbourg-lens-j2",          "Ligue 1", "Strasbourg",  "Lens",                "2026-08-29T15:15:00Z", 28, 26, 46, False),
    ("l1-auxerre-angers-j2",           "Ligue 1", "Auxerre",     "Angers",              "2026-08-29T18:45:00Z", 49, 27, 24, False),
    ("l1-brest-toulouse-j2",           "Ligue 1", "Brest",       "Toulouse",            "2026-08-29T18:45:00Z", 36, 28, 36, False),
    ("l1-lorient-troyes-j2",           "Ligue 1", "Lorient",     "Troyes",              "2026-08-29T18:45:00Z", 51, 27, 22, False),
    ("l1-lyon-lehavre-j2",             "Ligue 1", "Lyon",        "Le Havre",            "2026-08-29T18:45:00Z", 66, 20, 14, False),
    ("l1-parisfc-nice-j2",             "Ligue 1", "Paris FC",    "Nice",                "2026-08-30T13:00:00Z", 45, 29, 26, False),
    ("l1-rennes-lemans-j2",            "Ligue 1", "Rennes",      "Le Mans",             "2026-08-30T15:15:00Z", 67, 19, 14, False),
    ("l1-monaco-marseille-j2",         "Ligue 1", "Monaco",      "Marseille",           "2026-08-30T18:45:00Z", 39, 25, 36, True),

    # Premier League — RETIRADO 2026-08-26: estos 10 partidos viven en
    # seed-markets-2026-08-26-pl-j2-nfl-s1-multi.py (ids *-j2-2627). Los ids
    # pl-*-j2 fueron borrados de prod para evitar duplicados; no reinsertar.
    # ("pl-crystalpalace-mancity-j2",    "Premier League", "Crystal Palace",    "Manchester City",   "2026-08-28T19:00:00Z", 18, 22, 60, True),
    # ("pl-liverpool-forest-j2",         "Premier League", "Liverpool",         "Nottingham Forest", "2026-08-29T11:30:00Z", 65, 20, 15, True),
    # ("pl-bournemouth-everton-j2",      "Premier League", "Bournemouth",       "Everton",           "2026-08-29T14:00:00Z", 46, 27, 27, False),
    # ("pl-coventry-hull-j2",            "Premier League", "Coventry City",     "Hull City",         "2026-08-29T14:00:00Z", 51, 26, 23, False),
    # ("pl-tottenham-newcastle-j2",      "Premier League", "Tottenham",         "Newcastle",         "2026-08-29T16:30:00Z", 43, 26, 31, True),
    # ("pl-chelsea-brighton-j2",         "Premier League", "Chelsea",           "Brighton",          "2026-08-30T13:00:00Z", 50, 25, 25, False),
    # ("pl-leeds-brentford-j2",          "Premier League", "Leeds United",      "Brentford",         "2026-08-30T13:00:00Z", 37, 28, 35, False),
    # ("pl-sunderland-fulham-j2",        "Premier League", "Sunderland",        "Fulham",            "2026-08-30T13:00:00Z", 39, 28, 33, False),
    # ("pl-manutd-ipswich-j2",           "Premier League", "Manchester United", "Ipswich Town",      "2026-08-30T15:30:00Z", 67, 20, 13, True),
    # ("pl-astonvilla-arsenal-j2",       "Premier League", "Aston Villa",       "Arsenal",           "2026-08-31T19:00:00Z", 15, 22, 63, True),

    # Bundesliga
    ("bl-bayern-stuttgart-j1",         "Bundesliga", "Bayern Múnich",     "Stuttgart",                "2026-08-28T18:30:00Z", 76, 13, 11, True),
    ("bl-elversberg-leverkusen-j1",    "Bundesliga", "Elversberg",        "Bayer Leverkusen",         "2026-08-29T13:30:00Z", 18, 20, 62, False),
    ("bl-koln-hoffenheim-j1",          "Bundesliga", "Köln",              "Hoffenheim",               "2026-08-29T13:30:00Z", 32, 26, 42, False),
    ("bl-unionberlin-frankfurt-j1",    "Bundesliga", "Union Berlin",      "Eintracht Frankfurt",      "2026-08-29T13:30:00Z", 39, 26, 35, False),
    ("bl-mainz-paderborn-j1",          "Bundesliga", "Mainz",             "Paderborn",                "2026-08-29T13:30:00Z", 57, 23, 20, False),
    ("bl-leipzig-gladbach-j1",         "Bundesliga", "RB Leipzig",        "Borussia Mönchengladbach", "2026-08-29T13:30:00Z", 62, 21, 17, False),
    ("bl-dortmund-hamburg-j1",         "Bundesliga", "Borussia Dortmund", "Hamburg",                  "2026-08-29T16:30:00Z", 73, 16, 11, True),
    ("bl-freiburg-bremen-j1",          "Bundesliga", "Freiburg",          "Werder Bremen",            "2026-08-30T13:30:00Z", 46, 27, 27, False),
    ("bl-augsburg-schalke-j1",         "Bundesliga", "Augsburg",          "Schalke 04",               "2026-08-30T15:30:00Z", 44, 25, 31, False),

    # Liga Portugal (hora local Portugal −1 = UTC)
    ("lp-rioave-sporting-j4",          "Liga Portugal", "Rio Ave",         "Sporting CP",       "2026-08-28T19:15:00Z", 13, 21, 66, False),  # est
    ("lp-alverca-santaclara-j4",       "Liga Portugal", "Alverca",         "Santa Clara",       "2026-08-29T14:30:00Z", 36, 30, 34, False),  # est
    ("lp-arouca-maritimo-j4",          "Liga Portugal", "Arouca",          "Marítimo",          "2026-08-29T14:30:00Z", 42, 29, 29, False),  # est
    ("lp-viseu-porto-j4",              "Liga Portugal", "Académico Viseu", "Porto",             "2026-08-29T17:00:00Z", 10, 18, 72, False),  # est
    ("lp-nacional-estrela-j4",         "Liga Portugal", "Nacional",        "Estrela Amadora",   "2026-08-30T14:30:00Z", 40, 30, 30, False),  # est
    ("lp-casapia-moreirense-j4",       "Liga Portugal", "Casa Pia",        "Moreirense",        "2026-08-30T17:00:00Z", 38, 30, 32, False),  # est
    ("lp-famalicao-gilvicente-j4",     "Liga Portugal", "Famalicão",       "Gil Vicente",       "2026-08-30T19:30:00Z", 44, 29, 27, False),  # est
    ("lp-benfica-estoril-j4",          "Liga Portugal", "Benfica",         "Estoril",           "2026-08-31T19:15:00Z", 76, 15,  9, True),   # est, hora sujeta a playoff europeo
    ("lp-braga-vitoria-j4",            "Liga Portugal", "Braga",           "Vitória Guimarães", "2026-08-31T19:15:00Z", 52, 26, 22, False),  # est, hora sujeta a playoff europeo

    # Liga MX (horarios centro de México UTC−6 convertidos a UTC)
    ("mx-atlante-leon-j6",             "Liga MX", "Atlante",       "León",              "2026-08-29T01:00:00Z", 28, 28, 44, False),  # est
    ("mx-necaxa-cruzazul-j6",          "Liga MX", "Necaxa",        "Cruz Azul",         "2026-08-29T01:00:00Z", 30, 27, 43, True),   # est
    ("mx-tijuana-pumas-j6",            "Liga MX", "Tijuana",       "Pumas UNAM",        "2026-08-29T03:00:00Z", 39, 29, 32, False),  # est
    ("mx-atlas-queretaro-j6",          "Liga MX", "Atlas",         "Querétaro",         "2026-08-29T23:00:00Z", 50, 27, 23, False),  # est
    ("mx-pachuca-guadalajara-j6",      "Liga MX", "Pachuca",       "Guadalajara",       "2026-08-29T23:00:00Z", 36, 29, 35, True),   # est
    ("mx-america-puebla-j6",           "Liga MX", "América",       "Puebla",            "2026-08-30T01:00:00Z", 60, 23, 17, True),   # est
    ("mx-santos-tigres-j6",            "Liga MX", "Santos Laguna", "Tigres",            "2026-08-30T03:00:00Z", 30, 28, 42, True),   # est
    ("mx-toluca-juarez-j6",            "Liga MX", "Toluca",        "Juárez",            "2026-08-31T00:00:00Z", 58, 24, 18, False),  # est
    ("mx-monterrey-sanluis-j6",        "Liga MX", "Monterrey",     "Atlético San Luis", "2026-08-31T02:00:00Z", 58, 25, 17, False),  # est

    # MLS
    ("mls-seattle-chicago-j23",        "MLS", "Seattle Sounders",     "Chicago Fire",           "2026-08-29T20:30:00Z", 34, 24, 42, False),
    ("mls-atlanta-charlotte-j23",      "MLS", "Atlanta United",       "Charlotte FC",           "2026-08-29T23:30:00Z", 41, 25, 34, False),
    ("mls-columbus-newengland-j23",    "MLS", "Columbus Crew",        "New England Revolution", "2026-08-29T23:30:00Z", 49, 25, 26, False),
    ("mls-dcunited-lafc-j23",          "MLS", "DC United",            "Los Angeles FC",         "2026-08-29T23:30:00Z", 28, 25, 47, False),
    ("mls-intermiami-montreal-j23",    "MLS", "Inter Miami",          "CF Montréal",            "2026-08-29T23:30:00Z", 69, 17, 14, True),
    ("mls-redbulls-philadelphia-j23",  "MLS", "NY Red Bulls",         "Philadelphia Union",     "2026-08-29T23:30:00Z", 33, 23, 44, False),
    ("mls-toronto-nycfc-j23",          "MLS", "Toronto FC",           "New York City FC",       "2026-08-29T23:30:00Z", 37, 26, 37, False),
    ("mls-houston-sanjose-j23",        "MLS", "Houston Dynamo",       "San Jose Earthquakes",   "2026-08-30T00:30:00Z", 57, 22, 21, False),
    ("mls-sportingkc-vancouver-j23",   "MLS", "Sporting Kansas City", "Vancouver Whitecaps",    "2026-08-30T00:30:00Z", 14, 18, 68, False),
    ("mls-minnesota-orlando-j23",      "MLS", "Minnesota United",     "Orlando City",           "2026-08-30T00:30:00Z", 54, 22, 24, False),
    ("mls-nashville-cincinnati-j23",   "MLS", "Nashville SC",         "FC Cincinnati",          "2026-08-30T00:30:00Z", 48, 25, 27, False),  # est
    ("mls-colorado-saltlake-j23",      "MLS", "Colorado Rapids",      "Real Salt Lake",         "2026-08-30T01:30:00Z", 42, 27, 31, False),  # est
    ("mls-portland-austin-j23",        "MLS", "Portland Timbers",     "Austin FC",              "2026-08-30T02:30:00Z", 46, 27, 27, False),  # est
    ("mls-sandiego-galaxy-j23",        "MLS", "San Diego FC",         "LA Galaxy",              "2026-08-30T02:30:00Z", 55, 24, 21, False),  # est
    ("mls-stlouis-dallas-j23",         "MLS", "St. Louis City",       "FC Dallas",              "2026-08-30T23:00:00Z", 50, 26, 24, False),  # est

    # Serie A
    ("sa-milan-venezia-j2",            "Serie A", "AC Milan",   "Venezia",   "2026-08-28T18:45:00Z", 70, 19, 11, True),
    ("sa-fiorentina-frosinone-j2",     "Serie A", "Fiorentina", "Frosinone", "2026-08-29T16:30:00Z", 58, 23, 19, False),
    ("sa-monza-udinese-j2",            "Serie A", "Monza",      "Udinese",   "2026-08-29T16:30:00Z", 28, 30, 42, False),
    ("sa-sassuolo-torino-j2",          "Serie A", "Sassuolo",   "Torino",    "2026-08-29T16:30:00Z", 43, 28, 29, False),
    ("sa-juventus-parma-j2",           "Serie A", "Juventus",   "Parma",     "2026-08-29T18:45:00Z", 80, 14,  6, True),
    ("sa-napoli-como-j2",              "Serie A", "Napoli",     "Como",      "2026-08-30T16:30:00Z", 38, 30, 32, True),
    ("sa-cagliari-inter-j2",           "Serie A", "Cagliari",   "Inter",     "2026-08-30T18:45:00Z", 13, 21, 66, True),
    ("sa-lazio-genoa-j2",              "Serie A", "Lazio",      "Genoa",     "2026-08-30T18:45:00Z", 48, 29, 23, False),
    ("sa-lecce-roma-j2",               "Serie A", "Lecce",      "Roma",      "2026-08-31T16:30:00Z", 14, 23, 63, False),
    ("sa-atalanta-bologna-j2",         "Serie A", "Atalanta",   "Bologna",   "2026-08-31T18:45:00Z", 51, 26, 23, False),
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
        for (mid, subcategory, local, visitante, ends_at_iso,
             pct_local, pct_empate, pct_visitante, trending) in MATCHES:

            total_pct = pct_local + pct_empate + pct_visitante
            if abs(total_pct - 100) > 1e-6:
                print(f"  WARNING {mid}: las pct suman {total_pct}, no 100")

            result = await db.execute(select(Market).where(Market.id == mid))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {mid} (already exists)")
                skipped += 1
                continue

            ends_at = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))
            b = B_TRENDING if trending else B_DEFAULT

            market = Market(
                id=mid,
                question=f"¿Quién gana {local} vs {visitante}?",
                description=(
                    f"Mercado 1X2 del partido {local} contra {visitante}, {subcategory}, "
                    f"jornada del 28 al 31 de agosto de 2026."
                ),
                category=MarketCategory.DEPORTES,
                subcategory=subcategory,
                resolution_criteria=RESOLUTION_CRITERIA,
                ends_at=ends_at,
                b=b,
                status=MarketStatus.OPEN,
                trending=trending,
                market_type="multi",
            )
            db.add(market)
            await db.flush()

            targets = {
                "local": float(pct_local),
                "empate": float(pct_empate),
                "visitante": float(pct_visitante),
            }
            q_dict = init_qs_for_targets(targets, b)
            check_prices = prices_multi(q_dict, b)

            outcome_rows = [
                ("local",     f"🏠 {local}",     pct_local),
                ("empate",    "🤝 Empate",       pct_empate),
                ("visitante", f"✈️ {visitante}", pct_visitante),
            ]
            for key, label, target_pct in outcome_rows:
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
            print(f"  INSERT {mid} (multi, {subcategory}, b={b}, trending={trending})")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MATCHES)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
