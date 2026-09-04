"""Normas / Contexto / fuente: categoría GLOBAL (elecciones y geopolítica) + Migración. 51 activos al 2026-09-04."""
from market_content._common import binario_rules, entry

CONTENT: dict[str, dict] = {}

FIN_2026 = "2026-12-31T23:59:00+00:00"
NOV3 = "2026-11-03T12:00:00+00:00"


def cargo(nombre: str, cargo_txt: str, pais: str, ends: str, fuente_txt: str, extra: str = "") -> str:
    return binario_rules(f"""
Resuelve SÍ si {nombre} ocupa oficialmente el cargo de {cargo_txt} a las 23:59 (hora local de {pais}) del 31 de diciembre de 2026, según {fuente_txt}. Resuelve NO si para esa hora renunció, fue destituido, perdió el cargo por una elección o moción, falleció o fue reemplazado, aunque sea por un sucesor interino.{(' ' + extra) if extra else ''}

Un periodo de licencia temporal o una incapacidad médica sin relevo formal del cargo no resuelve NO: lo que cuenta es quién es el titular oficial. Si el país está en proceso de formar gobierno pero {nombre} sigue en funciones (en calidad de interino o de transición), resuelve SÍ.
""", ends, anticipado=False)


# ── Elecciones fuera de México ────────────────────────────────────────────
CONTENT["ice-perros-robot-contrato-2026"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 31 de diciembre de 2026 se publica un contrato adjudicado a nombre de ICE (Immigration and Customs Enforcement) por robots cuadrúpedos en SAM.gov, USAspending.gov o FPDS, o si ICE o el Departamento de Seguridad Nacional (DHS) confirman oficialmente la compra o la entrega de unidades. Una previsión de adquisición, una solicitud de información (RFI), una solicitud de propuestas sin adjudicar o una declaración de intención no cuentan. Un contrato del DHS que no nombre a ICE como la agencia compradora tampoco cuenta.
""", "2027-01-01T05:59:00+00:00"),
    "ICE registró en el sistema de previsión de adquisiciones del DHS una compra de entre 1 y 2 millones de dólares en robots Spot de Boston Dynamics para inspecciones en operativos migratorios, lo que se conoció el 28 de agosto de 2026 y generó reacciones en México. Las previsiones de compra del gobierno estadounidense no siempre se convierten en contratos en el mismo año fiscal. El mercado apuesta a que este sí se formalice antes de que termine 2026.",
    "https://sam.gov")

CONTENT["suecia-sap-mas-votos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado nacional oficial de la elección al Riksdag del 13 de septiembre de 2026, publicado por la autoridad electoral sueca (Valmyndigheten, val.se), da al Partido Socialdemócrata (Socialdemokraterna) más votos que a cualquier otro partido individual. Se usa el conteo definitivo, no el preliminar de la noche electoral. Un empate en votos con otro partido resuelve NO.
""", "2026-09-13T06:00:00+00:00", anticipado=False),
    "Suecia elige a su parlamento (Riksdag) el 13 de septiembre de 2026. El Partido Socialdemócrata ha sido el más votado en todas las elecciones suecas desde 1917, incluso en 2022, cuando perdió el gobierno frente al bloque de derecha encabezado por los Moderados con apoyo de los Demócratas de Suecia. El mercado apuesta a que conserve el primer lugar en votos, independientemente de quién forme gobierno.",
    "https://www.val.se")

CONTENT["marruecos-rni-mas-escanos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado oficial de la elección legislativa de Marruecos del 23 de septiembre de 2026, publicado por el Ministerio del Interior, da a la Agrupación Nacional de Independientes (RNI) más escaños en la Cámara de Representantes que a cualquier otro partido individual. Un empate en el primer lugar resuelve NO. Si la elección se pospone, el mercado se mantiene abierto hasta que se celebre en 2026; si pasa a 2027, se cancela.
""", "2026-09-23T07:00:00+00:00", anticipado=False),
    "Marruecos renueva su Cámara de Representantes el 23 de septiembre de 2026. El RNI, partido liberal del primer ministro Aziz Akhannouch, ganó las elecciones de 2021 con amplio margen y encabeza la coalición de gobierno junto al PAM y el Istiqlal. El mercado apuesta a que repita como primera fuerza pese al desgaste de cinco años de gobierno.",
    "https://www.elections.ma")

CONTENT["letonia-nueva-unidad-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado oficial de la elección al Saeima (parlamento de Letonia) de octubre de 2026, publicado por la Comisión Electoral Central (CVK, cvk.lv), da a Nueva Unidad (Jaunā Vienotība) más escaños que a cualquier otro partido o lista individual. Un empate en el primer lugar resuelve NO. Si la elección se pospone dentro de 2026, el cierre se recorre.
""", "2026-10-03T04:00:00+00:00", anticipado=False),
    "Letonia elige a los 100 diputados del Saeima en octubre de 2026. Nueva Unidad, el partido liberal-conservador de la primera ministra Evika Siliņa y del expremier Krišjānis Kariņš, fue la fuerza más votada en 2022. El mercado apuesta a que conserve el primer lugar en escaños frente a partidos de oposición y populistas en ascenso.",
    "https://www.cvk.lv")

CONTENT["brasil-segunda-vuelta-2026"] = entry(
    binario_rules("""
Resuelve SÍ si, según el resultado oficial del Tribunal Superior Electoral (TSE), ningún candidato obtiene más del 50% de los votos válidos (excluidos blancos y nulos) en la primera vuelta de la elección presidencial de Brasil del 4 de octubre de 2026, de modo que se convoca segunda vuelta. Resuelve NO si un candidato gana en primera vuelta. La fuente es la totalización oficial del TSE.
""", "2026-10-04T11:00:00+00:00", anticipado=False),
    "Brasil elige presidente el 4 de octubre de 2026. Desde la redemocratización, la mayoría de las elecciones presidenciales han necesitado segunda vuelta (1989, 2002, 2006, 2010, 2014, 2018 y 2022); solo 1994 y 1998 se resolvieron en primera vuelta. Con Lula da Silva buscando la reelección y una derecha dividida tras la inhabilitación de Bolsonaro, el mercado apuesta a que se repita el patrón de dos vueltas.",
    "https://www.tse.jus.br")

