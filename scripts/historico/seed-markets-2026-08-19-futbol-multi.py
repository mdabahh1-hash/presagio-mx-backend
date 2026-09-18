"""
Seed script: 81 mercados MULTI-OPCIÓN 1X2 de fútbol (local/empate/visitante).
LaLiga J2, Ligue 1 J1, Premier League J1, Bundesliga J1, Liga Portugal J3,
MLS, Liga MX Apertura 2026 y Serie A J1 — partidos del 20 al 30 de agosto 2026.

Mirrors seed-markets-2026-06-23-multi.py (template multi-outcome).
Run from the backend directory:
  DATABASE_URL="postgresql+asyncpg://..." python seed-markets-2026-08-19-futbol-multi.py

Resolución (manual, fuera de este script): POST /admin/markets/{id}/resolve
con outcome_key 'local', 'empate' o 'visitante'.
"""
import asyncio
import math
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.outcome import Outcome
from app.models.price_history import PriceHistory
from app.core.lmsr import prices_multi

B = 100.0

RESOLUTION_CRITERIA = (
    "Resultado oficial al término del tiempo reglamentario (90 min más añadido) "
    "según la página oficial de la liga o ESPN. Prórroga y penales no cuentan. "
    "Si el partido se pospone más de 7 días o se cancela, el mercado se cancela."
)

