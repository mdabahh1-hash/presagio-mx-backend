"""Normas / Contexto / fuente: Política MX (Elecciones, Sheinbaum, Congreso). 21 activos al 2026-09-04."""
from market_content._common import binario_rules, entry

INE = "https://www.ine.mx"
IECM = "https://www.iecm.mx"
PRESIDENCIA = "https://www.gob.mx/presidencia"
DOF = "https://www.dof.gob.mx"
GACETA = "https://gaceta.diputados.gob.mx"

MEDIOS_NAC = "El Universal, Milenio, Reforma, Excélsior, El Financiero, Proceso, Infobae México, Animal Político o Aristegui Noticias"

CONTENT: dict[str, dict] = {}

# ── Elecciones ────────────────────────────────────────────────────────────
CONTENT["influencer-candidatura-2027-anuncio"] = entry(
    binario_rules("""
Resuelve SÍ si entre el 4 de septiembre y el 31 de diciembre de 2026 un creador de contenido mexicano con 3 millones o más de seguidores en al menos una plataforma, cuya fama provenga principalmente de redes sociales (no actores, cantantes, conductores de televisión ni deportistas), anuncia públicamente que buscará una candidatura o precandidatura en las elecciones de 2027, o un partido lo presenta oficialmente como aspirante. El anuncio puede ser en video, publicación, entrevista o evento del partido.

No cuentan los anuncios previos al 4 de septiembre de 2026 (por ejemplo, Mariana Rodríguez), las especulaciones de terceros, las encuestas de partidos que «miden» a un influencer sin que él o el partido confirmen, ni cargos de designación (regidurías plurinominales sin anuncio público del aspirante). El conteo de seguidores se toma de la plataforma en la fecha del anuncio.
""", "2027-01-01T05:59:00+00:00",
        como=f"no hay registro oficial de aspiraciones antes del periodo de precampañas, así que el mercado se resuelve por cobertura de prensa. Se requiere que el anuncio lo reporten al menos dos medios nacionales ({MEDIOS_NAC}). El equipo de VEREDIKT publica los enlaces en los comentarios al resolver."),
    "Rumbo a las elecciones intermedias de 2027 los partidos mexicanos han fichado a figuras de redes sociales para competir por diputaciones y alcaldías, siguiendo el camino de casos como el de Mariana Rodríguez en Nuevo León. Con más de 500 diputaciones, 17 gubernaturas y cientos de ayuntamientos en juego, el mercado apuesta a que antes de que termine 2026 un influencer nuevo (con al menos 3 millones de seguidores) se destape o sea presentado por un partido.",
    None)

CONTENT["cdmx-alcalde"] = entry(
    binario_rules("""
Resuelve SÍ si la candidatura ganadora de la Jefatura de Gobierno de la Ciudad de México en la elección del 6 de junio de 2027 es de un partido o coalición distinta a Morena y sus aliados (PVEM y PT). Una candidatura de Morena, de PVEM, de PT o de cualquier coalición que incluya a alguno de ellos resuelve NO; una candidatura independiente o de cualquier otro partido resuelve SÍ.

La fuente es el cómputo definitivo del Instituto Electoral de la Ciudad de México (IECM), y en su caso la resolución del Tribunal Electoral (TECDMX o TEPJF) si hay impugnaciones. El mercado se resuelve con la constancia de mayoría; si la elección se anula y se repone, se mantiene abierto hasta la elección extraordinaria.

Aviso importante: en el calendario ordinario la Jefatura de Gobierno se renueva en 2030, no en 2027. Si en la jornada del 6 de junio de 2027 no se elige Jefatura de Gobierno (por ejemplo, porque no hubo elección extraordinaria), el mercado se cancela y las posiciones se reembolsan; no se resuelve con el resultado de las alcaldías ni del Congreso local.
""", "2027-06-06T00:00:00+00:00", anticipado=False),
    "La Ciudad de México ha sido gobernada por la izquierda desde 1997 (PRD y después Morena). En 2024 Clara Brugada ganó la Jefatura de Gobierno por Morena, aunque la oposición conservó varias alcaldías del poniente. Este mercado fue creado con la elección intermedia de 2027 en mente, pero la jefatura solo se renovaría ese año si hubiera una elección extraordinaria; de lo contrario se cancela (ver Normas).",
    IECM)