CONTENT["lula-gana-brasil-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Luiz Inácio Lula da Silva es proclamado presidente electo de Brasil por el Tribunal Superior Electoral (TSE) en la elección de 2026, ya sea en la primera vuelta del 4 de octubre o en la segunda vuelta del 25 de octubre. Si gana en primera vuelta, el mercado se resuelve de forma anticipada. Si Lula no es candidato en la boleta, resuelve NO.
""", "2026-10-25T11:00:00+00:00"),
    "Lula da Silva, presidente de Brasil por tercera vez desde 2023, busca la reelección en 2026 a los 80 años. Con Jair Bolsonaro inhabilitado, la derecha llega dividida entre varios aspirantes. El mercado apuesta a que Lula sea proclamado ganador, en primera o segunda vuelta, y se resuelve con la proclamación oficial del TSE.",
    "https://www.tse.jus.br")

CONTENT["israel-participacion-70-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el porcentaje oficial de participación publicado por la Comisión Electoral Central de Israel para la elección a la 26.ª Knéset del 27 de octubre de 2026 es igual o mayor a 70.0% del padrón. Se usa la cifra definitiva de la Comisión. Si la elección se adelanta o se pospone dentro de 2026, el cierre se recorre; si pasa a 2027, el mercado se cancela.
""", "2026-10-27T05:00:00+00:00", anticipado=False),
    "Israel elige su 26.ª Knéset el 27 de octubre de 2026. La participación en las cinco elecciones entre 2019 y 2022 osciló entre 67% y 71%, con 70.6% en 2022. Tras la guerra en Gaza y las tensiones internas, el mercado apuesta a si la participación vuelve a alcanzar el 70%.",
    "https://bechirot.gov.il")

CONTENT["likud-aliados-61-escanos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si, en el resultado oficial definitivo de la elección a la 26.ª Knéset del 27 de octubre de 2026 publicado por la Comisión Electoral Central, Likud más los partidos que hayan anunciado públicamente antes de la elección que formarán coalición con Likud suman al menos 61 de los 120 escaños. Solo cuentan los partidos con compromiso de coalición anunciado antes de la jornada electoral; los que se sumen después no cuentan. El equipo de VEREDIKT publica la lista de partidos considerados «aliados declarados» en los comentarios antes de la elección.
""", "2026-10-27T05:00:00+00:00", anticipado=False),
    "61 escaños son la mayoría de la Knéset de 120. En 2022 Likud y sus aliados de derecha y religiosos obtuvieron 64 escaños y formaron el gobierno de Netanyahu. El mercado apuesta a que el bloque declarado de Likud vuelva a tener mayoría propia tras la elección del 27 de octubre de 2026, sin depender de partidos de centro.",
    "https://bechirot.gov.il")

CONTENT["likud-mas-escanos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado oficial definitivo de la elección a la 26.ª Knéset del 27 de octubre de 2026, publicado por la Comisión Electoral Central de Israel, da a Likud más escaños que a cualquier otro partido o lista individual. Un empate en el primer lugar resuelve NO. Las listas conjuntas cuentan como un solo partido según aparezcan en la boleta.
""", "2026-10-27T05:00:00+00:00", anticipado=False),
    "Likud, el partido de Benjamin Netanyahu, ha sido la primera fuerza de la Knéset en la mayoría de las elecciones desde 2009, con 32 escaños en 2022. Enfrente aparecen listas de centro y derecha que buscan superarlo tras el desgaste de la guerra. El mercado apuesta solo al primer lugar en escaños, no a quién forma gobierno.",
    "https://bechirot.gov.il")

CONTENT["california-gobernador-demo-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado oficial certificado por el Secretario de Estado de California da el triunfo en la elección de gobernador del 3 de noviembre de 2026 a la candidatura del Partido Demócrata. Como California usa primaria abierta (top two), si los dos finalistas son demócratas resuelve SÍ. Se usa la certificación oficial, no las proyecciones de medios.
""", NOV3, anticipado=False),
    "California elige gobernador el 3 de noviembre de 2026 para suceder a Gavin Newsom, que no puede reelegirse. Ningún republicano gana una elección estatal en California desde 2006. Con el sistema de primaria top two, es posible que la boleta final tenga a dos demócratas, lo que resolvería SÍ automáticamente.",
    "https://www.sos.ca.gov/elections")

CONTENT["control-unificado-congreso-2027"] = entry(
    binario_rules("""
Resuelve SÍ si, al instalarse el 120.º Congreso de Estados Unidos el 3 de enero de 2027, un mismo partido (republicano o demócrata) tiene la mayoría de la Cámara de Representantes y el control del Senado, contando a los senadores independientes según la bancada con la que se agrupen. Resuelve NO si el control queda dividido. Se usa la composición oficial al momento de la instalación, según los registros del Clerk de la Cámara y del Senado.
""", NOV3, anticipado=False),
    "Las elecciones intermedias del 3 de noviembre de 2026 renuevan los 435 escaños de la Cámara y 33 del Senado. Tras 2024 los republicanos controlan ambas cámaras y la presidencia. Históricamente el partido del presidente pierde escaños en las intermedias, lo que hace probable un Congreso dividido. El mercado apuesta a que un solo partido conserve las dos cámaras.",
    "https://www.congress.gov")

CONTENT["demos-camara-congreso-120"] = entry(
    binario_rules("""
Resuelve SÍ si, con los resultados certificados de las elecciones del 3 de noviembre de 2026, el Partido Demócrata tiene la mayoría de escaños de la Cámara de Representantes (al menos 218 de 435, o la mayoría de los escaños ocupados) al instalarse el 120.º Congreso el 3 de enero de 2027. La fuente es el registro oficial del Clerk de la Cámara. Elecciones especiales o vacantes posteriores a la instalación no modifican el mercado.
""", NOV3, anticipado=False),
    "Los republicanos obtuvieron en 2024 una mayoría estrecha en la Cámara de Representantes. En las intermedias el partido del presidente suele perder escaños (los demócratas perdieron la Cámara en 2022, los republicanos en 2018). El mercado apuesta a que los demócratas recuperen la mayoría en las elecciones del 3 de noviembre de 2026.",
    "https://clerk.house.gov")

CONTENT["demos-ganancia-20-escanos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si la comparación entre la composición inicial del 119.º Congreso (3 de enero de 2025) y la composición inicial del 120.º Congreso (3 de enero de 2027) muestra una ganancia neta demócrata de 20 o más escaños en la Cámara de Representantes, según los registros oficiales del Clerk de la Cámara. Se comparan escaños asignados a cada partido en cada instalación, sin considerar vacantes o cambios intermedios.
""", NOV3, anticipado=False),
    "En las intermedias de 2018 los demócratas ganaron 41 escaños; en 2022 los republicanos ganaron 9. Una ganancia de 20 o más escaños sería una «ola» demócrata clara. El mercado se resuelve comparando la composición de la Cámara al instalarse cada Congreso, no los resultados distrito por distrito.",
    "https://clerk.house.gov")

