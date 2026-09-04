"""Normas / Contexto / fuente de los mercados de NFL (63 activos al 2026-09-04)."""
from market_content._common import BINARIO_PAGO, entry, fecha_mx, multi_rules

NFL_SCORES = "https://www.nfl.com/scores/"
NFL_STATS = "https://www.nfl.com/stats/"
ESPN_FANTASY = "https://fantasy.espn.com"
NFL_HONORS = "https://www.nfl.com/honors/"
NFL_SB = "https://www.nfl.com/super-bowl/"

SEMANA1 = "la Semana 1 de la temporada 2026 (10 al 14 de septiembre)"


# ── Ganador del partido ────────────────────────────────────────────────────
def partido_rules(a: str, b: str, kickoff_iso: str, nota: str = "") -> str:
    return f"""
El mercado se resuelve con el equipo ganador del partido {a} vs. {b} de la Semana 1 de la NFL 2026 según el resultado oficial de NFL.com, incluido el tiempo extra. Gana exactamente uno de los dos resultados.{(' ' + nota) if nota else ''}

Si el partido termina oficialmente empatado tras el tiempo extra, ningún equipo gana: el mercado se cancela y las posiciones se reembolsan. Si el kickoff se reprograma, el cierre se mueve al nuevo horario oficial; si el partido se reprograma fuera de {SEMANA1} o se cancela, el mercado se cancela.

Si NFL.com y otro medio reportan marcadores distintos, prevalece el resultado que aparece en NFL.com una vez marcado como final. Sanciones o decisiones administrativas posteriores no cambian un mercado ya resuelto.

El mercado deja de aceptar predicciones al kickoff programado: {fecha_mx(kickoff_iso)}. Cada acción del equipo ganador paga 1 PT; la del perdedor vale 0.
"""


