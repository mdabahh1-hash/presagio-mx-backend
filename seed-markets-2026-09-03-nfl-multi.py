"""
seed-markets-2026-09-03-nfl-multi.py
=====================================
Siembra 5 mercados MULTI-OPCIÓN de la temporada NFL 2026 en Veredikt usando el
motor categórico nativo (markets.market_type='multi' + N filas en
market_outcomes). NO son grupos de binarios.

Mercados (todos DEPORTES / subcategoría "NFL", b=100, status open):
  · Campeón Super Bowl LXI (12 opciones)
  · Novato Ofensivo del Año 2026, OROY (9)
  · Novato Defensivo del Año 2026, DROY (9)
  · Jugador Ofensivo del Año 2026, OPOY (11)
  · Jugador Defensivo del Año 2026, DPOY (9)

Uso:
  python seed-markets-2026-09-03-nfl-multi.py --dry-run   # valida sin tocar la BD
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-09-03-nfl-multi.py'

Idempotente: si el id del padre ya existe hace SKIP (SELECT previo, sin ON CONFLICT).
Los outcomes de un padre nuevo nunca chocan con uq_outcome_market_key porque el
padre no existía; si el padre existe se salta completo (outcomes incluidos).

Resolución (NO en este script): POST /admin/markets/{id}/resolve con
{outcome_key: ganador}. El padre pasa a status 'resolved' y se setea
resolved_outcome_key.

Fechas: el Super Bowl LXI es el 14 de febrero de 2027 (confirmado). NFL Honors
2027 (11 de febrero) es estimación por el patrón de años anteriores (jueves
previo al Super Bowl); si la NFL publica otra fecha, actualizar ends_at de los
4 mercados de premios.
"""
import asyncio
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DRY_RUN = "--dry-run" in sys.argv


# ---------------------------------------------------------------------------
# Siembra LMSR multinomial (misma parametrización que el helper del repo
# init_qs_for_targets(targets, b) de los seeds multi anteriores):
#   n = número de opciones (incluye "Otro"), p_ref = 1/n
#   q_i = b * ln( (pct_i/100) / p_ref )
# NO usar la fórmula binaria b*ln(p/(1-p)) para multi.
# ---------------------------------------------------------------------------
def init_qs_for_targets(targets, b):
    n = len(targets)
    p_ref = 1.0 / n
    return [b * math.log((pct / 100.0) / p_ref) for pct in targets]