CONTENT["demos-voto-popular-camara-2026"] = entry(
    binario_rules("""
Resuelve SÍ si la suma oficial de votos emitidos en los 435 distritos de la Cámara de Representantes en las elecciones del 3 de noviembre de 2026, según las estadísticas electorales que publica el Clerk de la Cámara, da más votos a candidatos del Partido Demócrata que a los de cualquier otro partido. Los distritos sin oposición cuentan con los votos que registren. Se usa la publicación oficial, que suele aparecer meses después de la elección; el mercado permanece abierto hasta entonces.
""", NOV3, anticipado=False),
    "El voto popular nacional para la Cámara es el termómetro más claro del ánimo electoral en Estados Unidos: los demócratas lo ganaron en 2018 y 2020, los republicanos en 2022 y 2024. El mercado apuesta a que los demócratas sumen más votos que los republicanos en los 435 distritos en las intermedias de 2026.",
    "https://clerk.house.gov")

CONTENT["florida-gobernador-rep-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado oficial certificado por la División de Elecciones de Florida da el triunfo en la elección de gobernador del 3 de noviembre de 2026 a la candidatura del Partido Republicano. Se usa la certificación oficial del estado, no las proyecciones de medios.
""", NOV3, anticipado=False),
    "Florida elige gobernador el 3 de noviembre de 2026 para suceder a Ron DeSantis, que termina su segundo periodo. El estado, antes competitivo, se ha vuelto sólidamente republicano: DeSantis ganó en 2022 por casi 20 puntos y Trump lo ganó con holgura en 2024. El mercado apuesta a que el candidato republicano conserve la gubernatura.",
    "https://dos.fl.gov/elections/")

CONTENT["republicanos-52-senadores-2027"] = entry(
    binario_rules("""
Resuelve SÍ si el Partido Republicano cuenta con al menos 52 senadores electos y en funciones al instalarse el 120.º Congreso el 3 de enero de 2027, según el registro oficial del Senado de Estados Unidos. Los independientes no cuentan como republicanos aunque se agrupen con ellos. Vacantes o nombramientos posteriores a la instalación no modifican el mercado.
""", NOV3, anticipado=False),
    "Los republicanos tienen 53 senadores tras las elecciones de 2024. En 2026 se renuevan 33 escaños del Senado, y el mapa favorece en general a los republicanos porque defienden pocos estados competitivos. El mercado apuesta a que conserven al menos 52 senadores, es decir, que pierdan como máximo un escaño neto.",
    "https://www.senate.gov")

CONTENT["republicanos-senado-congreso-120"] = entry(
    binario_rules("""
Resuelve SÍ si el Partido Republicano controla el Senado al instalarse el 120.º Congreso el 3 de enero de 2027, contando a los independientes según el partido con el que se agrupen. Con 50 senadores por bando, el control lo define el voto del vicepresidente: en ese caso resuelve SÍ mientras el vicepresidente sea republicano. La fuente es el registro oficial del Senado.
""", NOV3, anticipado=False),
    "Los republicanos controlan el Senado con 53 escaños desde enero de 2025. En las intermedias de 2026 se renuevan 33 escaños; los demócratas necesitan una ganancia neta de cuatro para tomar el control, en un mapa donde defienden estados competitivos como Georgia y Michigan. El mercado apuesta a que los republicanos conserven la mayoría.",
    "https://www.senate.gov")

CONTENT["texas-gobernador-rep-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el resultado oficial certificado por el Secretario de Estado de Texas da el triunfo en la elección de gobernador del 3 de noviembre de 2026 a la candidatura del Partido Republicano. Se usa la certificación oficial del estado, no las proyecciones de medios.
""", NOV3, anticipado=False),
    "Texas elige gobernador el 3 de noviembre de 2026, con Greg Abbott buscando un cuarto periodo. Ningún demócrata gana una elección estatal en Texas desde 1994, y Abbott ganó en 2022 por 11 puntos. El mercado apuesta a que el candidato republicano vuelva a ganar la gubernatura.",
    "https://www.sos.state.tx.us/elections/")

CONTENT["nz-bloque-derecha-mayoria-2026"] = entry(
    binario_rules("""
Resuelve SÍ si, en la asignación definitiva de escaños de la elección general de Nueva Zelanda del 7 de noviembre de 2026 publicada por la Comisión Electoral (electionresults.govt.nz), el Partido Nacional, ACT y New Zealand First suman al menos la mitad más uno de los escaños del nuevo Parlamento (incluidos escaños de exceso si los hay). Cuenta la suma de los tres partidos, formen o no gobierno juntos después.
""", "2026-11-06T20:00:00+00:00", anticipado=False),
    "En 2023 el Partido Nacional de Christopher Luxon formó gobierno con ACT y New Zealand First tras sumar mayoría en el Parlamento neozelandés. La elección del 7 de noviembre de 2026 decide si esa coalición de derecha conserva los números frente al bloque de Labour, los Verdes y Te Pāti Māori. El mercado apuesta a que los tres partidos vuelvan a sumar mayoría.",
    "https://www.electionresults.govt.nz")

