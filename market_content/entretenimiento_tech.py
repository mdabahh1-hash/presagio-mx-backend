"""Normas / Contexto / fuente: Entretenimiento (Influencers, realities) y Tech (IPO, NVIDIA). 7 activos al 2026-09-04."""
from market_content._common import binario_rules, entry

MEDIOS_ESPECTACULOS = "Milenio, Excélsior, El Universal, El Financiero, Infobae México, TVNotas o Quién"

CONTENT: dict[str, dict] = {}

# ── Influencers ───────────────────────────────────────────────────────────
CONTENT["emilio-antun-polemica-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si entre el 4 de septiembre y el 31 de diciembre de 2026 al menos tres de estos medios ({MEDIOS_ESPECTACULOS}) publican una nota sobre un hecho sentimental NUEVO de Emilio Antún: una nueva relación confirmada, una ruptura, una acusación de infidelidad, una reconciliación con Valentina Velasco o declaraciones públicas de una expareja sobre él. Notas que solo repasen la infidelidad de abril de 2026, rumores sin fuente identificada o publicaciones exclusivamente en redes de terceros no cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="no existe una fuente oficial para hechos de la vida privada; el mercado se resuelve por cobertura de prensa, con el umbral de tres medios de la lista publicando sobre el mismo hecho nuevo. El equipo de VEREDIKT enlaza las tres notas en los comentarios al resolver."),
    "Emilio Antún, creador de contenido regiomontano, admitió en abril de 2026 una infidelidad a su pareja Valentina Velasco, desapareció de redes durante semanas y reapareció en julio. Su vida sentimental es tema recurrente en la prensa de espectáculos. El mercado apuesta a que haya un capítulo nuevo antes de que termine 2026.",
    None)

CONTENT["fofo-marquez-libre-2026"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 31 de diciembre de 2026 Rodolfo «Fofo» Márquez abandona físicamente el centro penitenciario en el que cumple su sentencia, por cualquier vía: amparo con efectos de libertad, libertad anticipada, sustitución de la pena, prisión domiciliaria o cualquier otra medida que lo saque del penal. Un amparo concedido que ordene reponer el procedimiento sin excarcelación, un traslado a otro penal o un permiso temporal con retorno no cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="se verifica con los boletines del Poder Judicial del Estado de México o del Poder Judicial de la Federación (tribunal colegiado que resuelva el amparo) y con el reporte de al menos dos medios nacionales que confirmen que salió del penal. Los enlaces se publican en los comentarios."),
    "Fofo Márquez, influencer conocido por sus videos de ostentación, fue sentenciado a 17 años y 6 meses de prisión por tentativa de feminicidio tras golpear a una mujer en Naucalpan en 2024. La apelación confirmó la sentencia y el 29 de junio de 2026 la Suprema Corte se negó a atraer su amparo. Le queda un amparo directo ante el Tribunal Colegiado. El mercado apuesta a que, pese a todo, salga de prisión antes de que termine 2026.",
    None)

CONTENT["influencers-demanda-tribunales-2026"] = entry(
    binario_rules("""
Resuelve SÍ si entre el 4 de septiembre y el 31 de diciembre de 2026 un creador de contenido mexicano con 1 millón o más de seguidores en al menos una plataforma anuncia públicamente (video, publicación o entrevista) que presentó o presentará una demanda civil o una denuncia penal contra otro creador de contenido con 1 millón o más de seguidores, identificándolo por nombre o usuario. Amenazas genéricas de «acciones legales» sin identificar al demandado, demandas contra medios, marcas o exparejas que no sean creadores, y anuncios previos al 4 de septiembre no cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="no hay registro público consultable de demandas por nombre; se resuelve con el anuncio del propio creador y con el reporte de al menos dos medios nacionales. El conteo de seguidores se toma de la plataforma en la fecha del anuncio. Los enlaces se publican en los comentarios."),
    "Los pleitos entre creadores de contenido en México cada vez terminan más seguido en los juzgados: demandas por difamación, por uso de imagen o denuncias penales anunciadas en video se han vuelto parte del ciclo de polémicas. El mercado apuesta a que antes de que termine 2026 se anuncie una demanda nueva entre dos influencers con al menos un millón de seguidores cada uno.",
    None)

# ── Entretenimiento sin subcategoría ──────────────────────────────────────
CONTENT["fatima-bosch-reality-2027"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 31 de diciembre de 2027 Fátima Bosch aparece como concursante o integrante del elenco (no conductora, no jurado, no invitada de un solo episodio) en un reality o programa de competencia producido para México y transmitido en televisión abierta, televisión de paga o una plataforma de streaming, por ejemplo La Casa de los Famosos México, MasterChef Celebrity, ¿Quién es la máscara?, Exatlón, Survivor México o un docu-reality centrado en ella. Cuenta desde que se emite el primer episodio en el que participa; el anuncio de su participación sin emisión no basta.
""", "2028-01-01T05:59:00+00:00",
        como="se verifica con la emisión del programa (la aparición en pantalla como parte del elenco) y con el anuncio oficial de la productora o la cadena, reportados por al menos dos medios nacionales. El enlace se publica en los comentarios."),
    "Fátima Bosch, Miss Universo 2025, fue invitada públicamente a La Casa de los Famosos México 4 y no entró. Su reinado termina en noviembre de 2026, y a partir de entonces queda libre de las restricciones de la organización. Las reinas de belleza mexicanas suelen pasar a la televisión; el mercado apuesta a que Bosch acepte un reality antes de que termine 2027.",
    None)