CONTENT["morena-2027"] = entry(
    binario_rules("""
Resuelve SÍ si, en la asignación definitiva de diputaciones federales de la elección del 6 de junio de 2027 (300 de mayoría relativa más 200 de representación proporcional), Morena y sus aliados de coalición (PVEM y PT) suman más de 251 de los 500 escaños, es decir, mayoría absoluta de la Cámara de Diputados.

La fuente es la asignación oficial del Consejo General del INE, y en su caso la resolución definitiva del TEPJF. Cuenta la bancada asignada en la constancia oficial a cada partido, no los cambios de bancada posteriores. Si la reforma electoral en discusión cambia el número de escaños o las reglas de asignación, el umbral se ajusta a más de la mitad del total de escaños que resulte.
""", "2027-06-06T00:00:00+00:00", anticipado=False),
    "Las elecciones intermedias del 6 de junio de 2027 renuevan las 500 diputaciones federales. Morena y sus aliados (PVEM y PT) obtuvieron en 2024 una mayoría calificada que les permitió aprobar reformas constitucionales. Las intermedias históricamente desgastan al partido en el poder (en 2021 Morena perdió la mayoría calificada), y la reforma electoral en discusión durante 2026 podría modificar las reglas de asignación de escaños.",
    INE)

CONTENT["coalicion-morena-334-diputados-2027"] = entry(
    binario_rules("""
Resuelve SÍ si la suma de las diputaciones federales asignadas de forma definitiva a Morena, PVEM y PT tras la elección del 6 de junio de 2027, validada por el Consejo General del INE y, si hay impugnaciones, por el TEPJF, es igual o mayor a 334 de 500 (dos terceras partes de la Cámara). La fuente son las constancias oficiales de asignación.

Cuenta lo asignado a cada partido en la constancia, no las bancadas después de cambios de partido de diputados individuales. Si una reforma cambia el tamaño de la Cámara, el umbral pasa a ser dos terceras partes del nuevo total, redondeadas hacia arriba. El mercado se resuelve cuando la asignación quede firme, normalmente en agosto de 2027.
""", "2027-06-06T14:00:00+00:00", anticipado=False),
    "334 diputados son las dos terceras partes de la Cámara, el umbral necesario para aprobar reformas constitucionales sin votos de la oposición. Morena, PVEM y PT superan hoy ese número y competirán aliados en casi todo el país en 2027, pero las elecciones intermedias suelen castigar al oficialismo y la fórmula de sobrerrepresentación que les dio la mayoría calificada en 2024 está en el centro de la reforma electoral en discusión.",
    INE)

CONTENT["morena-10-gubernaturas-2027"] = entry(
    binario_rules("""
Resuelve SÍ si candidaturas de Morena, o de coaliciones que incluyan a Morena, ganan 10 o más de las 17 gubernaturas que se disputan el 6 de junio de 2027, según los cómputos definitivos de los organismos electorales locales (OPLE) y, en su caso, las resoluciones de los tribunales electorales. Una candidatura de PVEM o PT sin Morena en la coalición no cuenta.

Se resuelve cuando las 17 constancias de mayoría queden firmes. Si alguna elección se anula y se repone después, se toma el resultado de la elección extraordinaria si ocurre antes del 31 de diciembre de 2027; de lo contrario, esa gubernatura no cuenta para Morena.
""", "2027-06-06T14:00:00+00:00", anticipado=False,
        como="cada gubernatura la certifica su instituto electoral estatal (OPLE), no existe una sola página nacional. El equipo de VEREDIKT suma las 17 constancias de mayoría publicadas por los OPLE y las resoluciones de los tribunales, y publica el desglose en los comentarios al resolver."),
    "El 6 de junio de 2027 se renuevan 17 gubernaturas, la elección local más grande del sexenio. Morena ya gobierna 12 de esos estados y su coalición con PVEM y PT competirá en 16 de las 17 entidades. El mercado apuesta a que el oficialismo conserve la mayoría de esas gubernaturas pese al desgaste típico de una elección intermedia.",
    None)

