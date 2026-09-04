"""Normas / Contexto / fuente de los accesorios de fútbol: titulares, goles, Leagues Cup, Liga MX social (28 activos al 2026-09-04)."""
from market_content._common import BINARIO_PAGO, entry, fecha_mx

UEFA_URL = "https://www.uefa.com/uefachampionsleague/fixtures-results/"
LEAGUES_CUP_URL = "https://www.leaguescup.com"
LALIGA_URL = "https://www.laliga.com"
PL_URL = "https://www.premierleague.com/results"


def titular_rules(jugador: str, club: str, rival: str, partido_txt: str, fuente: str, cierre_iso: str, ventana: str) -> str:
    return f"""
Resuelve SÍ únicamente si {jugador} aparece en el once inicial oficial de {club} para {partido_txt}, tal como lo publica {fuente} antes del silbatazo. Entrar de cambio, quedarse en la banca o no ser convocado resuelve NO. Lo que cuenta es la alineación oficial publicada, no la que salte a la cancha tras una lesión en el calentamiento: si el jugador está en el once oficial y se lesiona antes de iniciar, sigue resolviendo SÍ.

El mercado cierra antes de que se publiquen las alineaciones: {fecha_mx(cierre_iso)}. Ninguna predicción se acepta después de esa hora aunque la alineación todavía no se conozca.

Si el partido se aplaza pero se juega dentro de {ventana}, el mercado se mantiene y el cierre se recorre. Si se reprograma fuera de esa ventana o se cancela, el mercado se cancela y las posiciones se reembolsan.

{BINARIO_PAGO} Se resuelve en cuanto la alineación oficial es pública, normalmente una hora antes del partido.
"""


def gol_rules(jugador: str, club: str, rival: str, kickoff_iso: str) -> str:
    return f"""
Resuelve SÍ si {jugador} tiene al menos un gol acreditado oficialmente por la UEFA (uefa.com) en el partido {club} vs. {rival} de la Jornada 1 de la fase de liga de la Champions League 2026-27. Cuenta cualquier gol de jugada o de penal en los 90 minutos más el tiempo añadido. Los autogoles no cuentan, ni los goles anulados por VAR. Si la UEFA reasigna la autoría de un gol después del partido, manda la acreditación final publicada en uefa.com.

Si {jugador} no participa ni un minuto (no convocado, lesionado o suplente sin ingresar), el mercado se cancela y se reembolsa. Si participa aunque sea una jugada y no anota, resuelve NO.

Si el partido se aplaza dentro de la Jornada 1 (8 al 10 de septiembre), el mercado se mantiene y el cierre se recorre; si se reprograma fuera de esa ventana o se cancela, el mercado se cancela.

El mercado cierra al silbatazo inicial: {fecha_mx(kickoff_iso)}. {BINARIO_PAGO}
"""


def social_mx_rules(condicion: str, medios: str, minimo: int, periodo: str, cierre_iso: str) -> str:
    return f"""
Cómo se resuelve: no existe una página oficial que registre este tipo de hechos, así que el mercado se resuelve por cobertura de prensa. Resuelve SÍ si {condicion} y el hecho es reportado por al menos {minimo} de estos medios: {medios}. La nota debe describir el hecho con fecha y partido identificables; publicaciones únicamente en redes sociales de aficionados no bastan.

Periodo válido: {periodo}. Un hecho ocurrido fuera de ese periodo, en Liga de Expansión, Liga MX Femenil o en partidos amistosos no cuenta.

El equipo de VEREDIKT publica en los comentarios del mercado el enlace a las notas usadas para resolver. En caso de duda razonable sobre si el hecho cumple la definición, el mercado se resuelve NO.

Cierra el {fecha_mx(cierre_iso, con_hora=False)}, al terminar el Apertura 2026 (incluida la Liguilla). {BINARIO_PAGO} Si el hecho ocurre antes, el mercado puede resolverse SÍ de inmediato.
"""


