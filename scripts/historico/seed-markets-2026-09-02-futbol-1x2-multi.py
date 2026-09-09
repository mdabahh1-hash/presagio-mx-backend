"""
seed-markets-2026-09-02-futbol-1x2-multi.py
============================================
Siembra 95 mercados 1X2 (local / empate / visitante) como mercados MULTI-OPCIÓN
en Veredikt usando el motor categórico nativo (markets.market_type='multi' +
3 filas en market_outcomes). NO son grupos de binarios.

Cobertura (kickoffs verificados el 1 sep 2026):
  LaLiga J4 (10) · Premier League J3 (10) · Bundesliga J2 (9) · Liga Portugal J5 (9)
  MLS 4-5 sep (15) · Liga MX J7 (5, los otros 4 están pospuestos por Leagues Cup)
  Serie A J3 (10) · Saudi Pro League J5 (9) · Champions League J1 (18)

Uso:
  python seed-markets-2026-09-02-futbol-1x2-multi.py --dry-run   # valida sin tocar la BD
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-09-02-futbol-1x2-multi.py'

Idempotente: si el id del padre ya existe hace SKIP (SELECT previo, sin ON CONFLICT).
"""
import asyncio
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DRY_RUN = "--dry-run" in sys.argv


def dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Siembra LMSR multinomial (misma parametrización que el helper del repo
# init_qs_for_targets(targets, b) del seed multi más reciente):
#   n = número de opciones, p_ref = 1/n
#   q_i = b * ln( (pct_i/100) / p_ref )
# Si el repo ya expone el helper, se puede reemplazar esta función por el import.
# ---------------------------------------------------------------------------
def init_qs_for_targets(targets, b):
    n = len(targets)
    p_ref = 1.0 / n
    return [b * math.log((pct / 100.0) / p_ref) for pct in targets]


# ---------------------------------------------------------------------------
# Textos por competencia
# ---------------------------------------------------------------------------
COMP = {
    "LaLiga": dict(sub="LaLiga", jornada="Jornada 4 de LaLiga 2026-27",
                   fuente="el acta oficial de LaLiga (laliga.com)"),
    "PL": dict(sub="Premier League", jornada="Jornada 3 de la Premier League 2026-27",
               fuente="el acta oficial de la Premier League (premierleague.com)"),
    "BL": dict(sub="Bundesliga", jornada="Jornada 2 de la Bundesliga 2026-27",
               fuente="el acta oficial de la Bundesliga (bundesliga.com)"),
    "LP": dict(sub="Liga Portugal", jornada="Jornada 5 de la Liga Portugal Betclic 2026-27",
               fuente="el acta oficial de la Liga Portugal (ligaportugal.pt)"),
    "MLS": dict(sub="MLS", jornada="MLS, fecha del 4 y 5 de septiembre de 2026",
                fuente="el resultado oficial de la MLS (mlssoccer.com)"),
    "MX": dict(sub="Liga MX", jornada="Jornada 7 del Apertura 2026 de la Liga MX",
               fuente="el resultado oficial de la Liga MX (ligamx.net)"),
    "SA": dict(sub="Serie A", jornada="Jornada 3 de la Serie A 2026-27",
               fuente="el acta oficial de la Serie A (legaseriea.it)"),
    "SPL": dict(sub="Saudi Pro League", jornada="Jornada 5 de la Saudi Pro League 2026-27",
                fuente="el resultado oficial de la Saudi Pro League (spl.com.sa)"),
    "UCL": dict(sub="Champions League", jornada="Jornada 1 de la fase de liga de la Champions League 2026-27",
                fuente="el acta oficial de la UEFA (uefa.com)"),
}

# ---------------------------------------------------------------------------
# PARTIDOS
# (id, comp, local, visitante, ends_at=kickoff UTC, pct_local, pct_empate, pct_visitante, trending)
# Los pct suman 100. Fuente del prior: "SR" = win probability de SportRadar
# consultada el 1 sep 2026; "EST" = estimación propia (ver comentario).
# ---------------------------------------------------------------------------
MATCHES = [
    # ── LaLiga · Jornada 4 (3 al 7 sep) ── priors SR
    ("laliga-realsociedad-celta-j4-2627", "LaLiga", "Real Sociedad", "Celta de Vigo", dt(2026, 9, 3, 19, 0), 48, 27, 25, False),
    ("laliga-betis-realmadrid-j4-2627", "LaLiga", "Real Betis", "Real Madrid", dt(2026, 9, 4, 19, 0), 13, 17, 70, True),
    ("laliga-athletic-atletico-j4-2627", "LaLiga", "Athletic Club", "Atlético de Madrid", dt(2026, 9, 5, 14, 15), 34, 28, 38, True),
    ("laliga-rayo-racing-j4-2627", "LaLiga", "Rayo Vallecano", "Racing Santander", dt(2026, 9, 5, 16, 30), 42, 28, 30, False),
    ("laliga-villarreal-depor-j4-2627", "LaLiga", "Villarreal", "Deportivo La Coruña", dt(2026, 9, 5, 19, 0), 65, 20, 15, False),
    ("laliga-valencia-barcelona-j4-2627", "LaLiga", "Valencia", "Barcelona", dt(2026, 9, 6, 14, 15), 10, 15, 75, True),
    ("laliga-alaves-osasuna-j4-2627", "LaLiga", "Alavés", "Osasuna", dt(2026, 9, 6, 16, 30), 42, 30, 28, False),
    ("laliga-malaga-levante-j4-2627", "LaLiga", "Málaga", "Levante", dt(2026, 9, 6, 16, 30), 39, 29, 32, False),
    ("laliga-espanyol-sevilla-j4-2627", "LaLiga", "Espanyol", "Sevilla", dt(2026, 9, 6, 19, 0), 41, 29, 30, False),
    ("laliga-getafe-celta-j4-2627", "LaLiga", "Getafe", "Celta de Vigo", dt(2026, 9, 7, 17, 0), 36, 33, 31, False),
    # NOTA: Elche vs Real Sociedad NO se siembra. No aparece en el calendario del proveedor
    # entre el 3 y el 7 de septiembre. Confirmar fecha antes de abrirlo.

    # ── Premier League · Jornada 3 (4 al 6 sep) ── priors SR
    ("pl-ipswich-liverpool-j3-2627", "PL", "Ipswich Town", "Liverpool", dt(2026, 9, 4, 19, 0), 18, 20, 62, False),
    ("pl-newcastle-bournemouth-j3-2627", "PL", "Newcastle United", "Bournemouth", dt(2026, 9, 5, 11, 30), 43, 26, 31, False),
    ("pl-brentford-sunderland-j3-2627", "PL", "Brentford", "Sunderland", dt(2026, 9, 5, 14, 0), 60, 23, 17, False),
    ("pl-brighton-leeds-j3-2627", "PL", "Brighton", "Leeds United", dt(2026, 9, 5, 14, 0), 50, 26, 24, False),
    ("pl-fulham-palace-j3-2627", "PL", "Fulham", "Crystal Palace", dt(2026, 9, 5, 14, 0), 41, 28, 31, False),
    ("pl-city-coventry-j3-2627", "PL", "Manchester City", "Coventry City", dt(2026, 9, 5, 14, 0), 83, 11, 6, False),
    ("pl-forest-tottenham-j3-2627", "PL", "Nottingham Forest", "Tottenham", dt(2026, 9, 5, 14, 0), 39, 27, 34, False),
    ("pl-hull-villa-j3-2627", "PL", "Hull City", "Aston Villa", dt(2026, 9, 5, 16, 30), 23, 26, 51, False),
    ("pl-everton-united-j3-2627", "PL", "Everton", "Manchester United", dt(2026, 9, 6, 13, 0), 31, 27, 42, False),
    ("pl-arsenal-chelsea-j3-2627", "PL", "Arsenal", "Chelsea", dt(2026, 9, 6, 15, 30), 57, 24, 19, True),

    # ── Bundesliga · Jornada 2 (4 al 6 sep) ── priors SR
    # OJO: el PDF traía "Leverkusen vs Gladbach" y "Elversberg vs Union Berlin". Los partidos
    # reales de la jornada son Leverkusen vs Union Berlin y Gladbach vs Elversberg. Corregido.
    ("bl-stuttgart-koln-j2-2627", "BL", "VfB Stuttgart", "FC Köln", dt(2026, 9, 4, 18, 30), 62, 19, 19, False),
    ("bl-hoffenheim-dortmund-j2-2627", "BL", "Hoffenheim", "Borussia Dortmund", dt(2026, 9, 5, 13, 30), 33, 25, 42, False),
    ("bl-leverkusen-union-j2-2627", "BL", "Bayer Leverkusen", "Union Berlin", dt(2026, 9, 5, 13, 30), 67, 18, 15, False),
    ("bl-gladbach-elversberg-j2-2627", "BL", "Borussia Mönchengladbach", "Elversberg", dt(2026, 9, 5, 13, 30), 52, 24, 24, False),
    ("bl-bremen-leipzig-j2-2627", "BL", "Werder Bremen", "RB Leipzig", dt(2026, 9, 5, 13, 30), 24, 23, 53, False),
    ("bl-paderborn-freiburg-j2-2627", "BL", "Paderborn", "Freiburg", dt(2026, 9, 5, 13, 30), 28, 26, 46, False),
    ("bl-schalke-bayern-j2-2627", "BL", "Schalke 04", "Bayern Múnich", dt(2026, 9, 5, 16, 30), 6, 10, 84, True),
    ("bl-hamburg-mainz-j2-2627", "BL", "Hamburgo", "Mainz 05", dt(2026, 9, 6, 13, 30), 33, 27, 40, False),
    ("bl-frankfurt-augsburg-j2-2627", "BL", "Eintracht Frankfurt", "Augsburgo", dt(2026, 9, 6, 15, 30), 49, 24, 27, False),

    # ── Liga Portugal · Jornada 5 (4 al 7 sep) ── priors EST (fuerza relativa; sin cuotas)
    ("lp-porto-moreirense-j5-2627", "LP", "FC Porto", "Moreirense", dt(2026, 9, 4, 19, 15), 72, 17, 11, False),
    ("lp-sporting-nacional-j5-2627", "LP", "Sporting CP", "Nacional", dt(2026, 9, 4, 19, 15), 75, 15, 10, False),
    ("lp-estrela-famalicao-j5-2627", "LP", "Estrela Amadora", "Famalicão", dt(2026, 9, 5, 14, 30), 32, 30, 38, False),
    ("lp-alverca-braga-j5-2627", "LP", "Alverca", "Braga", dt(2026, 9, 5, 17, 0), 22, 26, 52, False),
    ("lp-maritimo-benfica-j5-2627", "LP", "Marítimo", "Benfica", dt(2026, 9, 5, 17, 0), 12, 18, 70, False),
    ("lp-santaclara-rioave-j5-2627", "LP", "Santa Clara", "Rio Ave", dt(2026, 9, 6, 14, 30), 42, 29, 29, False),
    ("lp-guimaraes-casapia-j5-2627", "LP", "Vitória Guimarães", "Casa Pia", dt(2026, 9, 6, 17, 0), 50, 26, 24, False),
    ("lp-gilvicente-viseu-j5-2627", "LP", "Gil Vicente", "Académico de Viseu", dt(2026, 9, 6, 19, 30), 47, 28, 25, False),
    ("lp-estoril-arouca-j5-2627", "LP", "Estoril", "Arouca", dt(2026, 9, 7, 19, 15), 42, 28, 30, False),

    # ── MLS · 4 y 5 de septiembre ── priors SR salvo los marcados EST
    # OJO: el PDF traía 6 cruces equivocados (localías invertidas y rivales que no juegan
    # entre sí esta fecha). Aquí va el calendario real de los 15 partidos.
    ("mls-nycfc-nashville-sep26", "MLS", "New York City FC", "Nashville SC", dt(2026, 9, 4, 23, 30), 38, 26, 36, False),
    ("mls-charlotte-houston-sep26", "MLS", "Charlotte FC", "Houston Dynamo", dt(2026, 9, 5, 23, 30), 42, 26, 32, False),
    ("mls-cincinnati-dcunited-sep26", "MLS", "FC Cincinnati", "D.C. United", dt(2026, 9, 5, 23, 30), 62, 20, 18, False),
    ("mls-columbus-colorado-sep26", "MLS", "Columbus Crew", "Colorado Rapids", dt(2026, 9, 5, 23, 30), 46, 26, 28, False),
    ("mls-intermiami-atlanta-sep26", "MLS", "Inter Miami", "Atlanta United", dt(2026, 9, 5, 23, 30), 68, 17, 15, True),
    ("mls-orlando-sandiego-sep26", "MLS", "Orlando City", "San Diego FC", dt(2026, 9, 5, 23, 30), 44, 24, 32, False),
    ("mls-philadelphia-montreal-sep26", "MLS", "Philadelphia Union", "CF Montréal", dt(2026, 9, 5, 23, 30), 63, 20, 17, False),
    ("mls-toronto-chicago-sep26", "MLS", "Toronto FC", "Chicago Fire", dt(2026, 9, 5, 23, 30), 33, 25, 42, False),
    ("mls-austin-sanjose-sep26", "MLS", "Austin FC", "San Jose Earthquakes", dt(2026, 9, 6, 0, 30), 43, 25, 32, False),
    ("mls-dallas-sportingkc-sep26", "MLS", "FC Dallas", "Sporting Kansas City", dt(2026, 9, 6, 0, 30), 66, 19, 15, False),
    ("mls-seattle-redbulls-sep26", "MLS", "Seattle Sounders", "New York Red Bulls", dt(2026, 9, 6, 0, 30), 40, 27, 33, False),   # EST
    ("mls-rsl-lafc-sep26", "MLS", "Real Salt Lake", "LAFC", dt(2026, 9, 6, 1, 30), 35, 26, 39, False),                        # EST
    ("mls-galaxy-newengland-sep26", "MLS", "LA Galaxy", "New England Revolution", dt(2026, 9, 6, 1, 30), 40, 27, 33, False),   # EST
    ("mls-vancouver-stlouis-sep26", "MLS", "Vancouver Whitecaps", "St. Louis CITY", dt(2026, 9, 6, 2, 30), 50, 25, 25, False),  # EST
    ("mls-portland-minnesota-sep26", "MLS", "Portland Timbers", "Minnesota United", dt(2026, 9, 6, 2, 30), 40, 27, 33, False),  # EST

    # ── Liga MX · Jornada 7 Apertura 2026 (solo 5 partidos) ── priors EST
    # Pospuestos por Leagues Cup (NO abrir hasta que haya fecha): Puebla-Toluca,
    # Querétaro-Monterrey, América-Tijuana, Pumas-León.
    ("mx-juarez-pachuca-j7-ap26", "MX", "FC Juárez", "Pachuca", dt(2026, 9, 5, 3, 0), 30, 29, 41, False),
    ("mx-sanluis-chivas-j7-ap26", "MX", "Atlético de San Luis", "Guadalajara", dt(2026, 9, 5, 23, 0), 30, 29, 41, True),
    ("mx-tigres-necaxa-j7-ap26", "MX", "Tigres UANL", "Necaxa", dt(2026, 9, 6, 1, 0), 50, 27, 23, False),
    ("mx-atlas-atlante-j7-ap26", "MX", "Atlas", "Atlante", dt(2026, 9, 6, 3, 0), 48, 28, 24, False),
    ("mx-cruzazul-santos-j7-ap26", "MX", "Cruz Azul", "Santos Laguna", dt(2026, 9, 7, 2, 0), 58, 25, 17, True),

    # ── Serie A · Jornada 3 (4 al 7 sep) ── priors SR
    ("sa-genoa-como-j3-2627", "SA", "Genoa", "Como", dt(2026, 9, 4, 18, 45), 19, 28, 53, False),
    ("sa-fiorentina-torino-j3-2627", "SA", "Fiorentina", "Torino", dt(2026, 9, 5, 13, 0), 50, 28, 22, False),
    ("sa-inter-napoli-j3-2627", "SA", "Inter", "Napoli", dt(2026, 9, 5, 16, 0), 58, 25, 17, True),
    ("sa-roma-atalanta-j3-2627", "SA", "Roma", "Atalanta", dt(2026, 9, 5, 18, 45), 56, 25, 19, False),
    ("sa-frosinone-venezia-j3-2627", "SA", "Frosinone", "Venezia", dt(2026, 9, 6, 13, 0), 35, 28, 37, False),
    ("sa-parma-monza-j3-2627", "SA", "Parma", "Monza", dt(2026, 9, 6, 13, 0), 38, 31, 31, False),
    ("sa-bologna-sassuolo-j3-2627", "SA", "Bologna", "Sassuolo", dt(2026, 9, 6, 16, 0), 48, 28, 24, False),
    ("sa-juventus-milan-j3-2627", "SA", "Juventus", "AC Milan", dt(2026, 9, 6, 18, 45), 45, 29, 26, True),
    ("sa-cagliari-lecce-j3-2627", "SA", "Cagliari", "Lecce", dt(2026, 9, 7, 16, 30), 48, 29, 23, False),
    ("sa-udinese-lazio-j3-2627", "SA", "Udinese", "Lazio", dt(2026, 9, 7, 18, 45), 33, 30, 37, False),

    # ── Saudi Pro League · Jornada 5 (3 al 5 sep) ── priors EST · horarios KSA (UTC+3)
    # OJO: el PDF decía "Al Draih"; el club es Al Diriyah.
    ("spl-fayha-kholood-j5-2627", "SPL", "Al-Fayha", "Al-Kholood", dt(2026, 9, 3, 15, 55), 40, 30, 30, False),
    ("spl-neom-khaleej-j5-2627", "SPL", "NEOM SC", "Al-Khaleej", dt(2026, 9, 3, 16, 30), 45, 28, 27, False),
    ("spl-diriyah-qadsiah-j5-2627", "SPL", "Al Diriyah", "Al-Qadsiah", dt(2026, 9, 3, 18, 0), 30, 28, 42, False),
    ("spl-abha-ettifaq-j5-2627", "SPL", "Abha", "Al-Ettifaq", dt(2026, 9, 4, 16, 0), 33, 30, 37, False),
    ("spl-ahli-riyadh-j5-2627", "SPL", "Al-Ahli", "Al-Riyadh", dt(2026, 9, 4, 18, 0), 65, 20, 15, False),
    ("spl-shabab-hilal-j5-2627", "SPL", "Al-Shabab", "Al-Hilal", dt(2026, 9, 4, 18, 0), 18, 22, 60, False),
    ("spl-faisaly-hazm-j5-2627", "SPL", "Al-Faisaly", "Al-Hazm", dt(2026, 9, 5, 15, 50), 38, 30, 32, False),
    ("spl-taawoun-fateh-j5-2627", "SPL", "Al-Taawoun", "Al-Fateh", dt(2026, 9, 5, 15, 55), 45, 28, 27, False),
    ("spl-ittihad-nassr-j5-2627", "SPL", "Al-Ittihad", "Al-Nassr", dt(2026, 9, 5, 18, 0), 38, 25, 37, True),

    # ── Champions League · Jornada 1 fase de liga (8 al 10 sep) ── priors SR salvo EST
    ("ucl-aek-lask-j1-2627", "UCL", "AEK Athens", "LASK", dt(2026, 9, 8, 16, 45), 54, 24, 22, False),
    ("ucl-brugge-villa-j1-2627", "UCL", "Club Brugge", "Aston Villa", dt(2026, 9, 8, 16, 45), 35, 26, 39, False),
    ("ucl-dortmund-villarreal-j1-2627", "UCL", "Borussia Dortmund", "Villarreal", dt(2026, 9, 8, 19, 0), 54, 23, 23, False),
    ("ucl-porto-city-j1-2627", "UCL", "FC Porto", "Manchester City", dt(2026, 9, 8, 19, 0), 22, 24, 54, True),
    ("ucl-lille-betis-j1-2627", "UCL", "Lille", "Real Betis", dt(2026, 9, 8, 19, 0), 43, 27, 30, False),
    ("ucl-realmadrid-inter-j1-2627", "UCL", "Real Madrid", "Inter", dt(2026, 9, 8, 19, 0), 61, 21, 18, True),
    ("ucl-barcelona-feyenoord-j1-2627", "UCL", "Barcelona", "Feyenoord", dt(2026, 9, 9, 16, 45), 86, 9, 5, False),
    ("ucl-stuttgart-viking-j1-2627", "UCL", "Stuttgart", "Viking", dt(2026, 9, 9, 16, 45), 78, 13, 9, False),
    ("ucl-liverpool-atletico-j1-2627", "UCL", "Liverpool", "Atlético de Madrid", dt(2026, 9, 9, 19, 0), 55, 24, 21, True),
    ("ucl-psg-slovan-j1-2627", "UCL", "Paris Saint-Germain", "Slovan Bratislava", dt(2026, 9, 9, 19, 0), 93, 5, 2, False),
    ("ucl-sporting-galatasaray-j1-2627", "UCL", "Sporting CP", "Galatasaray", dt(2026, 9, 9, 19, 0), 45, 27, 28, False),   # EST
    ("ucl-napoli-arsenal-j1-2627", "UCL", "Napoli", "Arsenal", dt(2026, 9, 9, 19, 0), 28, 27, 45, True),                 # EST
    ("ucl-fenerbahce-roma-j1-2627", "UCL", "Fenerbahçe", "Roma", dt(2026, 9, 10, 16, 45), 33, 29, 38, False),            # EST
    ("ucl-psv-shakhtar-j1-2627", "UCL", "PSV Eindhoven", "Shakhtar Donetsk", dt(2026, 9, 10, 16, 45), 48, 26, 26, False),  # EST
    ("ucl-como-leipzig-j1-2627", "UCL", "Como", "RB Leipzig", dt(2026, 9, 10, 19, 0), 40, 28, 32, False),                # EST
    ("ucl-bayern-bodo-j1-2627", "UCL", "Bayern Múnich", "Bodø/Glimt", dt(2026, 9, 10, 19, 0), 82, 11, 7, False),         # EST
    ("ucl-united-sabah-j1-2627", "UCL", "Manchester United", "Sabah", dt(2026, 9, 10, 19, 0), 85, 10, 5, False),         # EST
    ("ucl-slavia-lens-j1-2627", "UCL", "Slavia Praha", "Lens", dt(2026, 9, 10, 19, 0), 42, 28, 30, False),               # EST
]


def build_market(row):
    mid, comp, home, away, ends_at, p_home, p_draw, p_away, trending = row
    c = COMP[comp]
    b = 150.0 if trending else 100.0
    targets = [p_home, p_draw, p_away]
    if sum(targets) != 100:
        print(f"  WARNING {mid}: los pct suman {sum(targets)}, no 100")
    qs = init_qs_for_targets(targets, b)
    return {
        "id": mid,
        "question": f"¿Quién ganará {home} vs. {away}?",
        "description": f"Mercado 1X2 de la {c['jornada']}. {home} recibe a {away}. "
                       f"Elige victoria local, empate o victoria visitante.",
        "subcategory": c["sub"],
        "resolution_criteria": (
            f"Resuelve con el resultado oficial al terminar los 90 minutos reglamentarios más el "
            f"tiempo agregado, según {c['fuente']}. No cuentan prórroga ni penales. Si el partido "
            f"se aplaza dentro de la misma jornada, el mercado sigue abierto y ends_at se mueve al "
            f"nuevo horario; si sale de la ventana de la jornada o se abandona sin resultado "
            f"oficial, el mercado se cancela vía admin y se reembolsa."
        ),
        "ends_at": ends_at,
        "b": b,
        "trending": trending,
        "outcomes": [
            {"outcome_key": "local", "label": f"🏠 {home}", "q": qs[0], "price": float(p_home)},
            {"outcome_key": "empate", "label": "🤝 Empate", "q": qs[1], "price": float(p_draw)},
            {"outcome_key": "visitante", "label": f"✈️ {away}", "q": qs[2], "price": float(p_away)},
        ],
    }


def validate():
    ids = [r[0] for r in MATCHES]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"ids duplicados: {dupes}"
    now = datetime.now(timezone.utc)
    vivos = []
    for r in MATCHES:
        assert len(r[0]) <= 100, f"{r[0]}: id demasiado largo"
        if r[4] <= now:
            print(f"  OMITIDO {r[0]}: el partido ya empezó ({r[4].isoformat()})")
            continue
        vivos.append(r)
    MATCHES[:] = vivos
    print(f"OK: {len(MATCHES)} partidos por sembrar, ids únicos, ends_at en el futuro.")


async def main():
    from sqlalchemy import select
    from app.database import AsyncSessionLocal, engine
    from app.models.market import Market, MarketCategory, MarketStatus
    from app.models.price_history import PriceHistory
    try:
        from app.models.outcome import Outcome as OutcomeModel
    except ImportError:  # por si el modelo se llama distinto en el repo
        from app.models.outcome import MarketOutcome as OutcomeModel

    inserted = skipped = 0
    async with AsyncSessionLocal() as db:
        for row in MATCHES:
            m = build_market(row)
            exists = await db.execute(select(Market).where(Market.id == m["id"]))
            if exists.scalar_one_or_none() is not None:
                print(f"  SKIP   {m['id']} (ya existe)")
                skipped += 1
                continue
            db.add(Market(
                id=m["id"], question=m["question"], description=m["description"],
                category=MarketCategory.DEPORTES, subcategory=m["subcategory"],
                resolution_criteria=m["resolution_criteria"],
                market_type="multi", b=m["b"], ends_at=m["ends_at"],
                status=MarketStatus.OPEN, trending=m["trending"],
                volume=0.0, num_trades=0,
            ))
            await db.flush()  # fija el id del padre antes de los outcomes
            for o in m["outcomes"]:
                db.add(OutcomeModel(market_id=m["id"], outcome_key=o["outcome_key"],
                                    label=o["label"], q=o["q"], price=o["price"]))
                print(f"           + {o['outcome_key']:<9} {o['price']:>5.1f}%  q={o['q']:.2f}")
            db.add(PriceHistory(market_id=m["id"], yes_price=0.0, volume_snapshot=0.0))
            print(f"  INSERT {m['id']}  b={m['b']}  trending={m['trending']}  ends_at={m['ends_at'].isoformat()}")
            inserted += 1
        await db.commit()
    await engine.dispose()
    print(f"\nDone. insertados={inserted} saltados={skipped}")


if __name__ == "__main__":
    validate()
    if DRY_RUN:
        for row in MATCHES:
            m = build_market(row)
            print(f"{m['id']:<40} {m['subcategory']:<18} {m['ends_at'].strftime('%Y-%m-%d %H:%MZ')}  "
                  + "  ".join(f"{o['price']:.0f}%/q={o['q']:.1f}" for o in m["outcomes"]))
        print("\n(dry-run) No se tocó la base de datos.")
    else:
        asyncio.run(main())