CONTENT["nz-national-mas-votos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el party vote (voto de lista) oficial de la elección general de Nueva Zelanda del 7 de noviembre de 2026, publicado por la Comisión Electoral, da al Partido Nacional más votos que a cualquier otro partido individual. Se usa el resultado oficial definitivo, incluidos los votos especiales, no el conteo preliminar de la noche. Un empate resuelve NO.
""", "2026-11-06T20:00:00+00:00", anticipado=False),
    "Nueva Zelanda vota con sistema proporcional mixto, y el party vote decide el reparto de escaños. El Partido Nacional fue el más votado en 2023 con cerca del 38%, por delante de Labour. El mercado apuesta a que National conserve el primer lugar en el voto de lista en la elección del 7 de noviembre de 2026.",
    "https://www.electionresults.govt.nz")

# ── Geopolítica y jefes de gobierno ───────────────────────────────────────
CONTENT["armenia-azerbaiyan-tratado-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el tratado de paz entre Armenia y Azerbaiyán es ratificado formalmente por los parlamentos (o el procedimiento constitucional equivalente) de ambos países y entra en vigor antes del 31 de diciembre de 2026. La firma del tratado sin ratificación, la ratificación por un solo país o una declaración conjunta no cuentan. Se requiere que ambos gobiernos, o un depositario oficial, confirmen la entrada en vigor.
""", FIN_2026,
        como="no hay una sola fuente: se verifica con los comunicados oficiales del gobierno y el parlamento de Armenia y de Azerbaiyán sobre la ratificación y la entrada en vigor, confirmados por al menos dos agencias internacionales (Reuters, AP, AFP, EFE). Los enlaces se publican en los comentarios."),
    "Armenia y Azerbaiyán acordaron en 2025 el texto de un tratado de paz para cerrar tres décadas de conflicto por Nagorno-Karabaj, pero su firma y ratificación han estado condicionadas a cambios constitucionales en Armenia y a otras exigencias de Bakú. El mercado apuesta a que el tratado quede ratificado por ambos y entre en vigor antes de que termine 2026.",
    None)

CONTENT["bulgaria-gerb-presidencia-2026"] = entry(
    binario_rules("""
Resuelve SÍ si gana la elección presidencial de Bulgaria de 2026 (prevista para el otoño; la fecha de cierre se ajustará a la de la primera vuelta cuando se confirme) un candidato cuyo apoyo formal por parte de GERB haya sido anunciado públicamente antes de la primera vuelta. Cuenta tanto un candidato propio de GERB como uno independiente respaldado oficialmente por el partido. Un apoyo anunciado solo para la segunda vuelta no cuenta. La fuente es el resultado oficial de la Comisión Electoral Central (CIK).
""", FIN_2026, anticipado=False),
    "Bulgaria elige presidente en el otoño de 2026 para suceder a Rumen Radev, que termina su segundo periodo. GERB, el partido de Boyko Borisov, es la primera fuerza parlamentaria pero ha perdido las dos últimas presidenciales frente a Radev. El mercado apuesta a que esta vez un candidato respaldado por GERB gane la presidencia.",
    "https://www.cik.bg")

CONTENT["burnham-pm-fin-2026"] = entry(
    cargo("Andy Burnham", "primer ministro del Reino Unido", "Londres", FIN_2026, "el registro oficial del gobierno británico (gov.uk)"),
    "Andy Burnham, exalcalde del Gran Mánchester, asumió como primer ministro del Reino Unido tras suceder a Keir Starmer al frente del Partido Laborista. Con un partido dividido y una oposición de Reform UK en ascenso, el mercado apuesta a que Burnham conserve el cargo hasta el último día de 2026.",
    "https://www.gov.uk/government/ministers/prime-minister")

CONTENT["carney-pm-fin-2026"] = entry(
    cargo("Mark Carney", "primer ministro de Canadá", "Ottawa", FIN_2026, "el registro oficial de la Oficina del Primer Ministro (pm.gc.ca)"),
    "Mark Carney, exgobernador del Banco de Canadá y del Banco de Inglaterra, es primer ministro de Canadá desde marzo de 2025 y ganó la elección federal de abril de ese año. Con una relación comercial tensa con Estados Unidos y un gobierno liberal sin mayoría holgada, el mercado apuesta a que siga en el cargo al cerrar 2026.",
    "https://pm.gc.ca")