UCL_TITULARES = [
    # id, jugador, club, rival, cierre_iso, contexto
    ("ucl-cherki-titular-j1-2627", "Rayan Cherki", "Manchester City", "FC Porto", "2026-09-08T17:30:00+00:00",
     "Rayan Cherki, mediapunta francés formado en el Lyon, llegó al Manchester City en 2025 como una de las grandes apuestas creativas de Guardiola. En un plantel con tanta competencia en la zona ofensiva, la titularidad en las noches europeas no está garantizada: Guardiola rota mucho y el Dragão es una salida donde suele privilegiar el control del mediocampo."),
    ("ucl-dimarco-titular-j1-2627", "Federico Dimarco", "Inter", "Real Madrid", "2026-09-08T17:30:00+00:00",
     "Federico Dimarco es el carrilero izquierdo titular del Inter desde hace varias temporadas y uno de los mejores en su posición en Europa. La duda en un partido tan exigente como el Bernabéu es la gestión de cargas: el Inter juega Serie A el fin de semana anterior y la rotación en la banda izquierda es habitual cuando hay tres partidos por semana."),
    ("ucl-diomande-titular-j1-2627", "Yan Diomande", "Real Madrid", "Inter", "2026-09-08T17:30:00+00:00",
     "Yan Diomande, extremo marfileño fichado por el Real Madrid tras destacar en LaLiga, compite por un lugar en un ataque con Mbappé, Vinícius y Rodrygo. Su titularidad ante el Inter depende del esquema que elija el técnico para el partido más difícil de la jornada inaugural; contra rivales grandes el Madrid suele apostar por nombres consolidados."),
    ("ucl-fidalgo-titular-j1-2627", "Álvaro Fidalgo", "Real Betis", "Lille", "2026-09-08T17:30:00+00:00",
     "Álvaro Fidalgo, mediocampista español que brilló en el América de la Liga MX (varios títulos con las Águilas), volvió a Europa para jugar con el Real Betis. Para la afición mexicana es un nombre conocido: su titularidad en el debut europeo del Betis ante el Lille marcaría cuánto peso tiene ya en el esquema de Pellegrini."),
    ("ucl-rodri-titular-j1-2627", "Rodri", "Barcelona", "Feyenoord", "2026-09-09T15:15:00+00:00",
     "Rodri, Balón de Oro 2024 y durante años el mediocentro del Manchester City, cambió de club para vestirse de azulgrana. Tras la lesión grave de rodilla que lo tuvo fuera casi toda la temporada 2024-25, la pregunta es si el Barcelona lo alinea de inicio en su primer partido de Champions con el club o gestiona sus minutos ante un rival como Feyenoord."),
    ("ucl-fabianruiz-titular-j1-2627", "Fabián Ruiz", "Paris Saint-Germain", "Slovan Bratislava", "2026-09-09T17:30:00+00:00",
     "Fabián Ruiz fue pieza clave del PSG campeón de Europa 2025 y del mediocampo de la selección española. Ante un rival de perfil bajo como el Slovan Bratislava, Luis Enrique suele aprovechar para rotar: el mercado apuesta a si el español conserva su lugar en el once o descansa para la liga."),
    ("ucl-lenormand-titular-j1-2627", "Robin Le Normand", "Atlético de Madrid", "Liverpool", "2026-09-09T17:30:00+00:00",
     "Robin Le Normand, central hispano-francés campeón de la Eurocopa 2024 con España, es uno de los defensores de confianza de Simeone desde su llegada al Atlético en 2024. Anfield exige a la línea defensiva, y el mercado apuesta a si Le Normand es parte del once inicial en una de las salidas más duras de la fase de liga."),
    ("ucl-wirtz-titular-j1-2627", "Florian Wirtz", "Liverpool", "Atlético de Madrid", "2026-09-09T17:30:00+00:00",
     "Florian Wirtz llegó al Liverpool en 2025 desde el Leverkusen como el fichaje más caro de la historia del club. Su adaptación a la Premier League ha sido uno de los temas de la temporada, y una noche de Champions en Anfield ante el Atlético es el tipo de partido en el que Slot decide si el alemán es titular indiscutible o parte de la rotación."),
    ("ucl-gnabry-titular-j1-2627", "Serge Gnabry", "Bayern Múnich", "Bodø/Glimt", "2026-09-10T17:30:00+00:00",
     "Serge Gnabry lleva desde 2018 en el Bayern, con altibajos entre lesiones y momentos de gran nivel. Con la llegada de Luis Díaz y la competencia en las bandas, su titularidad ya no es automática. Ante un rival de la parte baja del bombo como Bodø/Glimt, el Bayern suele rotar, lo que hace incierto si el alemán arranca."),
    ("ucl-yoro-titular-j1-2627", "Leny Yoro", "Manchester United", "Sabah", "2026-09-10T17:30:00+00:00",
     "Leny Yoro, central francés fichado por el Manchester United en 2024 a los 18 años, es una de las apuestas de futuro del club. Con el United de regreso a la Champions y un rival accesible como el Sabah, el mercado apunta a si el técnico lo pone de inicio en Old Trafford o reserva a su central joven para la liga."),
]