CONTENT["morena-250-diputados-2027"] = entry(
    binario_rules("""
Resuelve SÍ si la asignación definitiva de diputaciones federales de la elección del 6 de junio de 2027, validada por el INE y en su caso por el TEPJF, otorga al partido Morena por sí solo 250 o más de los 500 escaños. Cuenta únicamente la bancada asignada a Morena en la constancia oficial; los escaños de PVEM y PT no suman aunque vayan en coalición.

Si la reforma electoral cambia el tamaño de la Cámara, el umbral pasa a ser la mitad del nuevo total. El mercado se resuelve cuando la asignación quede firme, normalmente en agosto de 2027.
""", "2027-06-06T14:00:00+00:00", anticipado=False),
    "Se renuevan las 500 diputaciones federales el 6 de junio de 2027. El umbral de este mercado es que Morena, sin contar a PVEM ni PT, alcance por sí solo la mitad de la Cámara. En 2024 Morena rozó esa cifra gracias a las reglas de asignación de escaños de representación proporcional, precisamente las que la reforma electoral en discusión durante 2026 podría modificar.",
    INE)

CONTENT["participacion-federal-2027-60"] = entry(
    binario_rules("""
Resuelve SÍ si el cómputo definitivo del INE para la elección federal de diputados del 6 de junio de 2027 registra una participación ciudadana nacional superior al 60.00% de la lista nominal. Un 60.00% exacto resuelve NO. La fuente son los cómputos distritales definitivos publicados por el INE, no el PREP ni el conteo rápido.

Se resuelve cuando el INE publique la cifra oficial de participación de la elección de diputados federales, normalmente en las semanas posteriores a la jornada.
""", "2027-06-06T14:00:00+00:00", anticipado=False),
    "La elección intermedia de 2027 es concurrente con 17 gubernaturas, lo que suele elevar la participación. Aun así, la intermedia de 2021 tuvo participación de alrededor del 52%, y solo las presidenciales superan el 60% (2018 rondó el 63%, 2024 cerca del 61%). Superar 60% en una intermedia sería un salto histórico.",
    INE)

CONTENT["xochitl-2030"] = entry(
    binario_rules("""
Resuelve SÍ si Xóchitl Gálvez queda registrada formalmente ante el INE como candidata a la Presidencia de la República para la elección de 2030, por cualquier partido, coalición o vía independiente. La fuente es el registro oficial de candidaturas que aprueba el Consejo General del INE, previsto para los primeros meses de 2030.

Precandidaturas, encuestas internas, anuncios de intención o el respaldo de un partido sin registro formal no cuentan. Si Gálvez es registrada y después renuncia a la candidatura, el mercado resuelve SÍ de todos modos, porque el registro ya ocurrió.
""", "2030-01-15T00:00:00+00:00", anticipado=False),
    "Xóchitl Gálvez fue la candidata presidencial de la coalición PAN-PRI-PRD en 2024 y perdió ante Claudia Sheinbaum. Tras la elección se alejó de la política partidista, pero sigue siendo una de las figuras opositoras más conocidas del país. El mercado apuesta a si vuelve a ser candidata presidencial en 2030, cuando la oposición deberá definir a su abanderado frente al sucesor de Sheinbaum.",
    INE)

# ── Sheinbaum ─────────────────────────────────────────────────────────────
GRITO_FUENTE = "la transmisión oficial y la versión estenográfica que publica la Presidencia (gob.mx/presidencia)"