CONTENT["china-taiwan-fuego-real-24nm-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el gobierno de China (Ministerio de Defensa o Comando del Teatro Oriental del Ejército Popular de Liberación), el gobierno de Taiwán (Ministerio de Defensa Nacional) o ambos confirman oficialmente ejercicios militares chinos con fuego real (disparos de artillería, misiles o munición real) realizados dentro de las 24 millas náuticas (zona contigua) de la isla principal de Taiwán entre el 27 de agosto y el 31 de diciembre de 2026. Ejercicios sin fuego real, incursiones aéreas o navales, o fuego real fuera de las 24 millas o alrededor de islas menores (Kinmen, Matsu) no cuentan.
""", FIN_2026,
        como="se resuelve con la confirmación oficial de cualquiera de los dos gobiernos, publicada en sus comunicados y reportada por al menos dos agencias internacionales (Reuters, AP, AFP). El equipo de VEREDIKT enlaza el comunicado en los comentarios."),
    "China ha realizado ejercicios militares a gran escala alrededor de Taiwán en 2022, 2023, 2024 y 2025, en algunos casos con fuego real, pero generalmente fuera de la zona contigua de 24 millas náuticas de la isla principal. Cruzar esa línea con munición real sería una escalada significativa. El mercado apuesta a que ocurra antes de terminar 2026.",
    None)

CONTENT["corea-norte-prueba-nuclear-2026"] = entry(
    binario_rules("""
Resuelve SÍ si la Organización del Tratado de Prohibición Completa de los Ensayos Nucleares (CTBTO), la ONU, o los gobiernos de Corea del Sur o Estados Unidos confirman una prueba nuclear realizada por Corea del Norte antes del 31 de diciembre de 2026. Pruebas de misiles, incluso con capacidad nuclear, no cuentan; solo una detonación nuclear. Un evento sísmico sin confirmación oficial de que fue una prueba nuclear no cuenta.
""", FIN_2026),
    "Corea del Norte ha realizado seis pruebas nucleares, la última en septiembre de 2017. Desde entonces ha ampliado su arsenal de misiles y su sitio de pruebas de Punggye-ri ha mostrado señales de estar listo para una séptima prueba, según inteligencia surcoreana y estadounidense. El mercado apuesta a que la séptima prueba ocurra antes de que termine 2026.",
    "https://www.ctbto.org")

CONTENT["eeuu-iran-acuerdo-nuclear-2026"] = entry(
    binario_rules("""
Resuelve SÍ si los gobiernos de Estados Unidos e Irán firman antes del 31 de diciembre de 2026 un documento bilateral o multilateral vinculante sobre el programa nuclear iraní. Cuenta un acuerdo nuevo o una versión renovada del JCPOA firmada por ambos. Un acuerdo marco, una declaración de principios, negociaciones anunciadas o un acuerdo interino verbal no cuentan; se requiere un documento firmado y reconocido como vinculante por ambas partes.
""", FIN_2026,
        como="se verifica con los comunicados oficiales del Departamento de Estado de Estados Unidos y del Ministerio de Relaciones Exteriores de Irán, confirmados por al menos dos agencias internacionales (Reuters, AP, AFP). El equipo de VEREDIKT enlaza los comunicados en los comentarios."),
    "Estados Unidos abandonó el acuerdo nuclear con Irán (JCPOA) en 2018. Tras los ataques de Israel y Estados Unidos contra instalaciones nucleares iraníes en junio de 2025, las negociaciones se interrumpieron y luego se han reanudado de forma intermitente con mediación de Omán y Qatar. El mercado apuesta a que antes de terminar 2026 se firme un nuevo acuerdo vinculante.",
    None)

CONTENT["francia-disolucion-asamblea-2026"] = entry(
    binario_rules("""
Resuelve SÍ si se publica en el Journal officiel (Légifrance) un decreto del presidente de Francia que disuelva la Asamblea Nacional, emitido después del 26 de agosto y antes del 31 de diciembre de 2026. El anuncio verbal de una disolución no cuenta hasta que el decreto se publique. Una moción de censura que derribe al gobierno sin disolución no cuenta.
""", FIN_2026),
    "Emmanuel Macron disolvió la Asamblea Nacional en junio de 2024, lo que produjo un parlamento fragmentado sin mayoría y una sucesión de gobiernos frágiles. Desde junio de 2025 el presidente vuelve a tener la facultad de disolver. Con presupuestos difíciles de aprobar y gobiernos expuestos a mociones de censura, el mercado apuesta a que Macron convoque nuevas legislativas antes de terminar 2026.",
    "https://www.legifrance.gouv.fr")

CONTENT["haiti-primera-vuelta-2026"] = entry(
    binario_rules("""
Resuelve SÍ si la votación nacional de primera vuelta de la elección presidencial de Haití se celebra efectivamente (se abren las urnas a nivel nacional) antes del 31 de diciembre de 2026. Una convocatoria, un calendario publicado o una votación parcial en algunas regiones no cuentan. Un aplazamiento más allá de 2026 resuelve NO.
""", FIN_2026, anticipado=True,
        como="se verifica con los comunicados del Consejo Electoral Provisional de Haití (CEP) y con la cobertura de al menos dos agencias internacionales (Reuters, AP, AFP, EFE) que confirmen que la votación se llevó a cabo a nivel nacional."),
    "Haití no celebra elecciones desde 2016 y no tiene presidente electo desde el asesinato de Jovenel Moïse en 2021. Un Consejo Presidencial de Transición y una misión internacional de seguridad han intentado crear condiciones para votar, pero las pandillas controlan buena parte de Puerto Príncipe. El mercado apuesta a que la primera vuelta presidencial por fin ocurra en 2026.",
    None)

CONTENT["israel-iran-ataques-directos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si fuerzas regulares de Israel atacan territorio iraní, o fuerzas regulares de Irán atacan territorio israelí (misiles, drones, aviación o fuerzas terrestres), entre el 27 de agosto y el 31 de diciembre de 2026, confirmado por el gobierno atacante, el atacado o ambos. No cuentan ataques de grupos aliados o proxies (Hezbolá, hutíes, milicias iraquíes), ataques contra fuerzas de uno de los dos en terceros países, ciberataques ni operaciones encubiertas no reconocidas.
""", FIN_2026,
        como="se verifica con la confirmación oficial de al menos uno de los dos gobiernos (Fuerzas de Defensa de Israel o gobierno de Irán) y con el reporte de al menos dos agencias internacionales (Reuters, AP, AFP). El equipo de VEREDIKT enlaza las fuentes en los comentarios."),
    "Israel e Irán intercambiaron ataques directos en abril y octubre de 2024 y libraron una guerra de doce días en junio de 2025, con bombardeos israelíes a instalaciones nucleares y andanadas de misiles iraníes contra Israel. Desde entonces rige un alto el fuego frágil. El mercado apuesta a que haya una nueva ronda de ataques directos entre ambos antes de terminar 2026.",
    None)

CONTENT["macron-presidente-fin-2026"] = entry(
    cargo("Emmanuel Macron", "presidente de la República Francesa", "París", FIN_2026, "el registro oficial del Palacio del Elíseo (elysee.fr)"),
    "Emmanuel Macron es presidente de Francia desde 2017 y su segundo mandato termina en mayo de 2027. Tras la disolución fallida de 2024 y una sucesión de gobiernos débiles, la oposición ha pedido su renuncia en varias ocasiones, algo que él ha rechazado. El mercado apuesta a que complete el año 2026 en el Elíseo.",
    "https://www.elysee.fr")

CONTENT["merz-canciller-fin-2026"] = entry(
    cargo("Friedrich Merz", "canciller federal de Alemania", "Berlín", FIN_2026, "el registro oficial de la Cancillería (bundeskanzler.de)"),
    "Friedrich Merz, de la CDU, es canciller de Alemania desde mayo de 2025 al frente de una coalición con el SPD. Fue elegido en segunda votación tras fracasar en la primera, una señal de la fragilidad de su mayoría. Con la AfD como segunda fuerza en las encuestas y tensiones dentro de la coalición, el mercado apuesta a que Merz siga siendo canciller al terminar 2026.",
    "https://www.bundeskanzler.de")

