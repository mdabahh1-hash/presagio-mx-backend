"""Normas / Contexto / fuente: Clima (temporada de ciclones, sequía, temperatura). 5 activos al 2026-09-04."""
from market_content._common import FUENTE_CAIDA, binario_rules, entry

SMN = "https://smn.conagua.gob.mx"
MONITOR_SEQUIA = "https://smn.conagua.gob.mx/es/climatologia/monitor-de-sequia/monitor-de-sequia-en-mexico"

CONTENT: dict[str, dict] = {}

CONTENT["clima-dos-ciclones-tierra-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el Servicio Meteorológico Nacional (SMN) o el Centro Nacional de Huracanes de Estados Unidos (NHC) confirman que al menos dos ciclones tropicales con nombre (tormenta tropical o huracán, en el Pacífico o el Atlántico) tocaron tierra en México entre el 27 de agosto y el 30 de noviembre de 2026, entendiendo por tocar tierra que el centro del ciclón cruzó la línea de costa mexicana. Depresiones tropicales sin nombre, ciclones que pasan cerca sin que el centro cruce la costa, y los que tocaron tierra antes del 27 de agosto no cuentan. Un mismo ciclón que toque tierra dos veces cuenta una sola vez.

{FUENTE_CAIDA}
""", "2026-11-30T23:59:00+00:00"),
    "La temporada de ciclones en México va del 15 de mayo (Pacífico) y el 1 de junio (Atlántico) al 30 de noviembre. En una temporada típica entre cuatro y seis ciclones con nombre tocan tierra en el país, y septiembre y octubre son los meses de mayor actividad. El mercado apuesta a que en lo que resta de la temporada 2026, a partir del 27 de agosto, al menos dos ciclones con nombre lleguen a la costa mexicana.",
    SMN)

CONTENT["clima-huracan-cat3-mexico-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si un huracán con categoría 3, 4 o 5 en la escala Saffir-Simpson en el momento de tocar tierra en México (centro cruzando la costa mexicana, Pacífico o Atlántico), según la clasificación del SMN o del NHC, toca tierra entre el 27 de agosto y el 30 de noviembre de 2026. Cuenta la categoría al momento del impacto, no la máxima alcanzada en el mar. Impactos previos al 27 de agosto no cuentan.

{FUENTE_CAIDA}
""", "2026-11-30T23:59:00+00:00"),
    "Los huracanes mayores (categoría 3 o superior) que tocan tierra en México son relativamente frecuentes: Otis (2023, categoría 5 en Acapulco), John (2024) y Erick (2025) son ejemplos recientes. Este mercado, creado a finales de agosto de 2026, apuesta a que ocurra un impacto de huracán mayor en lo que resta de la temporada. Es hermano del mercado que cubre la temporada completa desde mayo.",
    SMN)

CONTENT["huracan-mayor-toca-mexico-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si al menos un huracán con categoría 3, 4 o 5 en la escala Saffir-Simpson en el momento del impacto toca tierra en territorio mexicano (centro cruzando la costa) entre el 15 de mayo y el 30 de noviembre de 2026, según los reportes del SMN de Conagua y del NHC. Cuenta la categoría al tocar tierra, no la máxima en el mar. Si un huracán mayor ya tocó tierra en México antes de hoy dentro de ese periodo, el mercado resuelve SÍ.

{FUENTE_CAIDA}
""", "2026-12-01T06:00:00+00:00"),
    "El SMN pronosticó para 2026 una temporada activa en el Pacífico, con cuatro a cinco huracanes mayores, impulsada por El Niño y por mares más cálidos. La temporada corre del 15 de mayo al 30 de noviembre. En los últimos años México ha recibido al menos un huracán mayor casi cada temporada (Otis en 2023, John en 2024, Erick en 2025). El mercado apuesta a que 2026 no sea la excepción.",
    SMN)

CONTENT["clima-sequia-20pct-dic-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el último Monitor de Sequía de México publicado por Conagua-SMN con fecha de corte en diciembre de 2026 (normalmente el corte del 31 de diciembre, publicado en enero) registra 20.0% o más del territorio nacional en las categorías D1 (sequía moderada) a D4 (sequía excepcional). La categoría D0 (anormalmente seco) no cuenta. Se usa el porcentaje nacional que publica el propio Monitor.

{FUENTE_CAIDA}
""", "2026-12-31T23:59:00+00:00", anticipado=False),
    "El Monitor de Sequía de México se publica cada quincena y clasifica el territorio en cinco categorías (D0 a D4). En los peores momentos de 2024 más del 70% del país estaba en sequía; las lluvias de 2025 redujeron la cifra de forma drástica. Diciembre es temporada seca, así que la sequía suele repuntar hacia fin de año. El mercado apuesta a que el cierre de 2026 tenga al menos 20% del territorio en sequía D1 a D4.",
    MONITOR_SEQUIA)

CONTENT["clima-temp-sobre-normal-sep-dic-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si los resúmenes climatológicos mensuales del SMN registran una temperatura media nacional por encima de la normal climatológica 1991-2020 en al menos tres de los cuatro meses de septiembre, octubre, noviembre y diciembre de 2026. Se usa la temperatura media mensual nacional que publica el SMN en su reporte de cada mes y la comparación con la normal que aparece en el mismo reporte. El mercado deja de operar el 31 de diciembre y se resuelve cuando el SMN publique el resumen de diciembre, normalmente en enero de 2027.

{FUENTE_CAIDA}
""", "2026-12-31T23:59:00+00:00", anticipado=False),
    "México ha registrado temperaturas por encima de la normal en la mayoría de los meses desde 2023, con 2024 como el año más cálido registrado en el país. La normal 1991-2020 es la referencia oficial del SMN. El mercado apuesta a que la tendencia continúe en al menos tres de los últimos cuatro meses de 2026.",
    SMN)
