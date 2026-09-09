"""
seed-markets-2026-09-02-binarios.py
====================================
Siembra 70 mercados BINARIOS (sí/no) en Veredikt con el motor LMSR binario que ya existe.

Bloques:
  A) Champions J1 · goleadores 2025/26: ¿marca en su primer partido?      (9)
  B) Champions J1 · titularidad en el once inicial                         (10)
  C) NFL Week 1 · QB 2+ pases de TD                                        (10)
  D) NFL Week 1 · RB al menos 1 TD                                         (10)
  E) NFL Week 1 · WR al menos 1 TD                                         (10)
  F) NFL Week 1 · 15+ puntos de fantasy (scoring estándar ESPN)            (12)
  G) Política y sociedad MX                                                (9)

Uso:
  python seed-markets-2026-09-02-binarios.py --dry-run
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-09-02-binarios.py'

El precio NO se hardcodea: initial_yes_price -> lmsr.init_q_for_price -> lmsr.yes_price_pct.
Idempotente por SELECT previo. Una fila obligatoria en price_history por mercado (outcome_key NULL).
"""
import asyncio
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DRY_RUN = "--dry-run" in sys.argv


def dt(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


# Cierre de mercados de titularidad: 90 minutos ANTES del kickoff. Las alineaciones oficiales
# salen ~60-75 min antes y dejarlo abierto hasta el kickoff regala arbitraje.
def lineup_close(kickoff):
    return kickoff - timedelta(minutes=90)


# ── Kickoffs verificados (UTC) ────────────────────────────────────────────
UCL = {
    "rma_int": dt(2026, 9, 8, 19, 0),   # Real Madrid vs Inter
    "fcp_mci": dt(2026, 9, 8, 19, 0),   # Porto vs Man City
    "lil_rbb": dt(2026, 9, 8, 19, 0),   # Lille vs Betis
    "bar_fey": dt(2026, 9, 9, 16, 45),  # Barcelona vs Feyenoord
    "lfc_atm": dt(2026, 9, 9, 19, 0),   # Liverpool vs Atlético
    "psg_slo": dt(2026, 9, 9, 19, 0),   # PSG vs Slovan
    "scp_gal": dt(2026, 9, 9, 19, 0),   # Sporting vs Galatasaray
    "bmu_bog": dt(2026, 9, 10, 19, 0),  # Bayern vs Bodø/Glimt
    "mun_sab": dt(2026, 9, 10, 19, 0),  # Man United vs Sabah
}
NFL = {
    "sea_ne": dt(2026, 9, 10, 0, 20),    # Seahawks vs Patriots (miércoles 9 sep noche ET)
    "lar_sf": dt(2026, 9, 11, 0, 35),    # Rams vs 49ers (Melbourne)
    "early": dt(2026, 9, 13, 17, 0),     # ventana 1:00 pm ET del domingo 13
    "late": dt(2026, 9, 13, 20, 25),     # ventana 4:25 pm ET
    "nyg_dal": dt(2026, 9, 14, 0, 20),   # SNF Giants vs Cowboys
    "kc_den": dt(2026, 9, 15, 0, 15),    # MNF Chiefs vs Broncos
}
# Fin de plazos de política: medianoche de CDMX (UTC-6) del último día incluido.
END_SEP30 = dt(2026, 10, 1, 5, 59, 59)     # "antes del 1 de octubre"
END_OCT31 = dt(2026, 11, 1, 5, 59, 59)     # "antes del 1 de noviembre"
END_DEC31 = dt(2027, 1, 1, 5, 59, 59)      # "antes de terminar 2026"

RES_GOL = ("Resuelve SÍ si el jugador tiene al menos un gol acreditado oficialmente por la UEFA (uefa.com) "
           "en el partido indicado de la Jornada 1 de la fase de liga 2026-27. Autogoles a favor del rival no "
           "cuentan. Si el jugador no participa ni un minuto (inactivo, lesionado o fuera de convocatoria) el "
           "mercado se cancela vía admin. Si participa aunque sea una jugada y no marca, resuelve NO.")
RES_TIT = ("Resuelve SÍ solo si el jugador aparece en el once inicial oficial publicado por la UEFA (uefa.com) "
           "para el partido indicado. Entrar como suplente o no ser convocado resuelve NO. Si el partido se "
           "pospone fuera de la Jornada 1, el mercado se cancela vía admin. El mercado cierra 90 minutos antes "
           "del kickoff, antes de la publicación de alineaciones.")
RES_QB = ("Resuelve SÍ si el quarterback lanza 2 o más pases de touchdown en el partido de la Semana 1 según la "
          "estadística oficial de NFL.com (incluye tiempo extra). Los touchdowns por carrera NO cuentan. Si el "
          "jugador es declarado inactivo y no juega, el mercado se cancela vía admin. Si juega al menos una "
          "jugada y no llega a 2, resuelve NO. Si el partido se reprograma fuera de la Semana 1, se cancela.")
RES_TD = ("Resuelve SÍ si el jugador anota al menos un touchdown por carrera o recepción en el partido de la "
          "Semana 1 según la estadística oficial de NFL.com (incluye tiempo extra). No cuentan pases de TD ni "
          "devoluciones. Si es declarado inactivo y no juega, el mercado se cancela vía admin. Si juega al "
          "menos una jugada y no anota, resuelve NO. Si el partido se reprograma fuera de la Semana 1, se cancela.")
RES_FAN = ("Resuelve SÍ si el jugador acumula 15.0 o más puntos de fantasy en la Semana 1 con el scoring "
           "estándar de ESPN (sin PPR): 0.04 pts por yarda de pase, 4 pts por TD de pase, -2 por intercepción, "
           "0.1 pts por yarda de carrera o recepción, 6 pts por TD de carrera o recepción, -2 por fumble perdido, "
           "2 pts por conversión de 2 puntos. Fuente: cifra final de puntos que muestra ESPN Fantasy (o el "
           "cálculo con la estadística oficial de NFL.com si hay discrepancia). Si el jugador es inactivo y no "
           "juega, se cancela vía admin. Si juega y no llega a 15.0, resuelve NO.")


def ucl_gol(pid, jugador, club, rival, key, prior, trending=False):
    return {
        "id": pid,
        "question": f"¿{jugador} marcará al menos un gol en su primer partido de la Champions 2026/27?",
        "description": f"{jugador} ({club}) debuta en la fase de liga 2026-27 ante {rival}. Fue uno de los máximos "
                       f"goleadores de la Champions 2025/26. Mercado de gol en la Jornada 1.",
        "subcategory": "Champions League", "resolution_criteria": RES_GOL,
        "ends_at": UCL[key], "b": 150.0 if trending else 100.0,
        "initial_yes_price": float(prior), "trending": trending,
    }


def ucl_tit(pid, jugador, club, rival, key, prior):
    return {
        "id": pid,
        "question": f"¿{jugador} será titular con {club} ante {rival} en la Jornada 1 de la Champions?",
        "description": f"Mercado de titularidad. Resuelve SÍ solo si {jugador} aparece en el once inicial oficial "
                       f"de {club} contra {rival}. Cierra 90 minutos antes del kickoff.",
        "subcategory": "Champions League", "resolution_criteria": RES_TIT,
        "ends_at": lineup_close(UCL[key]), "b": 100.0,
        "initial_yes_price": float(prior), "trending": False,
    }


def nfl_qb(pid, jugador, equipo, rival, key, prior, trending=False):
    return {
        "id": pid,
        "question": f"¿{jugador} lanzará 2 o más pases de touchdown en la Semana 1?",
        "description": f"{jugador} ({equipo}) abre la temporada NFL 2026 contra {rival}. Solo cuentan pases de "
                       f"touchdown según NFL.com; los TD por carrera no cuentan.",
        "subcategory": "NFL", "resolution_criteria": RES_QB,
        "ends_at": NFL[key], "b": 150.0 if trending else 100.0,
        "initial_yes_price": float(prior), "trending": trending,
    }


def nfl_td(pid, jugador, pos, equipo, rival, key, prior, trending=False):
    return {
        "id": pid,
        "question": f"¿{jugador} anotará al menos 1 touchdown en la Semana 1?",
        "description": f"{jugador}, {pos} de {equipo}, abre la temporada NFL 2026 contra {rival}. Cuenta cualquier "
                       f"touchdown por carrera o recepción según NFL.com.",
        "subcategory": "NFL", "resolution_criteria": RES_TD,
        "ends_at": NFL[key], "b": 150.0 if trending else 100.0,
        "initial_yes_price": float(prior), "trending": trending,
    }


def nfl_fan(pid, jugador, pos, equipo, rival, key, prior):
    return {
        "id": pid,
        "question": f"¿{jugador} conseguirá 15 o más puntos de Fantasy NFL (scoring estándar) en la Semana 1?",
        "description": f"{jugador}, {pos} de {equipo}, contra {rival}. Umbral de 15.0 puntos con el scoring "
                       f"estándar de ESPN (sin PPR): 6 por TD de carrera o recepción, 4 por TD de pase, "
                       f"0.1 por yarda terrestre o aérea recibida, 0.04 por yarda de pase.",
        "subcategory": "NFL", "resolution_criteria": RES_FAN,
        "ends_at": NFL[key], "b": 100.0,
        "initial_yes_price": float(prior), "trending": False,
    }


MARKETS = [
    # ── A) Champions J1 · goleadores ── priors EST (no hay cuotas publicadas aún)
    ucl_gol("ucl-mbappe-gol-j1-2627", "Kylian Mbappé", "Real Madrid", "Inter", "rma_int", 50, True),
    ucl_gol("ucl-kane-gol-j1-2627", "Harry Kane", "Bayern Múnich", "Bodø/Glimt", "bmu_bog", 62),
    ucl_gol("ucl-kvaratskhelia-gol-j1-2627", "Khvicha Kvaratskhelia", "Paris Saint-Germain", "Slovan Bratislava", "psg_slo", 42),
    ucl_gol("ucl-julianalvarez-gol-j1-2627", "Julián Álvarez", "Atlético de Madrid", "Liverpool", "lfc_atm", 33),
    # Anthony Gordon: NO ABRIR (Newcastle no participa en la UCL 2026/27)
    ucl_gol("ucl-haaland-gol-j1-2627", "Erling Haaland", "Manchester City", "Porto", "fcp_mci", 52, True),
    ucl_gol("ucl-dembele-gol-j1-2627", "Ousmane Dembélé", "Paris Saint-Germain", "Slovan Bratislava", "psg_slo", 45),
    ucl_gol("ucl-luisdiaz-gol-j1-2627", "Luis Díaz", "Bayern Múnich", "Bodø/Glimt", "bmu_bog", 45),
    ucl_gol("ucl-osimhen-gol-j1-2627", "Victor Osimhen", "Galatasaray", "Sporting CP", "scp_gal", 40),
    ucl_gol("ucl-ferminlopez-gol-j1-2627", "Fermín López", "Barcelona", "Feyenoord", "bar_fey", 38),

    # ── B) Champions J1 · titularidad ── priors EST (revisar team news antes de correr)
    ucl_tit("ucl-dimarco-titular-j1-2627", "Federico Dimarco", "Inter", "Real Madrid", "rma_int", 72),
    ucl_tit("ucl-fidalgo-titular-j1-2627", "Álvaro Fidalgo", "Real Betis", "Lille", "lil_rbb", 55),
    ucl_tit("ucl-cherki-titular-j1-2627", "Rayan Cherki", "Manchester City", "Porto", "fcp_mci", 45),
    ucl_tit("ucl-yoro-titular-j1-2627", "Leny Yoro", "Manchester United", "Sabah", "mun_sab", 60),
    ucl_tit("ucl-rodri-titular-j1-2627", "Rodri", "Barcelona", "Feyenoord", "bar_fey", 55),
    ucl_tit("ucl-diomande-titular-j1-2627", "Yan Diomande", "Real Madrid", "Inter", "rma_int", 45),
    ucl_tit("ucl-lenormand-titular-j1-2627", "Robin Le Normand", "Atlético de Madrid", "Liverpool", "lfc_atm", 65),
    ucl_tit("ucl-wirtz-titular-j1-2627", "Florian Wirtz", "Liverpool", "Atlético de Madrid", "lfc_atm", 80),
    ucl_tit("ucl-fabianruiz-titular-j1-2627", "Fabián Ruiz", "Paris Saint-Germain", "Slovan Bratislava", "psg_slo", 60),
    ucl_tit("ucl-gnabry-titular-j1-2627", "Serge Gnabry", "Bayern Múnich", "Bodø/Glimt", "bmu_bog", 50),

    # ── C) NFL Week 1 · QB 2+ pases de TD ── priors EST
    nfl_qb("nfl-allen-2tdpass-w1-2026", "Josh Allen", "Bills", "Texans", "early", 60, True),
    nfl_qb("nfl-burrow-2tdpass-w1-2026", "Joe Burrow", "Bengals", "Buccaneers", "early", 60),
    nfl_qb("nfl-lamar-2tdpass-w1-2026", "Lamar Jackson", "Ravens", "Colts", "early", 58),
    nfl_qb("nfl-hurts-2tdpass-w1-2026", "Jalen Hurts", "Eagles", "Commanders", "late", 48),
    nfl_qb("nfl-daniels-2tdpass-w1-2026", "Jayden Daniels", "Commanders", "Eagles", "late", 50),
    nfl_qb("nfl-goff-2tdpass-w1-2026", "Jared Goff", "Lions", "Saints", "early", 60),
    nfl_qb("nfl-herbert-2tdpass-w1-2026", "Justin Herbert", "Chargers", "Cardinals", "late", 55),
    nfl_qb("nfl-maye-2tdpass-w1-2026", "Drake Maye", "Patriots", "Seahawks", "sea_ne", 48),
    nfl_qb("nfl-stafford-2tdpass-w1-2026", "Matthew Stafford", "Rams", "49ers", "lar_sf", 55),
    nfl_qb("nfl-mahomes-2tdpass-w1-2026", "Patrick Mahomes", "Chiefs", "Broncos", "kc_den", 58, True),

    # ── D) NFL Week 1 · RB al menos 1 TD ── priors EST
    nfl_td("nfl-barkley-td-w1-2026", "Saquon Barkley", "corredor", "los Eagles", "Commanders", "late", 62, True),
    nfl_td("nfl-bijan-td-w1-2026", "Bijan Robinson", "corredor", "los Falcons", "Steelers", "early", 55),
    nfl_td("nfl-gibbs-td-w1-2026", "Jahmyr Gibbs", "corredor", "los Lions", "Saints", "early", 62),
    nfl_td("nfl-henry-td-w1-2026", "Derrick Henry", "corredor", "los Ravens", "Colts", "early", 62),
    nfl_td("nfl-jtaylor-td-w1-2026", "Jonathan Taylor", "corredor", "los Colts", "Ravens", "early", 55),
    nfl_td("nfl-mccaffrey-td-w1-2026", "Christian McCaffrey", "corredor", "los 49ers", "Rams", "lar_sf", 58, True),
    nfl_td("nfl-jcook-td-w1-2026", "James Cook", "corredor", "los Bills", "Texans", "early", 55),
    nfl_td("nfl-jacobs-td-w1-2026", "Josh Jacobs", "corredor", "los Packers", "Vikings", "late", 52),
    nfl_td("nfl-achane-td-w1-2026", "De'Von Achane", "corredor", "los Dolphins", "Raiders", "late", 52),
    nfl_td("nfl-breecehall-td-w1-2026", "Breece Hall", "corredor", "los Jets", "Titans", "early", 40),

    # ── E) NFL Week 1 · WR al menos 1 TD ── priors EST
    nfl_td("nfl-chase-td-w1-2026", "Ja'Marr Chase", "receptor", "los Bengals", "Buccaneers", "early", 55, True),
    nfl_td("nfl-jefferson-td-w1-2026", "Justin Jefferson", "receptor", "los Vikings", "Packers", "late", 50),
    nfl_td("nfl-lamb-td-w1-2026", "CeeDee Lamb", "receptor", "los Cowboys", "Giants", "nyg_dal", 48),
    nfl_td("nfl-stbrown-td-w1-2026", "Amon-Ra St. Brown", "receptor", "los Lions", "Saints", "early", 55),
    nfl_td("nfl-nacua-td-w1-2026", "Puka Nacua", "receptor", "los Rams", "49ers", "lar_sf", 48),
    nfl_td("nfl-collins-td-w1-2026", "Nico Collins", "receptor", "los Texans", "Bills", "early", 48),
    nfl_td("nfl-nabers-td-w1-2026", "Malik Nabers", "receptor", "los Giants", "Cowboys", "nyg_dal", 45),
    nfl_td("nfl-bthomas-td-w1-2026", "Brian Thomas Jr.", "receptor", "los Jaguars", "Browns", "early", 45),
    nfl_td("nfl-mclaurin-td-w1-2026", "Terry McLaurin", "receptor", "los Commanders", "Eagles", "late", 42),
    nfl_td("nfl-jsn-td-w1-2026", "Jaxon Smith-Njigba", "receptor", "los Seahawks", "Patriots", "sea_ne", 48),

    # ── F) NFL Week 1 · 15+ puntos fantasy estándar ── priors EST
    nfl_fan("nfl-jefferson-fantasy15-w1-2026", "Justin Jefferson", "receptor", "los Vikings", "Packers", "late", 35),
    nfl_fan("nfl-mccaffrey-fantasy15-w1-2026", "Christian McCaffrey", "corredor", "los 49ers", "Rams", "lar_sf", 55),
    nfl_fan("nfl-jcook-fantasy15-w1-2026", "James Cook", "corredor", "los Bills", "Texans", "early", 45),
    nfl_fan("nfl-nacua-fantasy15-w1-2026", "Puka Nacua", "receptor", "los Rams", "49ers", "lar_sf", 35),
    nfl_fan("nfl-bijan-fantasy15-w1-2026", "Bijan Robinson", "corredor", "los Falcons", "Steelers", "early", 50),
    nfl_fan("nfl-lamb-fantasy15-w1-2026", "CeeDee Lamb", "receptor", "los Cowboys", "Giants", "nyg_dal", 33),
    nfl_fan("nfl-stafford-fantasy15-w1-2026", "Matthew Stafford", "quarterback", "los Rams", "49ers", "lar_sf", 58),
    nfl_fan("nfl-lamar-fantasy15-w1-2026", "Lamar Jackson", "quarterback", "los Ravens", "Colts", "early", 75),
    nfl_fan("nfl-allen-fantasy15-w1-2026", "Josh Allen", "quarterback", "los Bills", "Texans", "early", 78),
    nfl_fan("nfl-london-fantasy15-w1-2026", "Drake London", "receptor", "los Falcons", "Steelers", "early", 33),
    nfl_fan("nfl-laporta-fantasy15-w1-2026", "Sam LaPorta", "ala cerrada", "los Lions", "Saints", "early", 15),
    nfl_fan("nfl-waddle-fantasy15-w1-2026", "Jaylen Waddle", "receptor", "los Dolphins", "Raiders", "late", 25),

    # ── G) Política y sociedad MX ── priors EST con contexto de prensa (ver notas en la respuesta)
    {
        "id": "sheinbaum-cancion-mananera-sep26",
        "question": "¿Claudia Sheinbaum pondrá una canción durante una mañanera antes del 1 de octubre de 2026?",
        "description": "La presidenta ya ha reproducido canciones en la mañanera varias veces en 2026 (José Alfredo "
                       "Jiménez en enero, Grupo Firme el 24 de junio). Resuelve sobre las conferencias del 2 al 30 "
                       "de septiembre.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si entre el 2 y el 30 de septiembre de 2026 (hora CDMX) se reproduce una "
                               "canción completa o un fragmento, grabada o en vivo, dentro de la conferencia matutina "
                               "de la Presidencia, a petición de la presidenta o de su equipo, y esto consta en el video "
                               "oficial de la mañanera (canal de Presidencia) o en al menos dos medios nacionales. "
                               "No cuenta música de fondo de un video institucional ni himnos en ceremonias oficiales.",
        "ends_at": END_SEP30, "b": 100.0, "initial_yes_price": 85.0, "trending": False,
    },
    {
        "id": "norona-rompe-visa-sep26",
        "question": "¿Gerardo Fernández Noroña romperá públicamente su visa de Estados Unidos antes del 1 de octubre de 2026?",
        "description": "El 19 de agosto, ante el reto de Lilly Téllez en la Comisión Permanente, Noroña dijo que rompería "
                       "su visa pero que no podía por su lesión en la mano y que lo haría al recuperarse. Después declaró "
                       "que sí volverá a Estados Unidos.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si antes del 1 de octubre de 2026 (hora CDMX) Fernández Noroña rompe, corta o "
                               "destruye físicamente su visa estadounidense en un acto público o en video difundido por él "
                               "mismo, y el hecho lo reportan al menos dos medios nacionales. Anunciar que la romperá, "
                               "mostrarla o decir que la devolvió no cuenta.",
        "ends_at": END_SEP30, "b": 100.0, "initial_yes_price": 12.0, "trending": False,
    },
    {
        "id": "paso-cortes-proceso-oficial-oct26",
        "question": "¿Se iniciará oficialmente el proceso para cambiar el nombre del Paso de Cortés antes del 1 de noviembre de 2026?",
        "description": "Sheinbaum propuso el 9 de agosto renombrarlo Paso de los Pueblos Indígenas. Los congresos de Puebla "
                       "y Estado de México abrieron una mesa de trabajo el 13 de agosto, pero aún no hay iniciativa formal.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si antes del 1 de noviembre de 2026 (hora CDMX) ocurre al menos uno: (a) se "
                               "presenta y registra formalmente en la Gaceta o el orden del día una iniciativa de ley, "
                               "decreto o punto de acuerdo para renombrar el Paso de Cortés en el Congreso de Puebla, del "
                               "Estado de México o de la Unión; (b) el Ejecutivo federal o un gobierno estatal publica un "
                               "decreto o acuerdo oficial con el cambio de nombre; (c) se convoca oficialmente una consulta "
                               "pública sobre el cambio. Declaraciones, mesas de trabajo o anuncios sin documento formal no "
                               "cuentan.",
        "ends_at": END_OCT31, "b": 100.0, "initial_yes_price": 60.0, "trending": False,
    },
    {
        "id": "pelea-legisladores-federales-sep26",
        "question": "¿Habrá otra pelea física entre legisladores federales mexicanos antes del 1 de octubre de 2026?",
        "description": "En 2026 ya hubo altercados con contacto físico en el Congreso federal el 28 de mayo (Escobar vs "
                       "Gutiérrez Mancilla) y el 12 de agosto (Gutiérrez Mancilla vs Arturo Ávila). El periodo ordinario "
                       "arrancó el 1 de septiembre.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si entre el 2 y el 30 de septiembre de 2026 (hora CDMX) al menos dos "
                               "diputados federales o senadores en funciones tienen contacto físico agresivo (golpes, "
                               "empujones, jalones, sujeciones) dentro del Congreso de la Unión, sus comisiones o la "
                               "Comisión Permanente, documentado en video y reportado como pelea, zafarrancho, empujones "
                               "o agresión por al menos dos medios nacionales. Insultos o amagos sin contacto no cuentan. "
                               "Congresos locales no cuentan.",
        "ends_at": END_SEP30, "b": 100.0, "initial_yes_price": 45.0, "trending": False,
    },
    {
        "id": "regulacion-scroll-infinito-2026",
        "question": "¿El Gobierno de México presentará una propuesta formal para regular el scroll infinito antes del 31 de diciembre de 2026?",
        "description": "Sheinbaum abrió en julio y agosto un debate nacional sobre redes sociales y menores y ha señalado el "
                       "scroll infinito como mecanismo adictivo. Dijo que primero irían las reglas para escuelas y después "
                       "se discutiría si regular las plataformas.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora CDMX) el Ejecutivo federal "
                               "presenta ante el Congreso de la Unión una iniciativa de ley, o publica un proyecto de "
                               "decreto, norma o lineamientos oficiales, cuyo texto mencione explícitamente limitar, "
                               "restringir, regular o desactivar el scroll o desplazamiento infinito (en cualquier "
                               "redacción equivalente) en plataformas digitales. Foros, campañas o declaraciones no cuentan. "
                               "Iniciativas de legisladores individuales sin respaldo del Ejecutivo no cuentan.",
        "ends_at": END_DEC31, "b": 100.0, "initial_yes_price": 45.0, "trending": False,
    },
    {
        "id": "cdmx-interviene-batalla-aura-sep26",
        "question": "¿Alguna autoridad de CDMX intervendrá, cancelará o dispersará una batalla de aura antes del 1 de octubre de 2026?",
        "description": "Las batallas de farmear aura llenaron CU, el Monumento a la Revolución y Bellas Artes en agosto. "
                       "Clara Brugada dijo que son bienvenidas mientras sean pacíficas; en Ignacio de la Llave, Veracruz, "
                       "un ayuntamiento sí frenó una por falta de permiso.",
        "category": "MEXICO", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si entre el 2 y el 30 de septiembre de 2026 (hora CDMX) una autoridad de la "
                               "Ciudad de México (Gobierno capitalino, SSC, alcaldía, o autoridad de un espacio público "
                               "como UNAM o INBAL dentro de CDMX) suspende, cancela, niega el permiso, desaloja o dispersa "
                               "una batalla de aura convocada públicamente, y el hecho lo reportan al menos dos medios "
                               "nacionales. Recomendaciones o presencia policial sin interrumpir el evento no cuentan.",
        "ends_at": END_SEP30, "b": 100.0, "initial_yes_price": 30.0, "trending": False,
    },
    {
        "id": "gobierno-reconoce-batallas-aura-2026",
        "question": "¿El Gobierno de México reconocerá oficialmente las batallas de aura como disciplina, actividad cultural o competencia organizada antes del 31 de diciembre de 2026?",
        "description": "Hasta ahora solo hay declaraciones de tolerancia (Brugada en CDMX). No existe ningún programa, "
                       "convocatoria ni registro oficial federal sobre las batallas de aura.",
        "category": "MEXICO", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora CDMX) una dependencia del "
                               "Gobierno federal (Presidencia, Secretaría de Cultura, CONADE, SEP, IMJUVE u otra) emite un "
                               "documento oficial (decreto, acuerdo, convocatoria, programa o comunicado oficial) que "
                               "organice, registre o reconozca las batallas de aura como disciplina, actividad cultural o "
                               "competencia oficial. Declaraciones verbales en conferencia, actos de gobiernos estatales o "
                               "municipales y eventos privados no cuentan.",
        "ends_at": END_DEC31, "b": 100.0, "initial_yes_price": 8.0, "trending": False,
    },
    {
        "id": "andy-recupera-visa-eu-2026",
        "question": "¿Estados Unidos le devolverá la visa a Andy López Beltrán antes del 31 de diciembre de 2026?",
        "description": "Andrés Manuel López Beltrán anunció el 14 de agosto que Estados Unidos le revocó la visa y envió "
                       "una carta a Trump. Dijo que no le interesa visitar Estados Unidos en estos tiempos.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora CDMX) el Departamento de "
                               "Estado o la Embajada de Estados Unidos confirman, o el propio López Beltrán confirma "
                               "públicamente con evidencia, que su visa fue restituida o que se le emitió una nueva visa "
                               "estadounidense. Reportes anónimos sin confirmación no cuentan.",
        "ends_at": END_DEC31, "b": 100.0, "initial_yes_price": 4.0, "trending": False,
    },
    {
        "id": "andy-solicita-visa-eu-2026",
        "question": "¿Andy López Beltrán intentará públicamente recuperar o solicitar nuevamente una visa de Estados Unidos antes de terminar 2026?",
        "description": "Tras la revocación, López Beltrán calificó la decisión como política y afirmó que no le causa "
                       "ningún problema no visitar Estados Unidos.",
        "category": "POLITICA_MX", "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora CDMX) López Beltrán declara "
                               "públicamente (redes, entrevista o comunicado) que solicitó una nueva visa, que pidió la "
                               "reconsideración o restitución de la revocada, o que presentó un recurso formal ante "
                               "autoridades estadounidenses; o si un medio nacional documenta la solicitud con evidencia y "
                               "él no lo desmiente en 72 horas. La carta a Trump del 14 de agosto no cuenta por ser previa "
                               "al mercado.",
        "ends_at": END_DEC31, "b": 100.0, "initial_yes_price": 8.0, "trending": False,
    },
]