# ── Tech ──────────────────────────────────────────────────────────────────
CONTENT["nvidia-1000"] = entry(
    binario_rules("""
Resuelve SÍ si el precio de cierre oficial de la acción de NVIDIA (NVDA) en el Nasdaq supera los US$1,000 en cualquier sesión de 2026, según los datos de cierre publicados por nasdaq.com. Solo cuenta el precio de cierre de la sesión regular, no máximos intradía ni operaciones fuera de horario. Si NVIDIA realiza un split de acciones en 2026, el umbral se ajusta proporcionalmente (por ejemplo, US$100 tras un split 10 a 1).
""", "2026-12-31T00:00:00+00:00"),
    "NVIDIA se convirtió en la empresa más valiosa del mundo gracias a la demanda de chips para inteligencia artificial y superó los US$4 billones de capitalización en 2025. Tras el split 10 a 1 de junio de 2024, la acción cotiza en un rango de tres cifras. Un cierre por encima de US$1,000 implicaría multiplicar su valor varias veces respecto a 2025, o depende de que no haya un nuevo split. El mercado apuesta a ese escenario extremo.",
    "https://www.nasdaq.com/market-activity/stocks/nvda")

CONTENT["anthropic-ipo-2026"] = entry(
    binario_rules("""
Resuelve SÍ si las acciones de Anthropic comienzan a cotizar en una bolsa de Estados Unidos (NYSE o Nasdaq) en cualquier momento antes de las 23:59 del 31 de diciembre de 2026, hora del Este, ya sea mediante una oferta pública inicial tradicional, una cotización directa o una fusión con una SPAC. Lo que cuenta es el primer día de cotización, no la presentación del prospecto (S-1) ni el anuncio de la fecha.
""", "2027-01-01T05:00:00+00:00",
        como="se verifica con el comunicado oficial de la empresa o de la bolsa (NYSE o Nasdaq) que confirme el inicio de cotización, reportado por al menos dos agencias o medios financieros (Reuters, Bloomberg, WSJ, CNBC). El enlace se publica en los comentarios."),
    "Anthropic, la empresa creadora de Claude, presentó de forma confidencial su solicitud de IPO a inicios de junio de 2026, y su valuación privada saltó de 380 a 965 mil millones de dólares entre febrero y mayo. Va camino a su primer trimestre con utilidad operativa, mientras SpaceX abrió la fila de salidas a bolsa de empresas tecnológicas y OpenAI también señaló su debut para 2026. El mercado apuesta a que Anthropic cotice antes de fin de año.",
    None)

CONTENT["openai-ipo-2026"] = entry(
    binario_rules("""
Resuelve SÍ si las acciones de OpenAI (o de la entidad con fines de lucro que agrupe su negocio) comienzan a cotizar en una bolsa de Estados Unidos (NYSE o Nasdaq) en cualquier momento antes de las 23:59 del 31 de diciembre de 2026, hora del Este, mediante una oferta pública inicial, una cotización directa o una fusión con una SPAC. Cuenta el primer día de cotización, no la presentación del prospecto ni el anuncio de fecha.
""", "2027-01-01T05:00:00+00:00",
        como="se verifica con el comunicado oficial de la empresa o de la bolsa (NYSE o Nasdaq) que confirme el inicio de cotización, reportado por al menos dos agencias o medios financieros (Reuters, Bloomberg, WSJ, CNBC). El enlace se publica en los comentarios."),
    "OpenAI, la empresa creadora de ChatGPT, anunció planes de salir a bolsa después de que se conociera la solicitud de Anthropic, pero va más atrás en el proceso, en etapa previa a la presentación o confidencial. Levantó 122 mil millones de dólares en marzo de 2026 con una valuación de 852 mil millones y genera cerca de 2 mil millones de ingresos al mes. El mercado apuesta a que logre debutar en bolsa antes de que termine 2026.",
    None)