CONTENT["sheinbaum-grito-2026-menciona-amlo"] = entry(
    binario_rules(f"""
Resuelve SÍ si durante la arenga del Grito de Independencia desde el balcón de Palacio Nacional la noche del 15 de septiembre de 2026, es decir, desde el primer «Mexicanas, mexicanos» hasta el último «¡Viva México!», la presidenta Claudia Sheinbaum pronuncia las palabras «López Obrador», «Andrés Manuel» o «AMLO». Cuenta una viva («¡Viva Andrés Manuel!») o cualquier mención dentro de la arenga.

No cuentan menciones en discursos previos o posteriores esa noche, en la mañanera del día siguiente ni en el desfile del 16. La fuente es {GRITO_FUENTE}; si hay discrepancia entre el video y la versión estenográfica, manda el video.
""", "2026-09-16T06:00:00+00:00", con_hora=True, anticipado=False),
    "En su primer Grito como presidenta, en 2025, Claudia Sheinbaum dio 22 vivas dedicadas a héroes, heroínas, mujeres indígenas y migrantes, sin mencionar a Andrés Manuel López Obrador, su antecesor y fundador de Morena. El Grito es el discurso más visto del año y cada viva se interpreta políticamente. El mercado apuesta a si en 2026 rompe esa línea y nombra a AMLO desde el balcón.",
    PRESIDENCIA)

CONTENT["sheinbaum-grito-2026-pueblos-indigenas"] = entry(
    binario_rules(f"""
Resuelve SÍ si en la arenga del Grito desde el balcón de Palacio Nacional la noche del 15 de septiembre de 2026 la presidenta pronuncia una viva que contenga textualmente la frase «pueblos indígenas», por ejemplo «¡Vivan los pueblos indígenas!» o «¡Vivan los pueblos indígenas de México!». Las frases «mujeres indígenas», «pueblos originarios», «comunidades indígenas» o «pueblos afromexicanos» NO cuentan por sí solas.

La fuente es {GRITO_FUENTE}; ante discrepancia manda el video. Solo cuenta la arenga, no discursos anteriores o posteriores.
""", "2026-09-16T06:00:00+00:00", con_hora=True, anticipado=False),
    "En el Grito de 2025 una de las vivas de Sheinbaum fue «¡Vivan las mujeres indígenas!», parte de una arenga con acento en mujeres, pueblos originarios y migrantes. El mercado apuesta a un detalle de redacción: si en 2026 la fórmula cambia a «pueblos indígenas». Es el tipo de matiz que se discute cada 16 de septiembre y que la versión estenográfica permite verificar palabra por palabra.",
    PRESIDENCIA)

CONTENT["sheinbaum-mananera-perros-robot-ice"] = entry(
    binario_rules("""
Resuelve SÍ si en la versión estenográfica oficial de una conferencia matutina de la Presidencia (gob.mx/presidencia) celebrada entre el 4 de septiembre y el 31 de diciembre de 2026 un reportero pregunta explícitamente sobre los perros robot o robots cuadrúpedos que ICE planea usar en operativos migratorios, o la presidenta los menciona por iniciativa propia. Basta una mención clara en cualquier mañanera del periodo.

Preguntas sobre ICE, redadas o migración en general que no mencionen los robots no cuentan. Tampoco cuentan menciones de perros robot de autoridades mexicanas (por ejemplo el K7 del Estado de México) salvo que se vinculen expresamente con los de ICE. Si la versión estenográfica de un día no se publica, se usa el video oficial de la mañanera.
""", "2027-01-01T05:59:00+00:00"),
    "El 28 de agosto de 2026 se conoció que ICE, la agencia migratoria de Estados Unidos, planea comprar perros robot para inspecciones en operativos migratorios. La mañanera de Sheinbaum es el espacio donde los reporteros preguntan casi a diario sobre la relación con Estados Unidos y la migración, y los temas virales suelen llegar tarde o temprano. El mercado apuesta a que los robots de ICE se mencionen ahí antes de fin de año.",
    PRESIDENCIA)