# ---------------------------------------------------------------------------
# MERCADOS
# outcomes: (outcome_key, label con emoji, pct). Los pct de cada mercado suman 100.
# ---------------------------------------------------------------------------
MARKETS = [
    {
        "id": "nfl-campeon-super-bowl-lxi",
        "question": "¿Quién ganará el Super Bowl LXI (temporada 2026)?",
        "description": "La temporada 2026 de la NFL arranca con los Rams como favoritos tras sumar a Myles Garrett, Trent McDuffie y el regreso de Aaron Donald. Los Seahawks defienden el título y 14 equipos abren a +2000 o mejor. El Super Bowl LXI se juega el 14 de febrero de 2027 en SoFi Stadium, Los Ángeles.",
        "category": "DEPORTES",
        "subcategory": "NFL",
        "resolution_criteria": "Se resuelve con el equipo que gane el Super Bowl LXI según el resultado oficial publicado por la NFL (nfl.com). Si el ganador no está entre las opciones nombradas, resuelve 'Otro'.",
        "market_type": "multi",
        "b": 100.0,
        "ends_at": datetime(2027, 2, 15, 4, 0, 0, tzinfo=timezone.utc),
        "trending": True,
        "outcomes": [
            ("rams",     "🐏 Los Angeles Rams",      13),
            ("bills",    "🦬 Buffalo Bills",         7),
            ("ravens",   "🐦‍⬛ Baltimore Ravens",     7),
            ("seahawks", "🦅 Seattle Seahawks",      7),
            ("eagles",   "🦅 Philadelphia Eagles",   5),
            ("patriots", "🇺🇸 New England Patriots", 5),
            ("chiefs",   "🏹 Kansas City Chiefs",    5),
            ("chargers", "⚡ Los Angeles Chargers",  5),
            ("packers",  "🧀 Green Bay Packers",     4),
            ("49ers",    "⛏️ San Francisco 49ers",   4),
            ("cowboys",  "⭐ Dallas Cowboys",        3),
            ("otro",     "🏈 Otro equipo",           35),
        ],
    },
    {
        "id": "nfl-oroy-2026",
        "question": "¿Quién será el Novato Ofensivo del Año (OROY) de la NFL 2026?",
        "description": "La clase 2026 no tiene un QB titular claro desde la semana 1 (Mendoza empieza detrás de Kirk Cousins en Raiders), así que el premio está más abierto que otros años. Jeremiyah Love (Cardinals) abre como favorito, pero juega detrás de una de las peores líneas ofensivas de la liga.",
        "category": "DEPORTES",
        "subcategory": "NFL",
        "resolution_criteria": "Se resuelve con el jugador que reciba el premio AP NFL Offensive Rookie of the Year anunciado en la gala NFL Honors 2027 (fuente oficial NFL y Associated Press). Si el ganador no está nombrado, resuelve 'Otro'.",
        "market_type": "multi",
        "b": 100.0,
        "ends_at": datetime(2027, 2, 12, 5, 0, 0, tzinfo=timezone.utc),
        "trending": True,
        "outcomes": [
            ("love",       "🏃 Jeremiyah Love (RB, Cardinals)", 16),
            ("tate",       "🎯 Carnell Tate (WR, Titans)",      14),
            ("mendoza",    "🎯 Fernando Mendoza (QB, Raiders)", 13),
            ("price",      "🏃 Jadarian Price (RB, Seahawks)",  12),
            ("stribling",  "🎯 De'Zhaun Stribling (WR)",        9),
            ("lemon",      "🎯 Makai Lemon (WR, Eagles)",       6),
            ("concepcion", "🎯 KC Concepcion (WR)",             4),
            ("beck",       "🎯 Carson Beck (QB)",               3),
            ("otro",       "🏈 Otro jugador",                   23),
        ],
    },
    {
        "id": "nfl-droy-2026",
        "question": "¿Quién será el Novato Defensivo del Año (DROY) de la NFL 2026?",
        "description": "Una de las primeras rondas defensivas más profundas en años. David Bailey (pick 2, Jets) llegó como favorito, pero Rueben Bain Jr. (pick 15, Bucs) lo alcanzó en las cuotas durante la pretemporada. Seis jugadores abren por debajo de +1000.",
        "category": "DEPORTES",
        "subcategory": "NFL",
        "resolution_criteria": "Se resuelve con el jugador que reciba el premio AP NFL Defensive Rookie of the Year anunciado en NFL Honors 2027 (fuente oficial NFL y Associated Press). Si el ganador no está nombrado, resuelve 'Otro'.",
        "market_type": "multi",
        "b": 100.0,
        "ends_at": datetime(2027, 2, 12, 5, 0, 0, tzinfo=timezone.utc),
        "trending": False,
        "outcomes": [
            ("bain",      "🏴‍☠️ Rueben Bain Jr. (EDGE, Buccaneers)", 15),
            ("bailey",    "✈️ David Bailey (EDGE, Jets)",            14),
            ("downs",     "⭐ Caleb Downs (S, Cowboys)",             11),
            ("styles",    "🛡️ Sonny Styles (LB, Commanders)",       9),
            ("reese",     "🗽 Arvell Reese (LB, Giants)",            9),
            ("delane",    "🏹 Mansoor Delane (CB, Chiefs)",          8),
            ("rodriguez", "🐬 Jacob Rodriguez (LB, Dolphins)",       5),
            ("mesidor",   "⚡ Akheem Mesidor (EDGE, Chargers)",      5),
            ("otro",      "🏈 Otro jugador",                         24),
        ],
    },
    {
        "id": "nfl-opoy-2026",
        "question": "¿Quién será el Jugador Ofensivo del Año (OPOY) de la NFL 2026?",
        "description": "Desde 2020 el premio se lo han llevado tres corredores y tres receptores, casi nunca un QB (el MVP absorbe a los quarterbacks). Jahmyr Gibbs abre como favorito tras la salida de David Montgomery de Detroit. Jaxon Smith-Njigba, el ganador 2025, aparece apenas octavo.",
        "category": "DEPORTES",
        "subcategory": "NFL",
        "resolution_criteria": "Se resuelve con el jugador que reciba el premio AP NFL Offensive Player of the Year anunciado en NFL Honors 2027 (fuente oficial NFL y Associated Press). Si el ganador no está nombrado, resuelve 'Otro'.",
        "market_type": "multi",
        "b": 100.0,
        "ends_at": datetime(2027, 2, 12, 5, 0, 0, tzinfo=timezone.utc),
        "trending": True,
        "outcomes": [
            ("gibbs",     "🦁 Jahmyr Gibbs (RB, Lions)",            12),
            ("robinson",  "🦅 Bijan Robinson (RB, Falcons)",        8),
            ("chase",     "🐅 Ja'Marr Chase (WR, Bengals)",         7),
            ("nacua",     "🐏 Puka Nacua (WR, Rams)",               6),
            ("jefferson", "🟣 Justin Jefferson (WR, Vikings)",      5),
            ("mccaffrey", "⛏️ Christian McCaffrey (RB, 49ers)",     4),
            ("barkley",   "🦅 Saquon Barkley (RB, Eagles)",         4),
            ("jsn",       "🦅 Jaxon Smith-Njigba (WR, Seahawks)",   4),
            ("lamb",      "⭐ CeeDee Lamb (WR, Cowboys)",           3),
            ("henry",     "🐦‍⬛ Derrick Henry (RB, Ravens)",         3),
            ("otro",      "🏈 Otro jugador",                        44),
        ],
    },
    {
        "id": "nfl-dpoy-2026",
        "question": "¿Quién será el Jugador Defensivo del Año (DPOY) de la NFL 2026?",
        "description": "Myles Garrett ganó el DPOY 2025 con los 50 votos y récord de 23 capturas, y ahora juega en los Rams junto a Aaron Donald. Busca ser bicampeón consecutivo y ganar tres en cuatro años. Micah Parsons cayó en las cuotas por lesión y podría volver hasta la semana 6.",
        "category": "DEPORTES",
        "subcategory": "NFL",
        "resolution_criteria": "Se resuelve con el jugador que reciba el premio AP NFL Defensive Player of the Year anunciado en NFL Honors 2027 (fuente oficial NFL y Associated Press). Si el ganador no está nombrado, resuelve 'Otro'.",
        "market_type": "multi",
        "b": 100.0,
        "ends_at": datetime(2027, 2, 12, 5, 0, 0, tzinfo=timezone.utc),
        "trending": True,
        "outcomes": [
            ("garrett",    "🐏 Myles Garrett (EDGE, Rams)",        15),
            ("anderson",   "🤠 Will Anderson Jr. (EDGE, Texans)",  11),
            ("hutchinson", "🦁 Aidan Hutchinson (EDGE, Lions)",    9),
            ("crosby",     "☠️ Maxx Crosby (EDGE, Raiders)",       6),
            ("bonitto",    "🐴 Nik Bonitto (EDGE, Broncos)",       6),
            ("bosa",       "⛏️ Nick Bosa (EDGE, 49ers)",           4),
            ("watt",       "🖤 T.J. Watt (EDGE, Steelers)",        4),
            ("burns",      "🗽 Brian Burns (EDGE, Giants)",        4),
            ("otro",       "🏈 Otro jugador",                      41),
        ],
    },
]