UCL_GOLES = [
    # id, jugador, club, rival, kickoff_iso, contexto
    ("ucl-haaland-gol-j1-2627", "Erling Haaland", "Manchester City", "FC Porto", "2026-09-08T19:00:00+00:00",
     "Erling Haaland es uno de los goleadores más prolíficos en la historia de la Champions, con más de 50 goles en la competencia antes de cumplir 26 años, y fue de los máximos anotadores de la edición 2025-26. Debuta la fase de liga en el Dragão, un estadio donde Porto suele defender con orden. El mercado apuesta a si el noruego marca en la primera noche europea de la temporada."),
    ("ucl-mbappe-gol-j1-2627", "Kylian Mbappé", "Real Madrid", "Inter", "2026-09-08T19:00:00+00:00",
     "Kylian Mbappé, Bota de Oro europea 2025 en su primera temporada en el Real Madrid, abre la Champions 2026-27 en el Bernabéu ante el Inter, una de las defensas más sólidas de Europa. Es un choque entre el goleador de referencia del torneo y un equipo que llegó a dos finales recientes basándose en su orden defensivo."),
    ("ucl-ferminlopez-gol-j1-2627", "Fermín López", "Barcelona", "Feyenoord", "2026-09-09T16:45:00+00:00",
     "Fermín López, canterano del Barcelona y medallista olímpico con España en 2024, se convirtió en un mediocampista con llegada al gol: fue de los anotadores destacados del Barça en la Champions 2025-26. Ante Feyenoord en el Camp Nou, un partido en el que el Barça parte como favorito, sus opciones de gol dependen de si es titular y del minuto en que participe."),
    ("ucl-dembele-gol-j1-2627", "Ousmane Dembélé", "Paris Saint-Germain", "Slovan Bratislava", "2026-09-09T19:00:00+00:00",
     "Ousmane Dembélé, Balón de Oro 2025 tras liderar al PSG campeón de Europa, abre la nueva Champions en el Parc des Princes ante el Slovan Bratislava, uno de los equipos con menos presupuesto del torneo. Contra rivales cerrados el PSG genera muchas ocasiones, así que la incógnita principal es cuántos minutos juega Dembélé, no si el equipo marca."),
    ("ucl-julianalvarez-gol-j1-2627", "Julián Álvarez", "Atlético de Madrid", "Liverpool", "2026-09-09T19:00:00+00:00",
     "Julián Álvarez, campeón del mundo con Argentina y referencia ofensiva del Atlético desde 2024, visita Anfield en la Jornada 1. Fue de los goleadores destacados de la Champions 2025-26. Ante el Liverpool el Atlético suele jugar a la contra, lo que reduce ocasiones pero convierte a la Araña en el hombre que puede definir cualquier transición."),
    ("ucl-kvaratskhelia-gol-j1-2627", "Khvicha Kvaratskhelia", "Paris Saint-Germain", "Slovan Bratislava", "2026-09-09T19:00:00+00:00",
     "Khvicha Kvaratskhelia, extremo georgiano fichado por el PSG en enero de 2025 y pieza del equipo campeón de Europa, comienza la Champions 2026-27 en casa ante el Slovan Bratislava. Es un partido en el que el PSG debería dominar y generar muchas ocasiones; el mercado apuesta a que el georgiano sea uno de los que las convierta."),
    ("ucl-osimhen-gol-j1-2627", "Victor Osimhen", "Galatasaray", "Sporting CP", "2026-09-09T19:00:00+00:00",
     "Victor Osimhen, delantero nigeriano que lideró el Scudetto del Napoli en 2023 y luego se convirtió en el goleador del Galatasaray, debuta la Champions 2026-27 en Lisboa ante el Sporting. Es de los delanteros más rematadores del torneo, pero visitar el José Alvalade contra el bicampeón portugués es una de las salidas más difíciles de la jornada."),
    ("ucl-kane-gol-j1-2627", "Harry Kane", "Bayern Múnich", "Bodø/Glimt", "2026-09-10T19:00:00+00:00",
     "Harry Kane, máximo goleador histórico de Inglaterra y goleador del Bayern desde 2023, abre la Champions en el Allianz Arena ante el Bodø/Glimt noruego. El Bayern en casa contra rivales de menor presupuesto suele producir goleadas, y Kane es además el lanzador de penales, lo que aumenta sus opciones de marcar."),
    ("ucl-luisdiaz-gol-j1-2627", "Luis Díaz", "Bayern Múnich", "Bodø/Glimt", "2026-09-10T19:00:00+00:00",
     "Luis Díaz, extremo colombiano que llegó al Bayern en 2025 desde el Liverpool, juega su primera Champions con el club bávaro. Ante Bodø/Glimt en Múnich el Bayern parte como gran favorito; la duda para este mercado es si Lucho es titular y si aprovecha las ocasiones que el equipo suele generar contra rivales replegados."),
]

