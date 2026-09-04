"""Normas / Contexto / fuente: F1 (Checo) y Boxeo (Canelo). 4 activos al 2026-09-04."""
from market_content._common import binario_rules, entry

F1_RESULTS = "https://www.formula1.com/en/results/2026/races"
BOXREC = "https://boxrec.com"

CONTENT: dict[str, dict] = {}

CONTENT["canelo-vence-mbilli-sep-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Saúl «Canelo» Álvarez es declarado ganador de su combate contra Christian Mbilli del 12 de septiembre de 2026 en Riad, por cualquier vía: decisión unánime, mayoritaria o dividida, nocaut, nocaut técnico, detención del árbitro o de la esquina, o descalificación del rival. Un empate (incluido el empate mayoritario), una derrota de Canelo o un «sin decisión» (no contest) resuelven NO.

La fuente es el resultado oficial anunciado en el ring y registrado por los organismos sancionadores; BoxRec es la referencia pública del registro. Si el resultado se modifica después por una decisión administrativa (por ejemplo, un cambio a no contest por dopaje), manda el resultado anunciado la noche de la pelea, no la corrección posterior.

Si la pelea se pospone, el mercado se mantiene abierto hasta la nueva fecha siempre que se celebre antes del 31 de diciembre de 2026; si se cancela o se recorre a 2027, el mercado se cancela y se reembolsa.
""", "2026-09-13T06:00:00+00:00", con_hora=True, anticipado=False),
    "Canelo Álvarez, el boxeador mexicano más importante de su generación y campeón indiscutido de los supermedianos hasta 2025, regresa al ring el 12 de septiembre de 2026 en Riad. Es su primer combate después de perder con Terence Crawford en septiembre de 2025 y de una cirugía de codo. Enfrente estará Christian Mbilli, campeón del CMB de peso supermediano, invicto y de estilo de presión constante. La pregunta es si Canelo, a los 36 años, sigue siendo el mejor de la división.",
    BOXREC)

CONTENT["canelo-gana-por-nocaut-sep-2026"] = entry(
    binario_rules("""
Resuelve SÍ únicamente si Canelo Álvarez gana su combate contra Christian Mbilli del 12 de septiembre de 2026 antes del límite: por nocaut, nocaut técnico, detención del árbitro, retiro de la esquina o del propio rival entre asaltos, o por lesión que impida a Mbilli continuar. Una victoria por decisión de los jueces, un empate, una derrota, una descalificación o un no contest resuelven NO.

La fuente es el resultado oficial anunciado en el ring y registrado por los organismos sancionadores; BoxRec es la referencia pública. Si hay duda entre «TKO» y «decisión técnica» (pelea detenida por corte y decidida en las tarjetas), una decisión técnica resuelve NO porque el resultado lo definen los jueces.

Si la pelea se pospone, el mercado sigue abierto hasta la nueva fecha si se celebra antes del 31 de diciembre de 2026; si se cancela o pasa a 2027, el mercado se cancela.
""", "2026-09-13T06:00:00+00:00", con_hora=True, anticipado=False),
    "Es un mercado derivado del Canelo vs. Mbilli del 12 de septiembre de 2026 en Riad. Canelo ha ganado la mayoría de sus peleas recientes por decisión, no por nocaut, y Mbilli llega invicto y con reputación de boxeador resistente y de mucho volumen. Ganar por la vía rápida es, por eso, un resultado menos probable que simplemente ganar, y este mercado paga precisamente esa diferencia.",
    BOXREC)

CONTENT["checo-puntos-gp-mexico-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Sergio «Checo» Pérez termina entre los diez primeros de la clasificación oficial del Gran Premio de México 2026 (1 de noviembre, Autódromo Hermanos Rodríguez) publicada por la FIA y reflejada en formula1.com. Cuenta la clasificación final con las sanciones aplicadas después de la carrera; si una penalización posterior lo saca del top 10, resuelve NO, y si lo mete, resuelve SÍ. El punto extra por vuelta rápida, si existiera, no cuenta: lo que importa es la posición.

Si Checo no toma la salida (no clasifica, se lesiona o el equipo no participa), resuelve NO. Si la carrera se cancela o se recorre fuera de 2026, el mercado se cancela. Una carrera acortada por bandera roja que otorgue puntos reducidos sigue contando por posición.
""", "2026-11-02T06:00:00+00:00", con_hora=False, anticipado=False),
    "Checo Pérez volvió a la Fórmula 1 en 2026 con Cadillac, la escudería número 11 y debutante en el campeonato, un equipo con ritmo bajo y varios abandonos en su primera temporada. El Gran Premio de México del 1 de noviembre es su carrera de casa ante una afición que llena el Hermanos Rodríguez cada año. Sumar puntos con un auto del fondo de la parrilla requiere una carrera con abandonos o condiciones caóticas, lo que hace de este mercado una apuesta emocional y deportiva a la vez.",
    F1_RESULTS)

CONTENT["checo-top10-campeonato-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Sergio «Checo» Pérez termina la temporada 2026 de Fórmula 1 en la posición 10 o mejor de la clasificación final del Campeonato Mundial de Pilotos publicada por la FIA tras la última carrera (Gran Premio de Abu Dabi, 6 de diciembre de 2026). Se toma la clasificación oficial con todas las sanciones y apelaciones resueltas al momento de la publicación; cambios posteriores por procesos administrativos no modifican el mercado.

Si Checo no completa la temporada (deja el equipo, lesión), cuenta su posición final en la tabla con los puntos que haya sumado. Si el campeonato se cancela antes de terminar, se toma la clasificación vigente al momento de la cancelación.
""", "2026-12-07T06:00:00+00:00", con_hora=False, anticipado=False),
    "Checo Pérez corre en 2026 con Cadillac, la escudería debutante, un auto con poco ritmo y que le ha costado varios abandonos. Con 22 pilotos en la parrilla, terminar entre los diez primeros del campeonato exige sumar puntos con regularidad, algo difícil desde el fondo. La temporada cierra el 6 de diciembre en Abu Dabi, y el mercado apuesta a si Checo consigue rescatar suficientes resultados para quedar dentro del top 10.",
    F1_RESULTS)