def build_outcomes(m):
    """Devuelve la lista de outcomes con q sembrado por init_qs_for_targets."""
    targets = [pct for _, _, pct in m["outcomes"]]
    if sum(targets) != 100:
        print(f"  WARNING {m['id']}: los pct suman {sum(targets)}, no 100")
    qs = init_qs_for_targets(targets, m["b"])
    return [
        {"outcome_key": key, "label": label, "q": q, "price": float(pct)}
        for (key, label, pct), q in zip(m["outcomes"], qs)
    ]


def validate():
    ids = [m["id"] for m in MARKETS]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"ids duplicados: {dupes}"
    now = datetime.now(timezone.utc)
    for m in MARKETS:
        assert len(m["id"]) <= 100, f"{m['id']}: id demasiado largo"
        assert m["market_type"] == "multi", f"{m['id']}: market_type debe ser 'multi'"
        assert m["category"] == "DEPORTES", f"{m['id']}: categoría no permitida (solo DEPORTES)"
        assert m["ends_at"].tzinfo is not None, f"{m['id']}: ends_at debe ser tz-aware"
        if m["ends_at"] <= now:
            print(f"  WARNING {m['id']}: ends_at ya pasó ({m['ends_at'].isoformat()}), se saltará")
        keys = [k for k, _, _ in m["outcomes"]]
        assert len(keys) == len(set(keys)), f"{m['id']}: outcome_key duplicado"
        for k in keys:
            assert k.isascii() and " " not in k, f"{m['id']}: outcome_key inválido {k!r}"
        for _, label, _ in m["outcomes"]:
            assert len(label) <= 200, f"{m['id']}: label demasiado largo {label!r}"
    print(f"OK: {len(MARKETS)} mercados por sembrar, ids y outcome_keys únicos, ends_at tz-aware en el futuro.")