# ── Fallback local de la fórmula binaria SOLO para --dry-run (en prod se usa app.core.lmsr) ──
def _init_q_for_price(p, b):
    return b * math.log(p / (1 - p)), 0.0


def _yes_price_pct(q_yes, q_no, b):
    return round(100 / (1 + math.exp((q_no - q_yes) / b)), 2)


def validate():
    ids = [m["id"] for m in MARKETS]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"ids duplicados: {dupes}"
    now = datetime.now(timezone.utc)
    vivos = []
    for m in MARKETS:
        assert 1.0 <= m["initial_yes_price"] <= 99.0, f"{m['id']}: prior fuera de rango"
        assert 50.0 <= m["b"] <= 300.0, f"{m['id']}: b fuera de rango"
        assert len(m["question"]) <= 500 and len(m["id"]) <= 100
        if m["ends_at"] <= now:
            print(f"  OMITIDO {m['id']}: ya cerró ({m['ends_at'].isoformat()})")
            continue
        vivos.append(m)
    MARKETS[:] = vivos
    print(f"OK: {len(MARKETS)} mercados binarios por sembrar, ids únicos, priors válidos.")


async def main():
    from sqlalchemy import select
    from app.database import AsyncSessionLocal, engine
    from app.models.market import Market, MarketCategory, MarketStatus
    from app.models.price_history import PriceHistory
    from app.core import lmsr

    inserted = skipped = 0
    async with AsyncSessionLocal() as db:
        for m in MARKETS:
            exists = await db.execute(select(Market).where(Market.id == m["id"]))
            if exists.scalar_one_or_none() is not None:
                print(f"  SKIP   {m['id']} (ya existe)")
                skipped += 1
                continue

            # Bloques A-F no traen "category": son DEPORTES. El bloque G trae el NOMBRE del enum.
            category = MarketCategory[m.get("category", "DEPORTES")]
            b = m["b"]
            q_yes, q_no = lmsr.init_q_for_price(m["initial_yes_price"] / 100.0, b)
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, b)

            market = Market(
                id=m["id"],
                question=m["question"],
                description=m["description"],
                category=category,
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
            db.add(PriceHistory(market_id=market.id, yes_price=yes_price_val, volume_snapshot=0.0))
            print(f"  INSERT {m['id']:<42} yes={yes_price_val:>6.2f}%  b={b}  cat={category.name}  "
                  f"ends_at={m['ends_at'].isoformat()}")
            inserted += 1
        await db.commit()
    await engine.dispose()
    print(f"\nDone. insertados={inserted} saltados={skipped}")


if __name__ == "__main__":
    validate()
    if DRY_RUN:
        for m in MARKETS:
            q_yes, q_no = _init_q_for_price(m["initial_yes_price"] / 100.0, m["b"])
            print(f"{m['id']:<42} {m.get('category', 'DEPORTES'):<12} {str(m.get('subcategory')):<17} "
                  f"{m['ends_at'].strftime('%Y-%m-%d %H:%M:%SZ')}  "
                  f"yes={_yes_price_pct(q_yes, q_no, m['b']):>6.2f}%  b={m['b']:.0f}  q_yes={q_yes:.2f}")
        print("\n(dry-run) No se tocó la base de datos.")
    else:
        asyncio.run(main())