# ── Congreso, gobierno y personajes (sin subcategoría) ────────────────────
CONTENT["norona-rompe-visa-sep26"] = entry(
    binario_rules(f"""
Resuelve SÍ si antes del 1 de octubre de 2026 (hora de la Ciudad de México) Gerardo Fernández Noroña rompe, corta, quema o destruye físicamente su visa de Estados Unidos en un acto público o en un video difundido por él mismo. Anunciar que la romperá, mostrarla intacta, decir que la devolvió o que la dejó vencer no cuenta. Tampoco cuenta destruir una fotocopia o una reproducción.
""", "2026-10-01T05:59:00+00:00",
        como=f"no existe registro oficial del hecho; se resuelve con el video del acto y con la cobertura de al menos dos medios nacionales ({MEDIOS_NAC}) que confirmen que destruyó el documento. Los enlaces se publican en los comentarios al resolver."),
    "El 19 de agosto de 2026, ante un reto de la senadora Lilly Téllez en la Comisión Permanente, Fernández Noroña dijo que rompería su visa estadounidense, pero que no podía hacerlo por una lesión en la mano y que lo haría al recuperarse. Días después declaró que sí volverá a viajar a Estados Unidos. El mercado apuesta a si cumple el gesto antes del 1 de octubre.",
    None)

CONTENT["pelea-legisladores-federales-sep26"] = entry(
    binario_rules("""
Resuelve SÍ si entre el 2 y el 30 de septiembre de 2026 (hora de la Ciudad de México) al menos dos diputados federales o senadores en funciones tienen contacto físico agresivo entre sí (golpes, empujones, jalones, sujeciones, forcejeos) dentro del Congreso de la Unión, sus comisiones o la Comisión Permanente, documentado en video. Insultos, gritos, amagos o bloqueos de tribuna sin contacto no cuentan. Congresos locales, eventos partidistas o la calle no cuentan.
""", "2026-10-01T05:59:00+00:00",
        como=f"no hay un registro oficial de altercados; se resuelve con el video del hecho y con al menos dos medios nacionales ({MEDIOS_NAC}) que lo reporten como pelea, zafarrancho, empujones o agresión entre legisladores. Los enlaces se publican en los comentarios."),
    "En 2026 ya hubo dos altercados con contacto físico en el Congreso federal: el 28 de mayo (Escobar contra Gutiérrez Mancilla) y el 12 de agosto (Gutiérrez Mancilla contra Arturo Ávila). El periodo ordinario de sesiones arrancó el 1 de septiembre con la discusión del paquete económico y la reforma electoral, temas que suelen calentar el pleno. El mercado apuesta a que septiembre deje otra pelea.",
    None)

CONTENT["sheinbaum-cancion-mananera-sep26"] = entry(
    binario_rules("""
Resuelve SÍ si entre el 2 y el 30 de septiembre de 2026 (hora de la Ciudad de México) se reproduce una canción, completa o en fragmento, grabada o en vivo, dentro de la conferencia matutina de la Presidencia, a petición de la presidenta o de su equipo. No cuenta la música de fondo de un video institucional, los himnos en ceremonias oficiales, ni una canción que suene por accidente o desde el público.
""", "2026-10-01T05:59:00+00:00",
        como="se verifica con el video oficial de la mañanera publicado por la Presidencia en su canal, y en su defecto con el reporte de al menos dos medios nacionales. El equipo de VEREDIKT indica en los comentarios la fecha y el minuto del video al resolver."),
    "La presidenta ya ha reproducido canciones en la mañanera varias veces en 2026: José Alfredo Jiménez en enero y Grupo Firme el 24 de junio, además de otros momentos musicales con motivo de aniversarios y homenajes. Septiembre, con las fiestas patrias, es un mes propicio para que vuelva a ocurrir. El mercado se limita a las conferencias del 2 al 30 de septiembre.",
    None)