PARTIDOS = [
    # id, equipo A, equipo B, kickoff, nota de normas, contexto
    ("nfl-patriots-seahawks-s1-2026", "Patriots", "Seahawks", "2026-09-10T00:20:00+00:00", "",
     "Kickoff de la temporada NFL 2026, jueves por la noche: la revancha del Super Bowl LX entre Patriots y Seahawks, con Seattle como campeón defensor. Por tradición el campeón abre la temporada en casa. Los Patriots, con Drake Maye en su tercer año como titular, llegan tras una campaña que los devolvió a la élite; los Seahawks, con Jaxon Smith-Njigba como Jugador Ofensivo del Año 2025, buscan repetir. Es el partido más visto de la Semana 1."),
    ("nfl-49ers-rams-s1-2026", "49ers", "Rams", "2026-09-11T00:35:00+00:00",
     "Se juega en Melbourne, Australia, en cancha neutral; ninguno de los dos equipos es local para fines de este mercado.",
     "Primer partido de temporada regular de la NFL en Australia: 49ers contra Rams en Melbourne. Es un duelo divisional del Oeste de la NFC entre dos rivales históricos de California. Los Rams abren 2026 como uno de los favoritos al Super Bowl tras sumar a Myles Garrett, Trent McDuffie y el regreso de Aaron Donald; los 49ers de Christian McCaffrey y Brock Purdy buscan recuperar el dominio de la división."),
    ("nfl-bears-panthers-s1-2026", "Bears", "Panthers", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026, domingo temprano. Bears y Panthers son dos franquicias en reconstrucción con quarterbacks jóvenes elegidos primero en el draft: Caleb Williams (2024) en Chicago y Bryce Young (2023) en Carolina. El partido enfrenta a dos equipos que necesitan arrancar con victoria para sostener sus proyectos."),
    ("nfl-bills-texans-s1-2026", "Bills", "Texans", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Bills contra Texans es un cruce entre dos contendientes de la AFC: Buffalo, con Josh Allen (MVP 2024) y James Cook, ha ganado su división varios años seguidos; Houston, con C.J. Stroud, Nico Collins y la defensa de Will Anderson Jr., es el equipo dominante del Sur de la AFC. Puede ser una previa de playoffs."),
    ("nfl-browns-jaguars-s1-2026", "Browns", "Jaguars", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Browns y Jaguars llegan con temporadas de dudas recientes. Cleveland se apoya en su defensa y en un equipo que cambió de identidad tras la salida de Myles Garrett; Jacksonville, con Trevor Lawrence y Brian Thomas Jr., quiere volver a ser contendiente en el Sur de la AFC. Partido entre equipos de la zona media de la conferencia."),
    ("nfl-bucs-bengals-s1-2026", "Buccaneers", "Bengals", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Buccaneers contra Bengals enfrenta a dos de los ataques más productivos de la liga: Tampa Bay, campeón del Sur de la NFC varias temporadas seguidas con Baker Mayfield, y Cincinnati con Joe Burrow y Ja'Marr Chase, ganador de la triple corona de receptores en 2024. Se espera un partido de muchos puntos."),
    ("nfl-falcons-steelers-s1-2026", "Falcons", "Steelers", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Los Falcons de Bijan Robinson y Drake London, un ataque joven que quiere dar el salto a playoffs, contra los Steelers, la franquicia con más consistencia de la liga: Pittsburgh no ha tenido temporada perdedora en más de dos décadas bajo Mike Tomlin y se apoya en la defensa de T.J. Watt. Estilos opuestos."),
    ("nfl-jets-titans-s1-2026", "Jets", "Titans", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Jets contra Titans enfrenta a dos equipos que buscan una identidad nueva. Los Jets, con Breece Hall y el novato David Bailey (segundo pick del draft 2026) en la defensa, arrancan otro proyecto; Tennessee, con Cam Ward (primer pick de 2025) y el novato Carnell Tate, intenta dejar la parte baja del Sur de la AFC."),
    ("nfl-ravens-colts-s1-2026", "Ravens", "Colts", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Los Ravens de Lamar Jackson (dos veces MVP) y Derrick Henry, uno de los favoritos perennes de la AFC, contra los Colts de Jonathan Taylor, que dependen de su ataque terrestre. Baltimore parte como favorito por plantilla; Indianápolis necesita ganar duelos así para pensar en playoffs."),
    ("nfl-saints-lions-s1-2026", "Saints", "Lions", "2026-09-13T17:00:00+00:00", "",
     "Semana 1 de la NFL 2026. Los Lions, que en los últimos años se convirtieron en uno de los mejores equipos de la NFC con Jared Goff, Amon-Ra St. Brown, Jahmyr Gibbs y Sam LaPorta, enfrentan a unos Saints en reconstrucción. Detroit es favorito claro; para Nueva Orleans es una prueba temprana de cuánto avanzó su proyecto."),
    ("nfl-cardinals-chargers-s1-2026", "Cardinals", "Chargers", "2026-09-13T20:25:00+00:00", "",
     "Semana 1 de la NFL 2026, domingo por la tarde. Los Chargers de Justin Herbert y el entrenador Jim Harbaugh, con una de las mejores defensas de la AFC, contra los Cardinals, que suman al corredor novato Jeremiyah Love, favorito en las apuestas a Novato Ofensivo del Año. Los Chargers parten como favoritos."),
    ("nfl-commanders-eagles-s1-2026", "Commanders", "Eagles", "2026-09-13T20:25:00+00:00", "",
     "Semana 1 de la NFL 2026: duelo divisional del Este de la NFC entre Commanders y Eagles, los dos equipos que jugaron la final de conferencia en enero de 2025. Los Eagles, campeones del Super Bowl LIX con Jalen Hurts y Saquon Barkley, contra los Commanders de Jayden Daniels, Novato Ofensivo del Año 2024. Uno de los partidos más atractivos del domingo."),
    ("nfl-dolphins-raiders-s1-2026", "Dolphins", "Raiders", "2026-09-13T20:25:00+00:00", "",
     "Semana 1 de la NFL 2026. Los Dolphins de De'Von Achane y Jaylen Waddle, un ataque veloz que depende de la salud de su quarterback, contra los Raiders, que arrancan con el veterano Kirk Cousins de titular y Fernando Mendoza, su quarterback novato, en la banca. Ambos equipos vienen de temporadas irregulares y buscan un buen arranque."),
    ("nfl-packers-vikings-s1-2026", "Packers", "Vikings", "2026-09-13T20:25:00+00:00", "",
     "Semana 1 de la NFL 2026: clásico del Norte de la NFC entre Packers y Vikings, una de las rivalidades más antiguas de la liga. Green Bay, con Jordan Love y Josh Jacobs, y Minnesota, con Justin Jefferson como el mejor receptor de la NFL, pelean la división junto a Detroit. Los duelos divisionales de la Semana 1 pesan doble en el desempate."),
    ("nfl-cowboys-giants-s1-2026", "Cowboys", "Giants", "2026-09-14T00:20:00+00:00", "",
     "Sunday Night Football de la Semana 1 de la NFL 2026: Cowboys contra Giants, rivalidad clásica del Este de la NFC. Dallas, con Dak Prescott y CeeDee Lamb, es el equipo más valioso de la liga y siempre juega bajo presión mediática; los Giants, con Malik Nabers como su receptor estrella, buscan salir del fondo de la división. Es el partido en horario estelar del domingo."),
    ("nfl-broncos-chiefs-s1-2026", "Broncos", "Chiefs", "2026-09-15T00:15:00+00:00", "",
     "Monday Night Football de la Semana 1 de la NFL 2026: duelo del Oeste de la AFC entre Broncos y Chiefs. Kansas City, con Patrick Mahomes (tres veces campeón del Super Bowl), ha dominado la división durante casi una década; Denver, con Bo Nix y la defensa de Nik Bonitto, se convirtió en su principal retador. Los Chiefs abren la temporada intentando recuperar el trono de la AFC."),
]

CONTENT: dict[str, dict] = {}
for mid, a, b, kickoff, nota, ctx in PARTIDOS:
    CONTENT[mid] = entry(partido_rules(a, b, kickoff, nota), ctx, NFL_SCORES)


# ── Props de jugador (Semana 1) ────────────────────────────────────────────
def td_rules(jugador: str, equipo: str, rival: str, kickoff_iso: str) -> str:
    return f"""
Resuelve SÍ si {jugador} ({equipo}) anota al menos un touchdown por carrera o por recepción en el partido {equipo} vs. {rival} de la Semana 1 de la NFL 2026, según la estadística oficial de NFL.com, incluido el tiempo extra. No cuentan los pases de touchdown lanzados por el jugador, los touchdowns en devoluciones de patada o de balón suelto, ni las conversiones de dos puntos.

Si {jugador} es declarado inactivo o no participa en ninguna jugada ofensiva, el mercado se cancela y se reembolsa. Si participa aunque sea en una jugada y no anota, resuelve NO. Un touchdown anulado por castigo no cuenta; manda el box score oficial final de NFL.com, incluidas las correcciones estadísticas que la liga publique en la semana siguiente.

Si el partido se reprograma dentro de {SEMANA1}, el cierre se recorre; si sale de esa ventana o se cancela, el mercado se cancela.

El mercado cierra al kickoff programado: {fecha_mx(kickoff_iso)}. {BINARIO_PAGO}
"""


def tdpass_rules(qb: str, equipo: str, rival: str, kickoff_iso: str) -> str:
    return f"""
Resuelve SÍ si {qb} ({equipo}) lanza 2 o más pases de touchdown en el partido {equipo} vs. {rival} de la Semana 1 de la NFL 2026, según la estadística oficial de NFL.com, incluido el tiempo extra. Solo cuentan pases de touchdown: los touchdowns por carrera del quarterback no suman, y un pase anulado por castigo tampoco.

Si {qb} es declarado inactivo o no participa en ninguna jugada, el mercado se cancela y se reembolsa. Si juega aunque sea una serie y termina con 0 o 1 pases de touchdown, resuelve NO. Manda el box score oficial final de NFL.com con sus correcciones estadísticas posteriores.

Si el partido se reprograma dentro de {SEMANA1}, el cierre se recorre; si sale de esa ventana o se cancela, el mercado se cancela.

El mercado cierra al kickoff programado: {fecha_mx(kickoff_iso)}. {BINARIO_PAGO}
"""


def fantasy_rules(jugador: str, equipo: str, rival: str, kickoff_iso: str) -> str:
    return f"""
Resuelve SÍ si {jugador} ({equipo}) acumula 15.0 o más puntos de fantasy en el partido {equipo} vs. {rival} de la Semana 1 de la NFL 2026 con el scoring estándar de ESPN (sin PPR): 0.04 puntos por yarda de pase, 4 por pase de touchdown, −2 por intercepción, 0.1 por yarda de carrera o recepción, 6 por touchdown de carrera o recepción, −2 por balón suelto perdido y 2 por conversión de dos puntos. Las recepciones no suman puntos por sí mismas.

La fuente es la cifra final que muestra ESPN Fantasy para el jugador en la Semana 1. Si ESPN no publica la cifra o hay discrepancia con la estadística oficial, el equipo de VEREDIKT recalcula con el box score final de NFL.com usando la tabla anterior, y esa cifra manda. Se toma el valor definitivo tras las correcciones estadísticas de la liga.

Si {jugador} es declarado inactivo y no juega, el mercado se cancela y se reembolsa. Si juega y no llega a 15.0, resuelve NO (14.9 es NO).

Si el partido se reprograma dentro de {SEMANA1}, el cierre se recorre; si sale de esa ventana o se cancela, el mercado se cancela. El mercado cierra al kickoff programado: {fecha_mx(kickoff_iso)}. {BINARIO_PAGO}
"""


# (id, tipo, jugador, equipo, rival, kickoff, contexto)
PROPS = [
    ("nfl-jsn-td-w1-2026", "td", "Jaxon Smith-Njigba", "Seahawks", "Patriots", "2026-09-10T00:20:00+00:00",
     "Jaxon Smith-Njigba fue el Jugador Ofensivo del Año 2025 y es el receptor principal de unos Seahawks campeones. Abre la temporada en el kickoff del jueves, la revancha del Super Bowl LX contra los Patriots. Como objetivo número uno de su ofensiva, cada semana es candidato a touchdown, pero los partidos de apertura suelen ser más cerrados y con menos anotaciones."),
    ("nfl-maye-2tdpass-w1-2026", "tdpass", "Drake Maye", "Patriots", "Seahawks", "2026-09-10T00:20:00+00:00",
     "Drake Maye, tercer pick del draft 2024, llega a su tercera temporada como quarterback titular de los Patriots y viene de llevarlos al Super Bowl LX. Dos pases de touchdown es la línea típica de un quarterback franquicia en un partido normal; el reto es que enfrente a la defensa campeona de los Seahawks en Seattle, en el partido inaugural de la temporada."),
    ("nfl-mccaffrey-fantasy15-w1-2026", "fantasy", "Christian McCaffrey", "49ers", "Rams", "2026-09-11T00:35:00+00:00",
     "Christian McCaffrey, Jugador Ofensivo del Año 2023, es el corredor más completo de la liga cuando está sano: suma yardas por tierra y por aire y es el principal anotador de los 49ers. Con scoring estándar, 15 puntos equivalen aproximadamente a 90 yardas totales y un touchdown. El partido se juega en Melbourne contra los Rams, que reforzaron su defensa con Myles Garrett y Aaron Donald."),
    ("nfl-mccaffrey-td-w1-2026", "td", "Christian McCaffrey", "49ers", "Rams", "2026-09-11T00:35:00+00:00",
     "Christian McCaffrey es el corredor de referencia de los 49ers y uno de los jugadores con más touchdowns de la NFL en las últimas temporadas cuando ha estado disponible. El debut es el partido histórico en Melbourne contra los Rams, un rival divisional que reforzó su frente defensivo con Myles Garrett y Aaron Donald. Anotar en la Semana 1 depende tanto de su salud como del ritmo del partido."),
    ("nfl-nacua-fantasy15-w1-2026", "fantasy", "Puka Nacua", "Rams", "49ers", "2026-09-11T00:35:00+00:00",
     "Puka Nacua rompió el récord de recepciones y yardas de un novato en 2023 y se consolidó como el receptor principal de Matthew Stafford. En scoring estándar (sin puntos por recepción) necesita cerca de 90 yardas y un touchdown, o 150 yardas sin anotar, para llegar a 15. El partido en Melbourne contra los 49ers es un duelo divisional donde los Rams parten como favoritos."),
    ("nfl-nacua-td-w1-2026", "td", "Puka Nacua", "Rams", "49ers", "2026-09-11T00:35:00+00:00",
     "Puka Nacua es el receptor número uno de los Rams y el objetivo favorito de Matthew Stafford en zona roja. Abre la temporada en el partido de Melbourne contra los 49ers, un rival divisional. Los Rams llegan como candidatos al Super Bowl con una ofensiva que anota con frecuencia, y Nacua suele ser el destino de muchos de esos pases."),
    ("nfl-stafford-2tdpass-w1-2026", "tdpass", "Matthew Stafford", "Rams", "49ers", "2026-09-11T00:35:00+00:00",
     "Matthew Stafford, campeón del Super Bowl LVI con los Rams, sigue siendo el quarterback de un equipo que en 2026 aparece entre los favoritos al título. Con Puka Nacua y un ataque profundo, dos pases de touchdown es un umbral alcanzable en la mayoría de sus partidos. La Semana 1 se juega en Melbourne contra los 49ers, un rival que conoce bien."),
    ("nfl-stafford-fantasy15-w1-2026", "fantasy", "Matthew Stafford", "Rams", "49ers", "2026-09-11T00:35:00+00:00",
     "Para un quarterback, 15 puntos en scoring estándar equivalen a unas 275 yardas de pase y dos touchdowns sin intercepciones, o 300 yardas con un touchdown. Stafford es un pasador de alto volumen en una ofensiva de los Rams diseñada para lanzar; el partido en Melbourne contra la defensa de los 49ers definirá si supera ese umbral en su primera semana."),
    ("nfl-allen-2tdpass-w1-2026", "tdpass", "Josh Allen", "Bills", "Texans", "2026-09-13T17:00:00+00:00",
     "Josh Allen, MVP de la temporada 2024, es el quarterback más productivo de los Bills en su historia y anota tanto por aire como por tierra. Este mercado solo cuenta los pases de touchdown, así que sus típicas carreras a la zona de anotación no suman. El rival de la Semana 1 son los Texans, con una de las mejores defensas de la AFC liderada por Will Anderson Jr."),
    ("nfl-allen-fantasy15-w1-2026", "fantasy", "Josh Allen", "Bills", "Texans", "2026-09-13T17:00:00+00:00",
     "Josh Allen es históricamente uno de los jugadores más valiosos del fantasy porque suma yardas y touchdowns por aire y por tierra. En scoring estándar, sus carreras a la zona de anotación (6 puntos cada una) hacen que el umbral de 15 puntos sea más accesible para él que para la mayoría de los quarterbacks. Enfrenta a los Texans en la Semana 1."),
    ("nfl-bijan-fantasy15-w1-2026", "fantasy", "Bijan Robinson", "Falcons", "Steelers", "2026-09-13T17:00:00+00:00",
     "Bijan Robinson es el motor de la ofensiva de los Falcons y uno de los corredores más usados de la liga tanto en acarreos como en recepciones. En scoring estándar necesita cerca de 90 yardas totales y un touchdown para llegar a 15. Enfrenta a los Steelers, una defensa tradicionalmente fuerte contra la carrera con T.J. Watt al frente."),
    ("nfl-bijan-td-w1-2026", "td", "Bijan Robinson", "Falcons", "Steelers", "2026-09-13T17:00:00+00:00",
     "Bijan Robinson, octavo pick del draft 2023, se convirtió en el principal anotador de los Falcons y en candidato al Jugador Ofensivo del Año 2026. Como corredor de zona roja de Atlanta tiene muchas oportunidades cada semana; el reto de la Semana 1 es la defensa de los Steelers, una de las más disciplinadas de la AFC."),
    ("nfl-breecehall-td-w1-2026", "td", "Breece Hall", "Jets", "Titans", "2026-09-13T17:00:00+00:00",
     "Breece Hall es el corredor principal de los Jets desde 2022 y su principal amenaza en jugadas largas por tierra y por aire. Enfrenta a los Titans en la Semana 1, un partido entre dos equipos en reconstrucción donde el juego terrestre suele tener protagonismo. Anotar depende de que los Jets lleguen a la zona roja con frecuencia."),
    ("nfl-bthomas-td-w1-2026", "td", "Brian Thomas Jr.", "Jaguars", "Browns", "2026-09-13T17:00:00+00:00",
     "Brian Thomas Jr. tuvo una de las mejores temporadas de novato para un receptor en 2024 y es el objetivo número uno de Trevor Lawrence en Jacksonville. La Semana 1 enfrenta a los Browns, una defensa que se apoya en su secundaria. Como receptor de jugadas largas, sus touchdowns dependen de conectar pases profundos más que del volumen en zona roja."),
    ("nfl-burrow-2tdpass-w1-2026", "tdpass", "Joe Burrow", "Bengals", "Buccaneers", "2026-09-13T17:00:00+00:00",
     "Joe Burrow lideró la NFL en yardas y pases de touchdown en 2024 y es el eje de la ofensiva más aérea de la liga junto a Ja'Marr Chase. Dos pases de touchdown es un umbral que supera en la mayoría de sus partidos cuando está sano. La Semana 1 contra los Buccaneers enfrenta a dos ataques de alto ritmo, un escenario favorable para los pasadores."),
    ("nfl-chase-td-w1-2026", "td", "Ja'Marr Chase", "Bengals", "Buccaneers", "2026-09-13T17:00:00+00:00",
     "Ja'Marr Chase ganó la triple corona de receptores en 2024 (líder en recepciones, yardas y touchdowns) y es el jugador más peligroso del ataque de los Bengals. Contra los Buccaneers en la Semana 1, en un partido que promete muchos puntos, es el favorito natural de Joe Burrow en la zona de anotación."),
    ("nfl-collins-td-w1-2026", "td", "Nico Collins", "Texans", "Bills", "2026-09-13T17:00:00+00:00",
     "Nico Collins es el receptor principal de C.J. Stroud en Houston y uno de los mejores de la AFC en yardas por recepción. La Semana 1 contra los Bills es un duelo entre contendientes de la AFC; los Texans tienden a apoyarse en Collins en las jugadas grandes, pero los partidos cerrados reducen las oportunidades de touchdown."),
    ("nfl-gibbs-td-w1-2026", "td", "Jahmyr Gibbs", "Lions", "Saints", "2026-09-13T17:00:00+00:00",
     "Jahmyr Gibbs es el corredor más explosivo de los Lions y, tras la salida de David Montgomery de Detroit, hereda la mayoría de los acarreos en la zona roja, lo que lo convirtió en favorito a Jugador Ofensivo del Año 2026. Contra los Saints, un rival en reconstrucción, los Lions parten como favoritos y se espera que anoten varias veces."),
    ("nfl-goff-2tdpass-w1-2026", "tdpass", "Jared Goff", "Lions", "Saints", "2026-09-13T17:00:00+00:00",
     "Jared Goff dirige una de las ofensivas más productivas de la NFL con Amon-Ra St. Brown, Sam LaPorta y Jahmyr Gibbs. Dos pases de touchdown es su promedio habitual en temporadas recientes, y la Semana 1 contra los Saints, un equipo en reconstrucción, es a priori un partido favorable para el ataque de Detroit."),
    ("nfl-henry-td-w1-2026", "td", "Derrick Henry", "Ravens", "Colts", "2026-09-13T17:00:00+00:00",
     "Derrick Henry, uno de los corredores más dominantes de su generación, llegó a los Ravens en 2024 y siguió anotando con regularidad junto a Lamar Jackson en un ataque terrestre de primer nivel. Es el corredor de zona roja de Baltimore y la Semana 1 contra los Colts, un rival ante el que los Ravens parten como favoritos, ofrece buenas condiciones para anotar."),
    ("nfl-jcook-fantasy15-w1-2026", "fantasy", "James Cook", "Bills", "Texans", "2026-09-13T17:00:00+00:00",
     "James Cook lideró la NFL en touchdowns por carrera en 2024 (16) y es el corredor principal de los Bills. En scoring estándar, sus touchdowns son la vía más directa a 15 puntos: un partido de dos anotaciones y 60 yardas lo supera. Enfrenta a la defensa de los Texans, una de las mejores de la AFC, en la Semana 1."),
    ("nfl-jcook-td-w1-2026", "td", "James Cook", "Bills", "Texans", "2026-09-13T17:00:00+00:00",
     "James Cook se convirtió en uno de los corredores con más touchdowns de la liga en 2024 y es la primera opción terrestre de los Bills en zona roja, aunque comparte esas jugadas con las carreras de Josh Allen. La Semana 1 es contra los Texans, un rival de playoffs con una defensa física que cuida bien la línea de gol."),
    ("nfl-jtaylor-td-w1-2026", "td", "Jonathan Taylor", "Colts", "Ravens", "2026-09-13T17:00:00+00:00",
     "Jonathan Taylor, líder en yardas por tierra de la NFL en 2021, sigue siendo el centro de la ofensiva de los Colts. Contra los Ravens en la Semana 1 enfrenta a una de las defensas más duras contra la carrera; para anotar, Indianápolis necesita sostener series largas y llegar a zona roja, donde Taylor recibe casi todos los acarreos."),
    ("nfl-lamar-2tdpass-w1-2026", "tdpass", "Lamar Jackson", "Ravens", "Colts", "2026-09-13T17:00:00+00:00",
     "Lamar Jackson, dos veces MVP, tuvo en 2024 la mejor temporada de pase de su carrera con más de 40 pases de touchdown. Este mercado cuenta solo pases, no sus carreras, así que depende de que Baltimore anote por aire. Contra los Colts en la Semana 1, los Ravens parten como favoritos y su ofensiva suele producir varios touchdowns por partido."),
    ("nfl-lamar-fantasy15-w1-2026", "fantasy", "Lamar Jackson", "Ravens", "Colts", "2026-09-13T17:00:00+00:00",
     "Lamar Jackson es de los quarterbacks más valiosos del fantasy porque suma yardas y touchdowns por aire y por tierra: en scoring estándar, cada carrera de anotación vale 6 puntos y 50 yardas terrestres valen 5. Contra los Colts en la Semana 1 el umbral de 15 puntos está dentro de su producción habitual; el riesgo es un partido corto o intercepciones."),
    ("nfl-laporta-fantasy15-w1-2026", "fantasy", "Sam LaPorta", "Lions", "Saints", "2026-09-13T17:00:00+00:00",
     "Sam LaPorta rompió el récord de recepciones para un ala cerrada novato en 2023 y es una de las armas de zona roja de Jared Goff. Para un ala cerrada, 15 puntos en scoring estándar (sin PPR) es un umbral alto: requiere unas 90 yardas y un touchdown. Contra los Saints en la Semana 1 los Lions parten como favoritos y suelen repartir los touchdowns entre varios receptores."),
    ("nfl-london-fantasy15-w1-2026", "fantasy", "Drake London", "Falcons", "Steelers", "2026-09-13T17:00:00+00:00",
     "Drake London es el receptor número uno de los Falcons y uno de los que más objetivos recibe en la liga. En scoring estándar necesita alrededor de 90 yardas y un touchdown para llegar a 15 puntos. La Semana 1 enfrenta a la defensa de los Steelers, un rival físico que suele forzar partidos de pocos puntos."),
    ("nfl-stbrown-td-w1-2026", "td", "Amon-Ra St. Brown", "Lions", "Saints", "2026-09-13T17:00:00+00:00",
     "Amon-Ra St. Brown es el receptor más confiable de los Lions y uno de los líderes en touchdowns por recepción de la NFL en las últimas temporadas. Como objetivo favorito de Jared Goff en zona roja, contra los Saints en la Semana 1, en un partido donde Detroit es favorito, tiene buenas condiciones para anotar."),
    ("nfl-achane-td-w1-2026", "td", "De'Von Achane", "Dolphins", "Raiders", "2026-09-13T20:25:00+00:00",
     "De'Von Achane es el corredor más rápido de la liga y una amenaza de touchdown desde cualquier parte del campo, tanto por tierra como en recepciones. Los Dolphins enfrentan a los Raiders en la Semana 1, y su ofensiva depende de generar jugadas grandes; Achane es el jugador con más probabilidad de convertir una de ellas en anotación."),
    ("nfl-barkley-td-w1-2026", "td", "Saquon Barkley", "Eagles", "Commanders", "2026-09-13T20:25:00+00:00",
     "Saquon Barkley corrió más de 2,000 yardas en 2024 y fue clave en el Super Bowl LIX de los Eagles. Es el corredor principal de la mejor ofensiva terrestre de la liga, detrás de una línea dominante. La Semana 1 es contra los Commanders, rival divisional al que los Eagles vencieron en la final de la NFC de enero de 2025; los touchdowns en zona roja a veces los cobra Jalen Hurts con el tush push."),
    ("nfl-daniels-2tdpass-w1-2026", "tdpass", "Jayden Daniels", "Commanders", "Eagles", "2026-09-13T20:25:00+00:00",
     "Jayden Daniels, Novato Ofensivo del Año 2024, llevó a los Commanders a la final de la NFC en su primera temporada y combina pase y carrera. Este mercado solo cuenta pases de touchdown. La Semana 1 contra los Eagles, campeones del Super Bowl LIX y rivales divisionales, es una de las pruebas más difíciles para lanzar dos anotaciones."),
    ("nfl-herbert-2tdpass-w1-2026", "tdpass", "Justin Herbert", "Chargers", "Cardinals", "2026-09-13T20:25:00+00:00",
     "Justin Herbert tiene uno de los brazos más potentes de la liga y récords de yardas de pase en sus primeras temporadas, aunque bajo Jim Harbaugh los Chargers juegan un futbol más conservador y terrestre. Dos pases de touchdown contra los Cardinals en la Semana 1 depende de cuánto abra el juego Los Ángeles en un partido donde es favorito."),
    ("nfl-hurts-2tdpass-w1-2026", "tdpass", "Jalen Hurts", "Eagles", "Commanders", "2026-09-13T20:25:00+00:00",
     "Jalen Hurts, MVP del Super Bowl LIX, anota mucho por tierra con el tush push, pero este mercado cuenta solo pases de touchdown, algo que en los Eagles se reparte con el ataque terrestre de Saquon Barkley. Contra los Commanders en la Semana 1, rival divisional al que Filadelfia eliminó en la final de la NFC, el umbral de dos pases de anotación es exigente para su estilo."),
    ("nfl-jacobs-td-w1-2026", "td", "Josh Jacobs", "Packers", "Vikings", "2026-09-13T20:25:00+00:00",
     "Josh Jacobs, líder en yardas por tierra de la NFL en 2022, es el corredor de zona roja de los Packers desde 2024 y uno de los que más touchdowns acumuló en la liga esa temporada. La Semana 1 es el clásico divisional contra los Vikings; Green Bay se apoya en su ataque terrestre en partidos cerrados, lo que da a Jacobs oportunidades cerca de la línea de gol."),
    ("nfl-jefferson-fantasy15-w1-2026", "fantasy", "Justin Jefferson", "Vikings", "Packers", "2026-09-13T20:25:00+00:00",
     "Justin Jefferson es el receptor con más yardas por partido en la historia de la NFL y el jugador con mayor techo de fantasy en su posición. En scoring estándar, 15 puntos equivalen a unas 90 yardas y un touchdown o 150 yardas sin anotar, cifras que supera con regularidad. El clásico divisional contra los Packers suele ser un partido de muchos pases."),
    ("nfl-jefferson-td-w1-2026", "td", "Justin Jefferson", "Vikings", "Packers", "2026-09-13T20:25:00+00:00",
     "Justin Jefferson es el receptor número uno de los Vikings y el mejor de la liga en su posición según la mayoría de los rankings. Contra los Packers en la Semana 1, rivalidad histórica del Norte de la NFC, es el objetivo preferido de Minnesota tanto en jugadas largas como en zona roja."),
    ("nfl-mclaurin-td-w1-2026", "td", "Terry McLaurin", "Commanders", "Eagles", "2026-09-13T20:25:00+00:00",
     "Terry McLaurin, capitán y receptor principal de los Commanders, tuvo su mejor temporada en touchdowns en 2024 con Jayden Daniels como quarterback. La Semana 1 contra los Eagles, campeones defensores y rivales divisionales, enfrenta a una de las mejores secundarias de la NFC; McLaurin es el objetivo de zona roja más claro de Washington."),
    ("nfl-waddle-fantasy15-w1-2026", "fantasy", "Jaylen Waddle", "Dolphins", "Raiders", "2026-09-13T20:25:00+00:00",
     "Jaylen Waddle es uno de los receptores más rápidos de la NFL y una amenaza de jugada larga en Miami. Sin puntos por recepción, llegar a 15 en scoring estándar requiere unas 90 yardas y un touchdown, o una recepción muy larga con anotación. Enfrenta a los Raiders en la Semana 1, en un partido donde la ofensiva de los Dolphins parte como favorita."),
    ("nfl-lamb-fantasy15-w1-2026", "fantasy", "CeeDee Lamb", "Cowboys", "Giants", "2026-09-14T00:20:00+00:00",
     "CeeDee Lamb, receptor número uno de los Cowboys y uno de los líderes de la liga en recepciones desde 2023, juega el Sunday Night Football de la Semana 1 contra los Giants. En scoring estándar necesita cerca de 90 yardas y un touchdown para 15 puntos; con Dak Prescott lanzándole con alto volumen es un umbral que alcanza en muchos partidos."),
    ("nfl-lamb-td-w1-2026", "td", "CeeDee Lamb", "Cowboys", "Giants", "2026-09-14T00:20:00+00:00",
     "CeeDee Lamb es el objetivo principal de Dak Prescott y el jugador con más recepciones de la historia de los Cowboys en una temporada (135 en 2023). El Sunday Night Football contra los Giants es un duelo divisional del Este de la NFC en horario estelar; Lamb suele ser el destino preferido de Dallas en zona roja."),
    ("nfl-nabers-td-w1-2026", "td", "Malik Nabers", "Giants", "Cowboys", "2026-09-14T00:20:00+00:00",
     "Malik Nabers, sexto pick del draft 2024, rompió el récord de recepciones de un novato de los Giants y es el centro de su ataque aéreo. Enfrenta a los Cowboys en el Sunday Night Football de la Semana 1; Nueva York depende de él para casi todo su juego de pase, lo que le da muchos objetivos, aunque el equipo suele tener dificultades para llegar a zona roja."),
    ("nfl-mahomes-2tdpass-w1-2026", "tdpass", "Patrick Mahomes", "Chiefs", "Broncos", "2026-09-15T00:15:00+00:00",
     "Patrick Mahomes, tres veces campeón del Super Bowl y dos veces MVP, abre 2026 en el Monday Night Football contra los Broncos, rival divisional. Dos pases de touchdown es su promedio en casi todas sus temporadas, aunque en los últimos años los Chiefs han ganado más con defensa y partidos cerrados que con ofensivas explosivas. Denver tiene una de las mejores defensas de la AFC."),
]

BUILDERS = {"td": td_rules, "tdpass": tdpass_rules, "fantasy": fantasy_rules}
SOURCES = {"td": NFL_STATS, "tdpass": NFL_STATS, "fantasy": ESPN_FANTASY}
for mid, tipo, jugador, equipo, rival, kickoff, ctx in PROPS:
    CONTENT[mid] = entry(BUILDERS[tipo](jugador, equipo, rival, kickoff), ctx, SOURCES[tipo])


# ── Premios y Super Bowl (multi) ───────────────────────────────────────────
def premio_rules(premio: str, sigla: str) -> str:
    return multi_rules(f"""
Gana el resultado que corresponda al jugador que reciba el premio {premio} ({sigla}) de la Associated Press para la temporada 2026, anunciado en la gala NFL Honors de febrero de 2027 y publicado en nfl.com. Solo cuenta el premio de la AP, que es el que la NFL reconoce como oficial; los premios de otros medios o de la asociación de jugadores no cuentan.

Si el ganador no está entre los jugadores nombrados en las opciones, gana «Otro jugador». Si el premio se declara compartido, gana el primer jugador que aparezca en el anuncio oficial de la NFL; si ninguno de los premiados está en las opciones, gana «Otro jugador». Un jugador que cambie de equipo durante la temporada sigue siendo la misma opción.

El mercado se resuelve en las horas posteriores a la gala NFL Honors. Si la gala se pospone, el cierre se recorre a la nueva fecha.
""", "2027-02-12T05:00:00+00:00")


CONTENT["nfl-dpoy-2026"] = entry(
    premio_rules("Jugador Defensivo del Año", "DPOY"),
    "El Jugador Defensivo del Año lo vota un panel de 50 periodistas de la Associated Press. Myles Garrett ganó la edición 2025 por unanimidad con récord de 23 capturas y en 2026 juega con los Rams al lado de Aaron Donald, buscando ser el primer bicampeón consecutivo en años. Micah Parsons cayó en las apuestas por una lesión que podría tenerlo fuera hasta la Semana 6. Históricamente el premio lo ganan casi siempre pass rushers (EDGE) con muchas capturas, lo que explica que las nueve opciones nombradas sean cazadores de quarterback.",
    NFL_HONORS)

CONTENT["nfl-droy-2026"] = entry(
    premio_rules("Novato Defensivo del Año", "DROY"),
    "La clase defensiva del draft 2026 es de las más profundas en años. David Bailey, segundo pick global con los Jets, llegó como favorito, pero Rueben Bain Jr. (pick 15, Buccaneers) lo alcanzó en las apuestas durante la pretemporada y seis novatos abren con cuotas por debajo de +1000. El premio lo vota la Associated Press y suele favorecer a pass rushers con muchas capturas o a esquineros con intercepciones y jugadas grandes desde la Semana 1.",
    NFL_HONORS)

CONTENT["nfl-opoy-2026"] = entry(
    premio_rules("Jugador Ofensivo del Año", "OPOY"),
    "Desde 2020 el Jugador Ofensivo del Año ha sido para corredores y receptores (tres y tres), casi nunca para un quarterback, porque el MVP absorbe a los pasadores. Jahmyr Gibbs abre como favorito tras la salida de David Montgomery de Detroit, que le deja casi todos los acarreos; Jaxon Smith-Njigba, ganador en 2025, aparece apenas octavo en las cuotas. Ja'Marr Chase (triple corona 2024), Saquon Barkley (2,000 yardas en 2024) y Bijan Robinson completan el grupo de favoritos.",
    NFL_HONORS)

CONTENT["nfl-oroy-2026"] = entry(
    premio_rules("Novato Ofensivo del Año", "OROY"),
    "El Novato Ofensivo del Año 2026 está más abierto que en años recientes porque la clase de quarterbacks no tiene un titular claro desde la Semana 1: Fernando Mendoza arranca detrás de Kirk Cousins en los Raiders y Carson Beck tampoco tiene un puesto asegurado. Jeremiyah Love (Cardinals) abre como favorito, aunque corre detrás de una de las peores líneas ofensivas de la liga. Carnell Tate (Titans) y Makai Lemon (Eagles) son los receptores mejor posicionados. El premio lo vota la Associated Press.",
    NFL_HONORS)

CONTENT["nfl-campeon-super-bowl-lxi"] = entry(
    multi_rules("""
Gana el resultado del equipo que gane el Super Bowl LXI, programado para el 14 de febrero de 2027 en el SoFi Stadium de Los Ángeles, según el resultado oficial publicado por la NFL (nfl.com). Si el campeón no es uno de los once equipos nombrados, gana «Otro equipo».

El mercado se resuelve al terminar el Super Bowl. Si el partido se pospone, el cierre se recorre a la nueva fecha oficial; si la temporada se cancela sin campeón, el mercado se cancela y se reembolsa. Los equipos eliminados en playoffs no se resuelven por separado: todas las opciones se liquidan juntas al final.
""", "2027-02-15T04:00:00+00:00"),
    "La temporada 2026 de la NFL arranca con los Rams como favoritos al título tras sumar a Myles Garrett y Trent McDuffie y con el regreso de Aaron Donald. Los Seahawks defienden el título del Super Bowl LX, y 14 equipos abren con cuotas de +2000 o mejores, lo que refleja una liga muy pareja. Bills (Josh Allen), Ravens (Lamar Jackson), Eagles (campeones del LIX), Chiefs (Mahomes) y Patriots (finalistas del LX) completan el grupo de aspirantes. El Super Bowl LXI se juega el 14 de febrero de 2027 en el SoFi Stadium.",
    NFL_SB)