async def main():
    from sqlalchemy import select
    from app.database import AsyncSessionLocal, engine
    from app.models.market import Market, MarketCategory, MarketStatus
    from app.models.price_history import PriceHistory
    from app.models.outcome import Outcome as OutcomeModel

    inserted = skipped = 0
    async with AsyncSessionLocal() as db:
        for m in MARKETS:
            exists = await db.execute(select(Market).where(Market.id == m["id"]))
            if exists.scalar_one_or_none() is not None:
                print(f"  SKIP   {m['id']} (ya existe)")
                skipped += 1
                continue
            if m["ends_at"] <= datetime.now(timezone.utc):
                print(f"  SKIP   {m['id']} (ya vencido: {m['ends_at'].isoformat()})")
                skipped += 1
                continue
            outcomes = build_outcomes(m)
            db.add(Market(
                id=m["id"], question=m["question"], description=m["description"],
                category=MarketCategory[m["category"]], subcategory=m.get("subcategory"),
                resolution_criteria=m["resolution_criteria"],
                market_type=m["market_type"], b=m["b"], ends_at=m["ends_at"],
                status=MarketStatus.OPEN, trending=m["trending"],
                volume=0.0, num_trades=0,
            ))
            await db.flush()  # fija el id del padre antes de los outcomes
            for o in outcomes:
                db.add(OutcomeModel(market_id=m["id"], outcome_key=o["outcome_key"],
                                    label=o["label"], q=o["q"], price=o["price"]))
                print(f"           + {o['outcome_key']:<11} {o['price']:>5.1f}%  q={o['q']:.2f}")
            db.add(PriceHistory(market_id=m["id"], yes_price=0.0, volume_snapshot=0.0))
            print(f"  INSERT {m['id']}  b={m['b']}  trending={m['trending']}  "
                  f"n={len(outcomes)}  ends_at={m['ends_at'].isoformat()}")
            inserted += 1
        await db.commit()
    await engine.dispose()
    print(f"\nDone. insertados={inserted} saltados={skipped}")


if __name__ == "__main__":
    validate()
    if DRY_RUN:
        for m in MARKETS:
            outcomes = build_outcomes(m)
            print(f"\n{m['id']}  {m['subcategory']}  b={m['b']}  trending={m['trending']}  "
                  f"{m['ends_at'].strftime('%Y-%m-%d %H:%MZ')}")
            for o in outcomes:
                print(f"    {o['outcome_key']:<11} {o['price']:>5.1f}%  q={o['q']:>8.2f}  {o['label']}")
        print("\n(dry-run) No se tocó la base de datos.")
    else:
        asyncio.run(main())