CONTENT["registro-celular-politico-sin-senal-oct26"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 31 de octubre de 2026 (hora de la Ciudad de México) un titular de cargo federal o estatal de elección popular (presidenta, gobernador, senador, diputado federal o local, alcalde), un integrante del gabinete federal o un dirigente nacional de partido declara públicamente, o un medio nacional reporta con nombre y apellido, que su línea celular fue suspendida o deshabilitada por no completar el registro con CURP ante la CRT. Un político que hable del tema en general, o que diga que «casi» le pasa, no cuenta.
""", "2026-11-01T05:59:00+00:00",
        como="no hay registro público de líneas suspendidas por persona; se resuelve con la declaración del propio político (video, publicación o entrevista) o con la nota de un medio nacional (El Universal, Milenio, Reforma, Excélsior, El Financiero, Proceso o Infobae México) que lo identifique. El enlace se publica en los comentarios."),
    "El registro obligatorio de líneas celulares con CURP entró en vigor en 2026 y la Comisión Reguladora de Telecomunicaciones (CRT) suspende las líneas no vinculadas según un calendario por último dígito del número: las terminadas en 0 el 15 de agosto, en 1 el 31 de agosto y así sucesivamente hasta diciembre. Millones de usuarios no han completado el trámite. El mercado apuesta a que a algún político de peso se le apague el teléfono y lo cuente.",
    None)

CONTENT["paso-cortes-proceso-oficial-oct26"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 1 de noviembre de 2026 (hora de la Ciudad de México) ocurre al menos uno de estos hechos: (a) se presenta y registra formalmente en la Gaceta Parlamentaria o en el orden del día una iniciativa de ley, decreto o punto de acuerdo para renombrar el Paso de Cortés en el Congreso de Puebla, el Congreso del Estado de México o el Congreso de la Unión; (b) el Ejecutivo federal o un gobierno estatal publica un decreto o acuerdo oficial con el cambio de nombre; (c) se convoca oficialmente a una consulta pública sobre el cambio.

Declaraciones, mesas de trabajo, foros o anuncios sin documento formal registrado no cuentan.
""", "2026-11-01T05:59:00+00:00",
        como="el hecho puede ocurrir en tres congresos distintos o en un decreto, así que no hay una sola fuente. Se verifica en las gacetas parlamentarias de Puebla, del Estado de México y de la Cámara de Diputados o el Senado, en el Diario Oficial de la Federación o en los periódicos oficiales estatales. El documento que resuelva se enlaza en los comentarios."),
    "El 9 de agosto de 2026 la presidenta Sheinbaum propuso renombrar el Paso de Cortés, el puerto de montaña entre el Popocatépetl y el Iztaccíhuatl, como Paso de los Pueblos Indígenas. Los congresos de Puebla y del Estado de México, que comparten la zona, abrieron una mesa de trabajo el 13 de agosto, pero al arrancar septiembre no existía iniciativa formal. El mercado apuesta a que el trámite oficial inicie antes de noviembre.",
    None)

CONTENT["ine-presupuesto-2027-menor"] = entry(
    binario_rules("""
Resuelve SÍ si la asignación nominal total aprobada al Instituto Nacional Electoral en el Presupuesto de Egresos de la Federación 2027, publicado en el Diario Oficial de la Federación, es inferior a $21,837,221,581 pesos, la cifra autorizada para 2026. Resuelve NO si es igual o superior. Se compara en pesos corrientes, sin ajustar por inflación, y se usa el ramo 22 completo tal como aparece en el decreto del PEF.

Si el PEF 2027 no se publica antes del 31 de diciembre de 2026, el mercado se mantiene abierto hasta su publicación.
""", "2026-11-16T05:59:00+00:00", anticipado=False),
    "El presupuesto del INE se decide cada año en la Cámara de Diputados dentro del PEF. Para 2026 se autorizaron $21,837 millones. 2027 es año de elección federal concurrente con 17 gubernaturas, lo que normalmente eleva el gasto electoral, pero la Cámara suele recortar la solicitud del instituto y la reforma electoral en discusión busca precisamente abaratar las elecciones. El mercado apuesta a un recorte nominal.",
    DOF)

CONTENT["pef-2027-aprobacion-15-nov"] = entry(
    binario_rules("""
Resuelve SÍ si la votación final del Presupuesto de Egresos de la Federación 2027 en el pleno de la Cámara de Diputados (la votación en lo general y en lo particular que lo aprueba definitivamente) ocurre antes de las 23:59 del 15 de noviembre de 2026, hora de la Ciudad de México. Resuelve NO si la votación ocurre después de esa hora, aunque sea en una sesión iniciada el día 15, o si no ocurre. La fuente es la Gaceta Parlamentaria y los comunicados oficiales de la Cámara de Diputados.
""", "2026-11-16T05:59:00+00:00"),
    "La Constitución fija el 15 de noviembre como fecha límite para que la Cámara de Diputados apruebe el PEF del año siguiente. Con mayoría calificada de Morena y aliados, en los últimos años se ha aprobado a tiempo, aunque con sesiones maratónicas que a veces terminan de madrugada. El mercado apuesta a que la votación definitiva se dé dentro del plazo legal y no en la madrugada del 16.",
    GACETA)