CONTENT: dict[str, dict] = {}

for mid, jugador, club, rival, cierre, ctx in UCL_TITULARES:
    CONTENT[mid] = entry(
        titular_rules(jugador, club, rival, f"{club} vs. {rival} (Jornada 1 de la fase de liga de la Champions League 2026-27)",
                      "la UEFA (uefa.com)", cierre, "la Jornada 1 de la fase de liga (8 al 10 de septiembre)"),
        ctx, UEFA_URL)

for mid, jugador, club, rival, kickoff, ctx in UCL_GOLES:
    CONTENT[mid] = entry(gol_rules(jugador, club, rival, kickoff), ctx, UEFA_URL)

# ── Titulares LaLiga / Premier (seeds del 26 de agosto; el club publica la alineación) ──
LIGA_TITULARES = [
    ("laliga-titular-julian-alvarez-j3", "Julián Álvarez", "Atlético de Madrid", "Sevilla vs. Atlético de Madrid (Jornada 3 de LaLiga 2026-27)",
     "el club en sus canales oficiales y el acta de LaLiga (laliga.com)", "2026-08-29T18:15:00+00:00", "la Jornada 3 de LaLiga (28 al 31 de agosto)", LALIGA_URL,
     "Julián Álvarez es la referencia ofensiva del Atlético de Simeone desde 2024. La visita al Sánchez-Pizjuán en la jornada 3 llega en la primera semana con partidos entre semana de la temporada, cuando los técnicos empiezan a rotar. El mercado apuesta a si el argentino conserva su lugar en el once o descansa ante el Sevilla."),
    ("laliga-titular-arda-guler-j3", "Arda Güler", "Real Madrid", "Real Madrid vs. Málaga (Jornada 3 de LaLiga 2026-27)",
     "el club en sus canales oficiales y el acta de LaLiga (laliga.com)", "2026-08-30T13:45:00+00:00", "la Jornada 3 de LaLiga (28 al 31 de agosto)", LALIGA_URL,
     "Arda Güler, el mediapunta turco que llegó al Real Madrid en 2023, se fue consolidando como pieza creativa del equipo. Contra rivales de la zona baja como el Málaga, el Madrid a veces rota y a veces aprovecha para dar continuidad a sus jóvenes: la titularidad de Güler en el Bernabéu es una lectura directa del rol que le da el técnico esta temporada."),
    ("laliga-titular-bernardo-silva-j3", "Bernardo Silva", "Real Madrid", "Real Madrid vs. Málaga (Jornada 3 de LaLiga 2026-27)",
     "el club en sus canales oficiales y el acta de LaLiga (laliga.com)", "2026-08-30T13:45:00+00:00", "la Jornada 3 de LaLiga (28 al 31 de agosto)", LALIGA_URL,
     "Bernardo Silva llegó al Real Madrid en el verano de 2026 después de casi una década como uno de los pilares del Manchester City de Guardiola. Compite por un lugar en un mediocampo lleno de nombres, y un partido en casa ante el Málaga en la jornada 3 es el escenario típico para ver si el portugués ya es titular o alterna."),
    ("pl-titular-kovacic-j2", "Mateo Kovačić", "Manchester City", "Crystal Palace vs. Manchester City (Jornada 2 de la Premier League 2026-27)",
     "el club en sus canales oficiales y el acta de la Premier League (premierleague.com)", "2026-08-28T17:45:00+00:00", "la Jornada 2 de la Premier League (28 al 31 de agosto)", PL_URL,
     "Mateo Kovačić, campeón de Champions con Real Madrid y Chelsea, compite en el Manchester City por un puesto en un mediocampo muy poblado. La visita a Selhurst Park en la jornada 2 llega en un momento en que Guardiola define su once base de la temporada, y el croata es de los jugadores que alternan titularidad con banca."),
    ("pl-titular-gakpo-j2", "Cody Gakpo", "Liverpool", "Liverpool vs. Nottingham Forest (Jornada 2 de la Premier League 2026-27)",
     "el club en sus canales oficiales y el acta de la Premier League (premierleague.com)", "2026-08-29T10:15:00+00:00", "la Jornada 2 de la Premier League (28 al 31 de agosto)", PL_URL,
     "Cody Gakpo, extremo neerlandés del Liverpool desde 2023, se disputa la banda izquierda con los refuerzos ofensivos que el club sumó en los últimos veranos. En Anfield ante el Nottingham Forest, con la temporada recién iniciada, su presencia en el once es un indicador de la jerarquía del ataque de Slot."),
]
for mid, jugador, club, partido, fuente, cierre, ventana, url, ctx in LIGA_TITULARES:
    CONTENT[mid] = entry(titular_rules(jugador, club, "", partido, fuente, cierre, ventana), ctx, url)