CONTENT["netanyahu-pm-fin-2026"] = entry(
    cargo("Benjamin Netanyahu", "primer ministro de Israel", "Jerusalén", FIN_2026, "el registro oficial de la Oficina del Primer Ministro (gov.il)",
          extra="Si tras la elección del 27 de octubre de 2026 el nuevo gobierno aún no se ha formado y Netanyahu sigue como primer ministro interino o de transición, resuelve SÍ."),
    "Benjamin Netanyahu es el primer ministro con más años en el cargo en la historia de Israel. La elección a la 26.ª Knéset está programada para el 27 de octubre de 2026 y la formación de gobierno en Israel puede tardar semanas o meses, durante los cuales el primer ministro saliente sigue en funciones. El mercado apuesta a que Netanyahu, por elección o por transición, siga siendo primer ministro el 31 de diciembre.",
    "https://www.gov.il/en/departments/prime_ministers_office")

CONTENT["onu-sg-mujer-2027"] = entry(
    binario_rules("""
Resuelve SÍ si la persona que la Asamblea General de la ONU designe formalmente como Secretaria o Secretario General para el periodo que comienza el 1 de enero de 2027 es una mujer. La fuente es la resolución de designación de la Asamblea General, publicada en un.org. Las recomendaciones del Consejo de Seguridad, las nominaciones y las encuestas de opinión (straw polls) no resuelven el mercado. Si la designación no ocurre antes del 31 de diciembre de 2026, el mercado se extiende hasta que ocurra.
""", FIN_2026, anticipado=False),
    "El mandato de António Guterres termina el 31 de diciembre de 2026. En 80 años, los nueve secretarios generales de la ONU han sido hombres, y varios países y organizaciones han pedido que la próxima sea una mujer; entre las candidaturas más mencionadas hay mujeres latinoamericanas, región a la que le correspondería el turno según la rotación informal. El mercado apuesta a que la Asamblea General designe por primera vez a una mujer.",
    "https://www.un.org/sg")

CONTENT["otan-nuevo-miembro-2026"] = entry(
    binario_rules("""
Resuelve SÍ únicamente si el protocolo de adhesión de un nuevo país miembro de la OTAN entra en vigor antes del 31 de diciembre de 2026, es decir, si el país deposita su instrumento de adhesión y la OTAN lo reconoce oficialmente como miembro (nato.int). Invitaciones, firmas de protocolos, ratificaciones parciales o asociaciones especiales no cuentan.
""", FIN_2026),
    "La OTAN tiene 32 miembros desde la adhesión de Suecia en marzo de 2024. Los candidatos declarados son Bosnia y Herzegovina, Georgia y Ucrania, ninguno con una vía rápida de ingreso. El mercado apuesta a que, pese a eso, algún país complete su adhesión formal antes de que termine 2026.",
    "https://www.nato.int")

CONTENT["rusia-ucrania-acuerdo-paz-2026"] = entry(
    binario_rules("""
Resuelve SÍ si existe un documento de acuerdo de paz firmado por representantes autorizados de los gobiernos de Rusia y Ucrania antes del 31 de diciembre de 2026, que ambos gobiernos reconozcan como tal. Un alto el fuego, un memorando de entendimiento, un acuerdo marco negociado por terceros sin firma de ambas partes o un acuerdo firmado por una sola de ellas no cuentan.
""", FIN_2026,
        como="se verifica con los comunicados oficiales de las presidencias de Rusia y Ucrania y con la confirmación de al menos dos agencias internacionales (Reuters, AP, AFP). Los enlaces se publican en los comentarios."),
    "La invasión rusa de Ucrania comenzó en febrero de 2022. Desde 2025 ha habido rondas de negociación con mediación de Estados Unidos y encuentros de alto nivel, pero las posiciones sobre territorio y garantías de seguridad siguen distantes. El mercado apuesta a que antes de terminar 2026 exista un acuerdo de paz formal firmado por ambos gobiernos.",
    None)

CONTENT["rusia-ucrania-altofuego-2026"] = entry(
    binario_rules("""
Resuelve SÍ si entra en vigor antes del 31 de diciembre de 2026 un alto el fuego de alcance nacional entre Rusia y Ucrania, reconocido por ambos gobiernos o por la ONU, que cubra todos los frentes. Treguas breves por festividades, pausas humanitarias locales, altos el fuego parciales (por ejemplo solo energético o marítimo) o anuncios unilaterales no cuentan.
""", FIN_2026,
        como="se verifica con los comunicados oficiales de ambos gobiernos o de la ONU sobre la entrada en vigor del alto el fuego, confirmados por al menos dos agencias internacionales (Reuters, AP, AFP). Los enlaces se publican en los comentarios."),
    "Desde 2025 se han propuesto y anunciado varios altos el fuego entre Rusia y Ucrania (energético, marítimo, por festividades), pero ninguno de alcance nacional y duradero. Este mercado apuesta a que uno de alcance total entre en vigor antes de terminar 2026; el mercado hermano de los 30 días apuesta a que además se sostenga.",
    None)

CONTENT["rusia-ucrania-altofuego-30dias"] = entry(
    binario_rules("""
Resuelve SÍ si un alto el fuego de alcance nacional entre Rusia y Ucrania, reconocido por ambos gobiernos o por la ONU y que entre en vigor antes del 31 de diciembre de 2026, se mantiene durante 30 días consecutivos sin que ninguno de los dos gobiernos lo declare roto ni se reanuden las hostilidades a gran escala, aunque el conteo de 30 días termine en 2027. Violaciones aisladas que ninguno de los dos gobiernos considere el fin del alto el fuego no lo interrumpen. Si no entra en vigor ningún alto el fuego nacional antes del 31 de diciembre de 2026, resuelve NO.
""", FIN_2026, anticipado=False,
        como="se verifica con los comunicados oficiales de ambos gobiernos o de la ONU sobre la entrada en vigor y la vigencia del alto el fuego, y con el seguimiento de al menos dos agencias internacionales (Reuters, AP, AFP) durante los 30 días. Los enlaces se publican en los comentarios."),
    "Un alto el fuego es tan valioso como su duración: en conflictos recientes muchos se rompen en días. Este mercado apuesta a que, si Rusia y Ucrania logran un alto el fuego nacional antes de terminar 2026, este sobreviva al menos 30 días consecutivos, el umbral habitual para considerar que una tregua es sostenible.",
    None)