CONTENT["andy-recupera-visa-eu-2026"] = entry(
    binario_rules("""
Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora de la Ciudad de México) el Departamento de Estado o la Embajada de Estados Unidos en México confirman, o el propio Andrés Manuel López Beltrán confirma públicamente con evidencia (imagen del documento, sello o comunicación oficial), que su visa fue restituida o que se le emitió una nueva visa estadounidense. Reportes anónimos, filtraciones sin confirmación o el hecho de que viaje a Estados Unidos por otra vía no cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="el gobierno de Estados Unidos no publica el estatus de visas individuales; se resuelve con una confirmación oficial (Departamento de Estado o Embajada) o con la confirmación pública del propio López Beltrán acompañada de evidencia, reportada por al menos dos medios nacionales."),
    "El 14 de agosto de 2026 Andrés Manuel López Beltrán, dirigente de Morena e hijo del expresidente, anunció que Estados Unidos le revocó la visa y envió una carta a Donald Trump. Calificó la decisión como política y dijo que no le interesa visitar Estados Unidos «en estos tiempos». El mercado apuesta a que, pese a eso, la visa le sea devuelta antes de fin de año.",
    None)

CONTENT["andy-solicita-visa-eu-2026"] = entry(
    binario_rules("""
Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora de la Ciudad de México) Andrés Manuel López Beltrán declara públicamente (redes sociales, entrevista o comunicado) que solicitó una nueva visa de Estados Unidos, que pidió la reconsideración o restitución de la revocada, o que presentó un recurso formal ante autoridades estadounidenses; o si un medio nacional documenta la solicitud con evidencia y él no lo desmiente en 72 horas. La carta a Trump del 14 de agosto de 2026 no cuenta por ser anterior al mercado.
""", "2027-01-01T05:59:00+00:00",
        como="no hay registro público de solicitudes de visa; se resuelve con la declaración del propio López Beltrán o con la nota documentada de un medio nacional no desmentida en 72 horas, reportada por al menos dos medios. Los enlaces se publican en los comentarios."),
    "Tras la revocación de su visa anunciada el 14 de agosto de 2026, López Beltrán dijo que la decisión era política y que no le causa ningún problema no viajar a Estados Unidos. Este mercado es el complemento del de la devolución: apuesta a si él da el paso de pedirla de nuevo o impugnar la revocación, algo que contradiría su postura pública.",
    None)

CONTENT["regulacion-scroll-infinito-2026"] = entry(
    binario_rules("""
Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora de la Ciudad de México) el Ejecutivo federal presenta ante el Congreso de la Unión una iniciativa de ley, o publica un proyecto de decreto, norma o lineamientos oficiales, cuyo texto mencione explícitamente limitar, restringir, regular o desactivar el scroll o desplazamiento infinito (en cualquier redacción equivalente, como «desplazamiento continuo» o «reproducción automática ilimitada») en plataformas digitales.

Foros, campañas, declaraciones en la mañanera o documentos de diagnóstico no cuentan. Iniciativas de legisladores individuales o de bancadas sin respaldo formal del Ejecutivo tampoco cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="la iniciativa aparecería en la Gaceta Parlamentaria de la Cámara de Diputados o del Senado, o el proyecto en el Diario Oficial de la Federación o el portal de la dependencia. El equipo de VEREDIKT verifica que el documento sea del Ejecutivo federal y que contenga la mención explícita, y enlaza el texto en los comentarios."),
    "Entre julio y agosto de 2026 la presidenta Sheinbaum abrió un debate nacional sobre redes sociales y menores de edad, y señaló al scroll infinito como uno de los mecanismos adictivos de las plataformas. Dijo que primero irían las reglas para el uso de celulares en escuelas y después se discutiría si regular a las plataformas. El mercado apuesta a que ese segundo paso se convierta en un documento formal antes de fin de año.",
    None)