# ── Leagues Cup 2026 ──────────────────────────────────────────────────────
CONTENT["monterrey-semis-leagues-cup-26"] = entry(
    f"""
Resuelve SÍ si Monterrey es el equipo que avanza a semifinales de la Leagues Cup 2026 tras su cuarto de final a partido único contra Chicago Fire, ya sea ganando en los 90 minutos o en la tanda de penales. Resuelve NO si Chicago Fire es el que avanza. A diferencia de los mercados 1X2, aquí sí cuenta la definición por penales porque lo que se predice es quién avanza, no el marcador.

La fuente es el resultado oficial publicado por la Leagues Cup (leaguescup.com). Si el partido se aplaza dentro de la ventana de cuartos de final (25 al 27 de agosto), el mercado se mantiene. Si Monterrey avanzara por decisión administrativa (descalificación del rival, walkover), también resuelve SÍ; si el torneo se suspende sin definir el cruce, el mercado se cancela.

Cierra el {fecha_mx("2026-08-25T00:00:00+00:00")}. {BINARIO_PAGO}
""",
    "La Leagues Cup 2026 enfrenta a clubes de la Liga MX y la MLS. Rayados de Monterrey, uno de los equipos con mayor presupuesto de México, visita a Chicago Fire, el mejor clasificado de la MLS en la fase previa, en un cuarto de final a partido único. En las ediciones anteriores del formato oficial la MLS dominó el torneo, y ningún club mexicano llegó a semifinales en las dos ediciones previas, así que avanzar tendría peso simbólico para la Liga MX.",
    LEAGUES_CUP_URL)