CONTENT["shutdown-eeuu-24h-2026"] = entry(
    binario_rules("""
Resuelve SÍ si hay una interrupción parcial o total de las operaciones del gobierno federal de Estados Unidos por falta de fondos aprobados (shutdown), de al menos 24 horas continuas, entre el 27 de agosto y el 31 de diciembre de 2026, confirmada oficialmente por la Oficina de Administración de Personal (OPM) o la Oficina de Administración y Presupuesto (OMB). Un lapso de fondos que se resuelva en menos de 24 horas o cierres previos al 27 de agosto no cuentan.
""", FIN_2026),
    "El año fiscal del gobierno federal de Estados Unidos termina el 30 de septiembre, y cada otoño el Congreso debe aprobar presupuestos o resoluciones de continuidad para evitar un cierre. Hubo cierres en 2013, 2018 y 2018-2019 (el más largo, 35 días). Con un Congreso polarizado y elecciones intermedias en noviembre, el mercado apuesta a que haya un cierre de al menos un día antes de fin de año.",
    "https://www.opm.gov")

CONTENT["sudan-altofuego-30dias-2026"] = entry(
    binario_rules("""
Resuelve SÍ si un alto el fuego nacional en Sudán, reconocido por la ONU y que cubra a las principales partes beligerantes (las Fuerzas Armadas Sudanesas y las Fuerzas de Apoyo Rápido), entra en vigor antes del 31 de diciembre de 2026 y se mantiene 30 días consecutivos sin que la ONU o las partes lo declaren roto, aunque el conteo termine en 2027. Treguas locales o humanitarias limitadas a una ciudad o región no cuentan.
""", FIN_2026, anticipado=False,
        como="se verifica con los comunicados oficiales de la ONU (Secretario General, Consejo de Seguridad o misión en Sudán) sobre la entrada en vigor y la vigencia del alto el fuego, y con el seguimiento de al menos dos agencias internacionales durante los 30 días. Los enlaces se publican en los comentarios."),
    "La guerra en Sudán entre el ejército y las Fuerzas de Apoyo Rápido comenzó en abril de 2023 y ha provocado la mayor crisis de desplazamiento del mundo. Varios altos el fuego negociados en Yeda y otras capitales se han roto en días. El mercado apuesta a que antes de terminar 2026 haya uno nacional, reconocido por la ONU, que dure al menos 30 días.",
    None)

CONTENT["takaichi-pm-fin-2026"] = entry(
    cargo("Sanae Takaichi", "primera ministra de Japón", "Tokio", FIN_2026, "el registro oficial de la Oficina del Primer Ministro (kantei.go.jp)"),
    "Sanae Takaichi se convirtió en la primera mujer primera ministra de Japón al asumir el liderazgo del Partido Liberal Democrático. Japón ha tenido una alta rotación de primeros ministros en las últimas décadas y el PLD gobierna sin la mayoría holgada de otros tiempos. El mercado apuesta a que Takaichi siga en el cargo al cerrar 2026.",
    "https://japan.kantei.go.jp")

CONTENT["trump-65-ordenes-ejecutivas-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el conteo del Federal Register de órdenes ejecutivas firmadas por Donald Trump con fecha entre el 1 de enero y el 31 de diciembre de 2026 es de 65 o más. Solo cuentan los documentos clasificados como «Executive Order» con número asignado; los memorandos presidenciales, proclamaciones y directivas de seguridad nacional no cuentan. Se usa el conteo del Federal Register una vez publicadas todas las órdenes del año, aunque la publicación de las últimas se retrase a enero de 2027.
""", FIN_2026),
    "Donald Trump firmó más de 200 órdenes ejecutivas en 2025, su primer año del segundo mandato, un ritmo sin precedentes en décadas. El ritmo suele bajar en el segundo año, cuando muchas prioridades ya se decretaron. El mercado apuesta a si en 2026 llega al menos a 65, una cifra que aún sería alta comparada con presidentes anteriores.",
    "https://www.federalregister.gov/presidential-documents/executive-orders")

CONTENT["trump-aprobacion-gallup-45-2026"] = entry(
    binario_rules("""
Resuelve SÍ si la cifra general de aprobación presidencial («approve») de la última encuesta Gallup de aprobación de Donald Trump publicada en 2026 es igual o mayor a 45%. Se usa la cifra principal de adultos que publica Gallup en su página de seguimiento, no promedios de otros agregadores ni submuestras. Si Gallup no publica ninguna medición en 2026, el mercado se cancela.
""", FIN_2026, anticipado=False),
    "Gallup mide la aprobación presidencial desde la década de 1940 y es la serie de referencia. La aprobación de Trump en su segundo mandato ha oscilado en general por debajo del 45%, con caídas ligadas a la economía y los aranceles. El mercado apuesta a que la última medición de Gallup en 2026 lo tenga en 45% o más.",
    "https://news.gallup.com/poll/203198/presidential-approval-ratings-donald-trump.aspx")

CONTENT["trump-arancel-general-10pct-post-ago"] = entry(
    binario_rules("""
Resuelve SÍ si mediante una orden ejecutiva, proclamación o regulación con efecto legal, emitida entre el 27 de agosto y el 31 de diciembre de 2026 y publicada en el Federal Register, se impone un NUEVO arancel general mínimo de 10% o más a las importaciones de todos o casi todos los países, adicional a los aranceles ya vigentes al 26 de agosto de 2026. Aranceles dirigidos a un país, un sector o un producto específico, aumentos de aranceles existentes o anuncios sin documento con efecto legal no cuentan.
""", FIN_2026),
    "En 2025 Trump impuso un arancel base de 10% a casi todas las importaciones más aranceles «recíprocos» por país, que han sido litigados en tribunales. Este mercado apuesta a que después del 26 de agosto de 2026 se imponga otro arancel general nuevo, de al menos 10%, encima de los vigentes, algo que Trump ha insinuado como respuesta a fallos judiciales o a negociaciones estancadas.",
    "https://www.federalregister.gov")

CONTENT["trump-gabinete-salida-post-ago-2026"] = entry(
    binario_rules("""
Resuelve SÍ si al menos un secretario titular confirmado por el Senado de alguno de los 15 departamentos ejecutivos del gabinete de Trump (Estado, Tesoro, Defensa, Justicia, Interior, Agricultura, Comercio, Trabajo, Salud, Vivienda, Transporte, Energía, Educación, Asuntos de Veteranos y Seguridad Nacional) deja el cargo por renuncia, destitución o fallecimiento entre el 27 de agosto y el 31 de diciembre de 2026. Cuenta desde que la salida es efectiva o anunciada oficialmente con fecha. No cuentan funcionarios interinos, cargos con rango de gabinete que no son secretarios (vicepresidente, jefe de gabinete, directores de agencias) ni salidas previas al 27 de agosto.
""", FIN_2026,
        como="se verifica con el anuncio oficial de la Casa Blanca, del departamento correspondiente o del propio secretario, confirmado por al menos dos agencias internacionales (Reuters, AP, AFP). El enlace se publica en los comentarios."),
    "El primer mandato de Trump tuvo la rotación de gabinete más alta en décadas. En el segundo, los secretarios han sido más estables, aunque varios han enfrentado polémicas. El mercado apuesta a que entre finales de agosto y el cierre de 2026 al menos un secretario titular deje su puesto.",
    None)

CONTENT["trump-ley-insurreccion-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Donald Trump emite antes del 31 de diciembre de 2026 una orden ejecutiva o proclamación, publicada en el Federal Register, que cite expresamente la Insurrection Act (10 U.S.C. §§ 251-255) como autoridad para desplegar fuerzas militares. Amenazas verbales, despliegues de la Guardia Nacional bajo otras autoridades (por ejemplo el Título 10 o el Título 32) o menciones en discursos no cuentan.
""", FIN_2026),
    "La Ley de Insurrección permite al presidente usar al ejército en territorio nacional para sofocar disturbios; no se invoca desde 1992 (disturbios de Los Ángeles). Trump ha amenazado con invocarla en varias ocasiones, y en 2025 desplegó a la Guardia Nacional en ciudades bajo otras autoridades legales. El mercado apuesta a que la invoque formalmente antes de terminar 2026.",
    "https://www.federalregister.gov")