# (id, liga_jornada, local, visitante, ends_at_iso, trending, pct_local, pct_empate, pct_visitante)
MATCHES = [
    # ── LaLiga · Jornada 2 (20 al 24 ago) ──
    ("laliga-rayo-alaves-2008",       "LaLiga Jornada 2", "Rayo Vallecano",      "Deportivo Alavés",     "2026-08-20T10:00:00Z", False, 42, 29, 29),
    ("laliga-betis-realsociedad-2108", "LaLiga Jornada 2", "Real Betis",          "Real Sociedad",        "2026-08-21T10:00:00Z", False, 40, 28, 32),
    ("laliga-athletic-sevilla-2208",  "LaLiga Jornada 2", "Athletic Club",       "Sevilla",              "2026-08-22T10:00:00Z", False, 48, 27, 25),
    ("laliga-valencia-celta-2208",    "LaLiga Jornada 2", "Valencia",            "Celta de Vigo",        "2026-08-22T10:00:00Z", False, 38, 29, 33),
    ("laliga-espanyol-realmadrid-2208", "LaLiga Jornada 2", "Espanyol",          "Real Madrid",          "2026-08-22T10:00:00Z", True,  14, 20, 66),
    ("laliga-atletico-villarreal-2308", "LaLiga Jornada 2", "Atlético de Madrid", "Villarreal",          "2026-08-23T10:00:00Z", False, 48, 26, 26),
    ("laliga-getafe-racing-2308",     "LaLiga Jornada 2", "Getafe",              "Racing Santander",     "2026-08-23T10:00:00Z", False, 45, 29, 26),
    ("laliga-elche-barcelona-2308",   "LaLiga Jornada 2", "Elche",               "Barcelona",            "2026-08-23T10:00:00Z", True,  12, 19, 69),
    ("laliga-osasuna-levante-2408",   "LaLiga Jornada 2", "Osasuna",             "Levante",              "2026-08-24T10:00:00Z", False, 44, 29, 27),
    ("laliga-malaga-depor-2408",      "LaLiga Jornada 2", "Málaga",              "Deportivo La Coruña",  "2026-08-24T10:00:00Z", False, 40, 30, 30),

    # ── Ligue 1 · Jornada 1 (21 al 23 ago) ──
    ("l1-marsella-estrasburgo-2108",  "Ligue 1 Jornada 1", "Marsella",   "Estrasburgo", "2026-08-21T10:00:00Z", False, 52, 25, 23),
    ("l1-lens-auxerre-2208",          "Ligue 1 Jornada 1", "Lens",       "Auxerre",     "2026-08-22T10:00:00Z", False, 50, 27, 23),
    ("l1-toulouse-lyon-2208",         "Ligue 1 Jornada 1", "Toulouse",   "Lyon",        "2026-08-22T10:00:00Z", False, 30, 27, 43),
    ("l1-niza-lorient-2208",          "Ligue 1 Jornada 1", "Niza",       "Lorient",     "2026-08-22T10:00:00Z", False, 50, 27, 23),
    ("l1-troyes-parisfc-2208",        "Ligue 1 Jornada 1", "Troyes",     "Paris FC",    "2026-08-22T10:00:00Z", False, 38, 30, 32),
    ("l1-lemans-brest-2208",          "Ligue 1 Jornada 1", "Le Mans",    "Brest",       "2026-08-22T10:00:00Z", False, 34, 30, 36),
    ("l1-angers-lille-2308",          "Ligue 1 Jornada 1", "Angers",     "Lille",       "2026-08-23T10:00:00Z", False, 25, 27, 48),
    ("l1-lehavre-monaco-2308",        "Ligue 1 Jornada 1", "Le Havre",   "Mónaco",      "2026-08-23T10:00:00Z", False, 18, 24, 58),
    ("l1-psg-rennes-2308",            "Ligue 1 Jornada 1", "PSG",        "Rennes",      "2026-08-23T10:00:00Z", True,  70, 18, 12),

    # ── Premier League · Jornada 1 (21 al 24 ago) ──
    ("pl-arsenal-coventry-2108",      "Premier League Jornada 1", "Arsenal",           "Coventry City",     "2026-08-21T10:00:00Z", True,  78, 14, 8),
    ("pl-hull-manutd-2208",           "Premier League Jornada 1", "Hull City",         "Manchester United", "2026-08-22T10:00:00Z", False, 18, 24, 58),
    ("pl-everton-palace-2208",        "Premier League Jornada 1", "Everton",           "Crystal Palace",    "2026-08-22T10:00:00Z", False, 36, 29, 35),
    ("pl-ipswich-sunderland-2208",    "Premier League Jornada 1", "Ipswich Town",      "Sunderland",        "2026-08-22T10:00:00Z", False, 38, 30, 32),
    ("pl-forest-leeds-2208",          "Premier League Jornada 1", "Nottingham Forest", "Leeds United",      "2026-08-22T10:00:00Z", False, 42, 28, 30),
    ("pl-brentford-tottenham-2208",   "Premier League Jornada 1", "Brentford",         "Tottenham",         "2026-08-22T10:00:00Z", False, 32, 27, 41),
    ("pl-brighton-astonvilla-2308",   "Premier League Jornada 1", "Brighton",          "Aston Villa",       "2026-08-23T10:00:00Z", False, 38, 28, 34),
    ("pl-mancity-bournemouth-2308",   "Premier League Jornada 1", "Manchester City",   "Bournemouth",       "2026-08-23T10:00:00Z", False, 62, 21, 17),
    ("pl-newcastle-liverpool-2308",   "Premier League Jornada 1", "Newcastle United",  "Liverpool",         "2026-08-23T10:00:00Z", True,  32, 26, 42),
    ("pl-fulham-chelsea-2408",        "Premier League Jornada 1", "Fulham",            "Chelsea",           "2026-08-24T10:00:00Z", False, 28, 26, 46),

    # ── Bundesliga · Jornada 1 (28 al 30 ago) ──
    ("bl-bayern-stuttgart-2808",      "Bundesliga Jornada 1", "Bayern Múnich",     "Stuttgart",           "2026-08-28T10:00:00Z", True,  64, 20, 16),
    ("bl-union-frankfurt-2908",       "Bundesliga Jornada 1", "Union Berlin",      "Eintracht Frankfurt", "2026-08-29T10:00:00Z", False, 32, 28, 40),
    ("bl-colonia-hoffenheim-2908",    "Bundesliga Jornada 1", "Colonia",           "Hoffenheim",          "2026-08-29T10:00:00Z", False, 38, 29, 33),
    ("bl-mainz-paderborn-2908",       "Bundesliga Jornada 1", "Mainz",             "Paderborn",           "2026-08-29T10:00:00Z", False, 52, 27, 21),
    ("bl-leipzig-gladbach-2908",      "Bundesliga Jornada 1", "RB Leipzig",        "Mönchengladbach",     "2026-08-29T10:00:00Z", False, 52, 25, 23),
    ("bl-elversberg-leverkusen-2908", "Bundesliga Jornada 1", "Elversberg",        "Bayer Leverkusen",    "2026-08-29T10:00:00Z", False, 16, 22, 62),
    ("bl-dortmund-hamburgo-2908",     "Bundesliga Jornada 1", "Borussia Dortmund", "Hamburgo",            "2026-08-29T10:00:00Z", False, 62, 22, 16),
    ("bl-friburgo-werder-3008",       "Bundesliga Jornada 1", "Friburgo",          "Werder Bremen",       "2026-08-30T10:00:00Z", False, 44, 28, 28),
    ("bl-augsburgo-schalke-3008",     "Bundesliga Jornada 1", "Augsburgo",         "Schalke 04",          "2026-08-30T10:00:00Z", False, 44, 29, 27),

    # ── Liga Portugal · Jornada 3 (22 y 23 ago) ──
    ("lp-maritimo-viseu-2208",        "Liga Portugal Jornada 3", "Marítimo",          "Académico de Viseu", "2026-08-22T10:00:00Z", False, 42, 30, 28),
    ("lp-estoril-rioave-2208",        "Liga Portugal Jornada 3", "Estoril",           "Rio Ave",            "2026-08-22T10:00:00Z", False, 42, 30, 28),
    ("lp-sporting-alverca-2208",      "Liga Portugal Jornada 3", "Sporting CP",       "Alverca",            "2026-08-22T10:00:00Z", False, 76, 15, 9),
    ("lp-guimaraes-nacional-2308",    "Liga Portugal Jornada 3", "Vitória Guimarães", "Nacional",           "2026-08-23T10:00:00Z", False, 52, 27, 21),
    ("lp-santaclara-famalicao-2308",  "Liga Portugal Jornada 3", "Santa Clara",       "Famalicão",          "2026-08-23T10:00:00Z", False, 38, 30, 32),
    ("lp-porto-arouca-2308",          "Liga Portugal Jornada 3", "FC Porto",          "Arouca",             "2026-08-23T10:00:00Z", False, 72, 17, 11),
    ("lp-moreirense-benfica-2308",    "Liga Portugal Jornada 3", "Moreirense",        "Benfica",            "2026-08-23T10:00:00Z", False, 14, 21, 65),
    ("lp-gilvicente-casapia-2308",    "Liga Portugal Jornada 3", "Gil Vicente",       "Casa Pia",           "2026-08-23T10:00:00Z", False, 42, 30, 28),
    ("lp-estrela-braga-2308",         "Liga Portugal Jornada 3", "Estrela Amadora",   "Braga",              "2026-08-23T10:00:00Z", False, 20, 25, 55),

    # ── MLS · Fecha del 22 y 23 ago ──
    ("mls-montreal-galaxy-2208",      "MLS", "CF Montréal",            "LA Galaxy",            "2026-08-22T22:00:00Z", False, 42, 28, 30),
    ("mls-charlotte-dcunited-2208",   "MLS", "Charlotte FC",           "D.C. United",          "2026-08-22T22:00:00Z", False, 50, 27, 23),
    ("mls-cincinnati-seattle-2208",   "MLS", "FC Cincinnati",          "Seattle Sounders",     "2026-08-22T22:00:00Z", False, 45, 27, 28),
    ("mls-miami-toronto-2208",        "MLS", "Inter Miami",            "Toronto FC",           "2026-08-22T22:00:00Z", True,  58, 23, 19),
    ("mls-orlando-rsl-2208",          "MLS", "Orlando City",           "Real Salt Lake",       "2026-08-22T22:00:00Z", False, 48, 27, 25),
    ("mls-nyredbulls-chicago-2208",   "MLS", "New York Red Bulls",     "Chicago Fire",         "2026-08-22T22:00:00Z", False, 44, 28, 28),
    ("mls-austin-philadelphia-2208",  "MLS", "Austin FC",              "Philadelphia Union",   "2026-08-22T22:00:00Z", False, 38, 28, 34),
    ("mls-nashville-columbus-2208",   "MLS", "Nashville SC",           "Columbus Crew",        "2026-08-22T22:00:00Z", False, 42, 28, 30),
    ("mls-stlouis-houston-2208",      "MLS", "St. Louis City",         "Houston Dynamo",       "2026-08-22T22:00:00Z", False, 42, 29, 29),
    ("mls-vancouver-dallas-2208",     "MLS", "Vancouver Whitecaps",    "FC Dallas",            "2026-08-22T22:00:00Z", False, 50, 26, 24),
    ("mls-lafc-portland-2208",        "MLS", "LAFC",                   "Portland Timbers",     "2026-08-22T22:00:00Z", False, 52, 26, 22),
    ("mls-sandiego-colorado-2208",    "MLS", "San Diego FC",           "Colorado Rapids",      "2026-08-22T22:00:00Z", False, 50, 26, 24),
    ("mls-sanjose-minnesota-2208",    "MLS", "San Jose Earthquakes",   "Minnesota United",     "2026-08-22T22:00:00Z", False, 38, 28, 34),
    ("mls-newengland-nycfc-2308",     "MLS", "New England Revolution", "New York City FC",     "2026-08-23T22:00:00Z", False, 36, 29, 35),
    ("mls-atlanta-skc-2308",          "MLS", "Atlanta United",         "Sporting Kansas City", "2026-08-23T22:00:00Z", False, 46, 28, 26),

    # ── Liga MX · Jornada del 21 al 23 ago ──
    ("mx-leon-monterrey-2108",        "Liga MX Apertura 2026", "León",                 "Monterrey",     "2026-08-21T22:00:00Z", False, 30, 27, 43),
    ("mx-tigres-atlante-2108",        "Liga MX Apertura 2026", "Tigres UANL",          "Atlante",       "2026-08-21T22:00:00Z", False, 62, 23, 15),
    ("mx-juarez-america-2108",        "Liga MX Apertura 2026", "FC Juárez",            "América",       "2026-08-21T22:00:00Z", True,  24, 26, 50),
    ("mx-queretaro-toluca-2108",      "Liga MX Apertura 2026", "Querétaro",            "Toluca",        "2026-08-21T22:00:00Z", False, 24, 26, 50),
    ("mx-chivas-tijuana-2208",        "Liga MX Apertura 2026", "Guadalajara",          "Tijuana",       "2026-08-22T22:00:00Z", False, 44, 28, 28),
    ("mx-puebla-santos-2208",         "Liga MX Apertura 2026", "Puebla",               "Santos Laguna", "2026-08-22T22:00:00Z", False, 38, 30, 32),
    ("mx-cruzazul-atlas-2208",        "Liga MX Apertura 2026", "Cruz Azul",            "Atlas",         "2026-08-22T22:00:00Z", True,  56, 25, 19),
    ("mx-sanluis-pachuca-2308",       "Liga MX Apertura 2026", "Atlético de San Luis", "Pachuca",       "2026-08-23T22:00:00Z", False, 34, 28, 38),
    ("mx-pumas-necaxa-2308",          "Liga MX Apertura 2026", "Pumas UNAM",           "Necaxa",        "2026-08-23T22:00:00Z", False, 46, 28, 26),

    # ── Serie A · Jornada 1 (22 al 24 ago) ──
    ("sa-inter-monza-2208",           "Serie A Jornada 1", "Inter",     "Monza",      "2026-08-22T10:00:00Z", False, 68, 19, 13),
    ("sa-udinese-como-2208",          "Serie A Jornada 1", "Udinese",   "Como",       "2026-08-22T10:00:00Z", False, 38, 29, 33),
    ("sa-genoa-napoli-2208",          "Serie A Jornada 1", "Genoa",     "Napoli",     "2026-08-22T10:00:00Z", False, 20, 25, 55),
    ("sa-parma-cagliari-2208",        "Serie A Jornada 1", "Parma",     "Cagliari",   "2026-08-22T10:00:00Z", False, 40, 30, 30),
    ("sa-frosinone-juventus-2308",    "Serie A Jornada 1", "Frosinone", "Juventus",   "2026-08-23T10:00:00Z", False, 16, 23, 61),
    ("sa-venezia-lecce-2308",         "Serie A Jornada 1", "Venezia",   "Lecce",      "2026-08-23T10:00:00Z", False, 38, 30, 32),
    ("sa-atalanta-sassuolo-2308",     "Serie A Jornada 1", "Atalanta",  "Sassuolo",   "2026-08-23T10:00:00Z", False, 58, 24, 18),
    ("sa-torino-milan-2308",          "Serie A Jornada 1", "Torino",    "AC Milan",   "2026-08-23T10:00:00Z", True,  26, 27, 47),
    ("sa-bologna-lazio-2408",         "Serie A Jornada 1", "Bologna",   "Lazio",      "2026-08-24T10:00:00Z", False, 42, 28, 30),
    ("sa-roma-fiorentina-2408",       "Serie A Jornada 1", "Roma",      "Fiorentina", "2026-08-24T10:00:00Z", False, 44, 28, 28),
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
        for (mid, liga_jornada, local, visitante, ends_at_iso, trending,
             pct_local, pct_empate, pct_visitante) in MATCHES:

            total_pct = pct_local + pct_empate + pct_visitante
            if abs(total_pct - 100) > 1e-6:
                print(f"  WARNING {mid}: las pct suman {total_pct}, no 100")

            result = await db.execute(select(Market).where(Market.id == mid))
            if result.scalar_one_or_none() is not None:
                print(f"  SKIP  {mid} (already exists)")
                skipped += 1
                continue

            ends_at = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))

            # Nunca sembrar un mercado ya cerrado: si fue borrado a propósito
            # (cleanup-mercados-vencidos-sin-predicciones-*), no debe resucitar.
            if ends_at < datetime.now(timezone.utc):
                print(f"  SKIP  {mid} (ya vencido: ends_at={ends_at_iso}; no se siembran mercados cerrados)")
                skipped += 1
                continue

            market = Market(
                id=mid,
                question=f"{local} vs. {visitante} — ¿quién gana? ({liga_jornada})",
                description=f"Mercado 1X2 del partido {local} vs. {visitante}, {liga_jornada}. Elige local, empate o visitante.",
                category=MarketCategory.DEPORTES,
                resolution_criteria=RESOLUTION_CRITERIA,
                ends_at=ends_at,
                b=B,
                q_yes=0.0,
                q_no=0.0,
                yes_price=0.0,
                volume=0.0,
                num_trades=0,
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
            q_dict = init_qs_for_targets(targets, B)
            initial_prices = prices_multi(q_dict, B)

            outcome_rows = [
                ("local",     f"🏠 {local}",     pct_local),
                ("empate",    "🤝 Empate",       pct_empate),
                ("visitante", f"✈️ {visitante}", pct_visitante),
            ]
            for key, label, target_pct in outcome_rows:
                outcome = Outcome(
                    market_id=market.id,
                    outcome_key=key,
                    label=label,
                    q=q_dict[key],
                    price=initial_prices[key],
                )
                db.add(outcome)
                print(f"    outcome: {label:28s}  target={target_pct:.1f}%  actual={initial_prices[key]:.2f}%")

            db.add(PriceHistory(market_id=market.id, yes_price=0.0, volume_snapshot=0.0))

            inserted += 1
            print(f"  INSERT {mid} (multi, b={B})")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MATCHES)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