CONTENT["liga-mx-gana-leagues-cup-26"] = entry(
    f"""
Resuelve SÍ si el campeón de la Leagues Cup 2026, definido en la final del 6 de septiembre, es un club de la Liga MX (León, Toluca, Monterrey o América, los cuatro que llegaron a cuartos de final). Resuelve NO si el campeón es un club de la MLS. Cuenta el ganador de la final, incluida una definición por penales.

La fuente es el resultado oficial publicado por la Leagues Cup (leaguescup.com). Si la final se aplaza, el mercado se mantiene abierto hasta que se juegue dentro de septiembre de 2026; si el torneo se cancela sin campeón, el mercado se cancela.

Cierra el {fecha_mx("2026-09-06T20:00:00+00:00")}, hora programada de la final. {BINARIO_PAGO} Si todos los clubes mexicanos son eliminados antes de la final, el mercado se resuelve NO en ese momento.
""",
    "Desde que la Leagues Cup adoptó el formato con todos los clubes de la Liga MX y la MLS (2023), todas las ediciones las ganó un equipo de la MLS: Inter Miami en 2023, Columbus Crew en 2024 y Seattle Sounders en 2025. En 2026 cuatro clubes mexicanos (León, Toluca, Monterrey y América) llegaron a cuartos de final contra cuatro de la MLS. El mercado pregunta si por fin un club de la Liga MX se lleva el trofeo.",
    LEAGUES_CUP_URL)

# ── Liga MX: hechos sociales del Apertura 2026 ────────────────────────────
CONTENT["mx-mascota-incidente-viral-ap26"] = entry(
    social_mx_rules(
        "la mascota oficial de un club de la Liga MX varonil, dentro del estadio en día de partido, protagoniza un altercado físico con un jugador, aficionado, árbitro o miembro del personal, sufre una caída o lesión, es expulsada o retirada por seguridad, o recibe una sanción de la Liga MX o de su propio club",
        "ESPN México, TUDN, Récord, Mediotiempo o Fox Sports MX", 2,
        "del 4 de septiembre de 2026 al final del Apertura 2026, incluida la Liguilla. Bailes, memes, burlas o polémicas en redes sin incidente físico ni sanción no cuentan",
        "2026-12-28T06:00:00+00:00"),
    "Las mascotas de la Liga MX son parte del espectáculo y también de la polémica: cada temporada hay episodios de mascotas que se pelean con aficionados rivales, se caen desde estructuras, interrumpen jugadas o son sancionadas por la Liga o por su club. Este mercado apuesta a que ese patrón se repita antes de que termine el Apertura 2026.",
    None)

CONTENT["mx-perro-interrumpe-partido-ap26"] = entry(
    social_mx_rules(
        "en cualquier partido oficial de la Liga MX varonil del Apertura 2026 (fase regular, Play-In o Liguilla, incluida una final recorrida al 24 y 27 de diciembre) un perro entra al terreno de juego y el árbitro detiene el juego con el balón en juego, confirmado por el video de la transmisión",
        "ESPN, TUDN, Récord o Mediotiempo", 1,
        "del 4 de septiembre de 2026 al final del Apertura 2026. Un perro que entre durante una pausa (balón fuera, medio tiempo, calentamiento) sin que el árbitro deba detener el juego no cuenta",
        "2026-12-28T06:00:00+00:00"),
    "El perro que se mete a la cancha es un clásico del futbol mexicano: la perrita Tunita detuvo un partido del Atlético de San Luis en 2020 y el tlacuache del estadio de Veracruz en 2019 también fue viral. Los estadios en México suelen tener accesos por los que los animales callejeros se cuelan, y el mercado apuesta a que vuelva a pasar en un partido de Primera División antes de la final de diciembre.",
    None)