CONTENT["trump-putin-reunion-post-ago-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Donald Trump y Vladímir Putin sostienen una reunión con ambos físicamente presentes en el mismo lugar entre el 27 de agosto y el 31 de diciembre de 2026, confirmada por la Casa Blanca o el Kremlin. Cuenta un encuentro bilateral formal o una reunión al margen de una cumbre. Llamadas telefónicas, videoconferencias, encuentros de delegaciones sin los dos presidentes o reuniones previas al 27 de agosto no cuentan.
""", FIN_2026,
        como="se verifica con la confirmación oficial de la Casa Blanca o del Kremlin y con el reporte de al menos dos agencias internacionales (Reuters, AP, AFP). Los enlaces se publican en los comentarios."),
    "Trump y Putin se reunieron en Alaska en agosto de 2025 para discutir el fin de la guerra en Ucrania, sin acuerdo definitivo, y han hablado por teléfono en varias ocasiones desde entonces. El mercado apuesta a que vuelvan a verse en persona entre finales de agosto y el cierre de 2026, ya sea en una nueva cumbre bilateral o al margen de un foro internacional.",
    None)

CONTENT["trump-veto-2026"] = entry(
    binario_rules("""
Resuelve SÍ si Donald Trump emite al menos un veto presidencial formal (regular o de bolsillo) a un proyecto de ley aprobado por el Congreso entre el 27 de agosto y el 31 de diciembre de 2026, según el registro oficial de vetos del Senado de Estados Unidos. La firma de una ley con declaraciones de objeción (signing statement) o el rechazo de un proyecto que no llegó a su escritorio no cuentan.
""", FIN_2026),
    "Trump vetó diez proyectos de ley en su primer mandato. En el segundo, con un Congreso republicano, los vetos han sido raros porque pocas leyes que él rechace llegan a su escritorio. El mercado apuesta a que entre finales de agosto y el cierre de 2026 emita al menos uno, por ejemplo contra una resolución del Congreso sobre aranceles o poderes de guerra.",
    "https://www.senate.gov/legislative/vetoes/vetoCounts.htm")

CONTENT["uk-eleccion-anticipada-2026"] = entry(
    binario_rules("""
Resuelve SÍ si se publica formalmente la convocatoria a una elección general anticipada del Reino Unido (la proclamación real de disolución del Parlamento y convocatoria de elecciones, publicada en The Gazette) antes del 31 de diciembre de 2026. La elección en sí puede celebrarse en 2027; lo que cuenta es la convocatoria formal. Anuncios de intención, votaciones parlamentarias sin proclamación o elecciones parciales no cuentan.
""", FIN_2026),
    "La última elección general del Reino Unido fue en julio de 2024 y la siguiente no es obligatoria hasta 2029. Un cambio de primer ministro dentro del Partido Laborista, el ascenso de Reform UK en las encuestas y un Parlamento con mayoría laborista pero dividida han alimentado la especulación sobre un adelanto. El mercado apuesta a que la convocatoria formal ocurra antes de terminar 2026.",
    "https://www.thegazette.co.uk")

CONTENT["vonderleyen-ce-fin-2026"] = entry(
    cargo("Ursula von der Leyen", "presidenta de la Comisión Europea", "Bruselas", FIN_2026, "el registro oficial de la Comisión Europea (commission.europa.eu)"),
    "Ursula von der Leyen preside la Comisión Europea desde 2019 y fue reelegida en 2024 para un segundo mandato hasta 2029. En 2025 sobrevivió a una moción de censura en el Parlamento Europeo. El mercado apuesta a que siga al frente de la Comisión al terminar 2026, pese a las tensiones por los acuerdos comerciales con Estados Unidos y las críticas de varios grupos parlamentarios.",
    "https://commission.europa.eu")

CONTENT["zelenski-presidente-fin-2026"] = entry(
    cargo("Volodímir Zelenski", "presidente de Ucrania", "Kiev", FIN_2026, "el registro oficial de la Presidencia de Ucrania (president.gov.ua)"),
    "Volodímir Zelenski es presidente de Ucrania desde 2019. Su mandato de cinco años venció en mayo de 2024, pero la ley marcial vigente por la invasión rusa impide celebrar elecciones, por lo que sigue en el cargo. Un acuerdo de paz podría abrir la puerta a elecciones en 2026. El mercado apuesta a que siga siendo el presidente reconocido oficialmente el 31 de diciembre de 2026.",
    "https://www.president.gov.ua")
