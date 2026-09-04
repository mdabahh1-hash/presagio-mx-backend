"""Normas / Contexto / fuente: Economía, Mercados Globales y México. 8 activos al 2026-09-04."""
from market_content._common import FUENTE_CAIDA, binario_rules, entry

BANXICO = "https://www.banxico.org.mx"
INEGI_INPC = "https://www.inegi.org.mx/temas/inpc/"
FED = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
SE = "https://www.gob.mx/se"

CONTENT: dict[str, dict] = {}

# ── Economía ──────────────────────────────────────────────────────────────
CONTENT["banxico-mantiene-tasa-sep26"] = entry(
    binario_rules("""
Resuelve SÍ si el anuncio de política monetaria del Banco de México del 24 de septiembre de 2026 deja la tasa de interés objetivo (tasa de referencia) en 6.50%. Cualquier movimiento, al alza o a la baja y de cualquier magnitud, resuelve NO. La fuente es el comunicado oficial publicado en banxico.org.mx a las 13:00 h de ese día.

Si la Junta de Gobierno pospone la decisión, el mercado se mantiene abierto hasta el nuevo anuncio siempre que ocurra antes del 31 de octubre de 2026; una decisión extraordinaria anterior al 24 de septiembre que mueva la tasa resuelve NO en ese momento.
""", "2026-09-24T18:55:00+00:00", con_hora=True, anticipado=False),
    "Banxico recortó la tasa de referencia hasta 6.50% en marzo de 2026 y desde entonces la ha mantenido en sus últimas tres decisiones; su comunicado señala que será apropiado mantenerla en el nivel actual. La inflación bajó a 3.10% en la primera quincena de julio de 2026, su nivel más bajo desde 2020, lo que reabre el debate sobre nuevos recortes. El mercado apuesta a que la pausa continúe en la decisión del 24 de septiembre.",
    BANXICO)

CONTENT["banxico-recorte-tasa-2026-q3"] = entry(
    binario_rules("""
Resuelve SÍ si el Banco de México anuncia un recorte a la tasa de interés objetivo, de cualquier magnitud, en cualquiera de sus decisiones de política monetaria con fecha entre el 1 de julio y el 30 de septiembre de 2026, incluidas decisiones extraordinarias. La fuente son los comunicados oficiales de las decisiones de política monetaria en banxico.org.mx. Un recorte anunciado en octubre o después resuelve NO.
""", "2026-09-30T23:59:00+00:00"),
    "Banxico cerró su ciclo de recortes con la tasa en 6.50% en la primavera de 2026 y ha mantenido pausa desde entonces. La OCDE revisó a la baja el crecimiento de México a 0.8% para 2026 y la inflación ha bajado hacia el objetivo, dos argumentos para retomar los recortes. El tercer trimestre incluye las decisiones de agosto y del 24 de septiembre; el mercado apuesta a que en alguna de ellas haya recorte.",
    BANXICO)

CONTENT["tmec-extension-16-anos-2026"] = entry(
    binario_rules("""
Resuelve SÍ si los gobiernos de México, Estados Unidos y Canadá confirman oficialmente, antes de las 23:59 del 31 de diciembre de 2026 (hora de la Ciudad de México), la extensión del T-MEC por 16 años adicionales prevista en el artículo 34.7 del tratado. Se requiere la confirmación por escrito de los tres países (comunicados de la Secretaría de Economía, la USTR y Global Affairs Canada, o una declaración conjunta). Declaraciones de intención, acuerdos de dos de los tres países o la mera continuación del tratado bajo revisiones anuales no cuentan.
""", "2027-01-01T05:59:00+00:00"),
    "El T-MEC prevé una revisión conjunta a los seis años de su entrada en vigor. En la revisión del 1 de julio de 2026 Estados Unidos rechazó confirmar la extensión, lo que activó revisiones anuales hasta 2036. El tratado permite acordar la extensión por 16 años en cualquier momento posterior. El mercado apuesta a que los tres países la confirmen antes de que termine 2026.",
    SE)

CONTENT["mexico-inflacion-2026"] = entry(
    binario_rules("""
Resuelve SÍ si la inflación general anual de México, medida por el Índice Nacional de Precios al Consumidor (INPC) de diciembre de 2026 que publica el INEGI en la primera quincena de enero de 2027, es menor a 4.00%. Se usa la variación anual del índice general (no la subyacente ni la quincenal). Un dato de exactamente 4.00% resuelve NO. Revisiones posteriores del INEGI no modifican el mercado.
""", "2027-01-15T00:00:00+00:00", anticipado=False),
    "El objetivo de inflación de Banxico es 3% con un rango de tolerancia de 1 punto, es decir, hasta 4%. Tras el pico de 2022, la inflación bajó gradualmente y a mediados de 2026 rondaba el 3.1%. El mercado apuesta a que la inflación anual de diciembre de 2026, el dato que cierra el año, quede por debajo de 4%.",
    INEGI_INPC)

# ── Mercados Globales ─────────────────────────────────────────────────────
CONTENT["fed-mantiene-tasa-sep26"] = entry(
    binario_rules("""
Resuelve SÍ si el Comité Federal de Mercado Abierto (FOMC) deja el rango objetivo de la tasa de fondos federales sin cambios en su anuncio del 16 de septiembre de 2026. Cualquier cambio en el rango, al alza o a la baja, resuelve NO. La fuente es el comunicado oficial de la Reserva Federal publicado en federalreserve.gov a las 2:00 p.m. hora del Este.

Si la reunión se pospone, el mercado se mantiene abierto hasta el nuevo anuncio dentro de septiembre; una decisión extraordinaria antes del 16 de septiembre que mueva la tasa resuelve NO en ese momento.
""", "2026-09-16T17:55:00+00:00", con_hora=True, anticipado=False),
    "La reunión del FOMC del 15 y 16 de septiembre de 2026 llega con el mercado dividido: los futuros descontaban un alza hasta que un dato débil de empleo de julio y un CPI en línea cambiaron el escenario base a «sin cambios». La división interna del FOMC, con votos disidentes en reuniones recientes, mantiene viva la incertidumbre. El mercado apuesta a que la Fed no mueva la tasa.",
    FED)

# ── México ────────────────────────────────────────────────────────────────
CONTENT["cdmx-interviene-batalla-aura-sep26"] = entry(
    binario_rules("""
Resuelve SÍ si entre el 2 y el 30 de septiembre de 2026 (hora de la Ciudad de México) una autoridad de la Ciudad de México (Gobierno capitalino, Secretaría de Seguridad Ciudadana, una alcaldía, o la autoridad de un espacio público dentro de la ciudad como la UNAM o el INBAL) suspende, cancela, niega el permiso, desaloja o dispersa una batalla de aura convocada públicamente. Recomendaciones, presencia policial sin interrumpir el evento o declaraciones de las autoridades no cuentan. Intervenciones fuera de la Ciudad de México no cuentan.
""", "2026-10-01T05:59:00+00:00",
        como="no hay registro oficial de este tipo de intervenciones; se resuelve con el reporte de al menos dos medios nacionales (El Universal, Milenio, Reforma, Excélsior, Infobae México, Animal Político o La Jornada) que describan la intervención con fecha, lugar y autoridad. Los enlaces se publican en los comentarios."),
    "Las «batallas de aura», encuentros masivos de jóvenes que compiten con poses y gestos para «farmear aura», llenaron Ciudad Universitaria, el Monumento a la Revolución y Bellas Artes en agosto de 2026. La jefa de gobierno Clara Brugada dijo que son bienvenidas mientras sean pacíficas; en Ignacio de la Llave, Veracruz, un ayuntamiento sí frenó una por falta de permiso. El mercado apuesta a que alguna autoridad capitalina intervenga en septiembre.",
    None)

CONTENT["mexico-perros-robot-federal-2026"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 31 de diciembre de 2026 la Secretaría de Seguridad y Protección Ciudadana, la Guardia Nacional, la Sedena, la Marina, el Instituto Nacional de Migración o la Presidencia anuncia oficialmente (comunicado, mañanera o licitación publicada en CompraNet) la compra o incorporación de robots cuadrúpedos para uso operativo. Robots de gobiernos estatales o municipales (como el K7 del Estado de México) no cuentan. Demostraciones, pruebas piloto o donaciones sin anuncio de incorporación no cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="el anuncio puede venir por tres vías: un comunicado oficial de la dependencia, la versión estenográfica de una mañanera (gob.mx/presidencia) o una licitación en CompraNet. El equipo de VEREDIKT enlaza el documento oficial en los comentarios al resolver."),
    "El C5 del Estado de México presentó su perro robot K7 en la mañanera del 22 de julio de 2026, y semanas después se conoció el plan de ICE de comprar robots Spot para operativos migratorios en Estados Unidos. El mercado apuesta a que una dependencia federal mexicana de seguridad o migración dé el paso de anunciar su propia compra antes de que termine 2026.",
    None)

CONTENT["gobierno-reconoce-batallas-aura-2026"] = entry(
    binario_rules("""
Resuelve SÍ si a más tardar el 31 de diciembre de 2026 (hora de la Ciudad de México) una dependencia del Gobierno federal (Presidencia, Secretaría de Cultura, CONADE, SEP, IMJUVE u otra) emite un documento oficial (decreto, acuerdo, convocatoria, programa o comunicado oficial) que organice, registre o reconozca las batallas de aura como disciplina, actividad cultural o competencia oficial. Declaraciones verbales en conferencia, actos de gobiernos estatales o municipales y eventos privados no cuentan.
""", "2027-01-01T05:59:00+00:00",
        como="el documento aparecería en el Diario Oficial de la Federación o en el portal oficial de la dependencia (gob.mx). El equipo de VEREDIKT verifica que sea un documento oficial federal, no una declaración, y lo enlaza en los comentarios."),
    "Hasta el arranque de septiembre de 2026 las batallas de aura solo habían recibido declaraciones de tolerancia, como la de Clara Brugada en la Ciudad de México; no existe ningún programa, convocatoria ni registro oficial federal. El mercado apuesta a que el Gobierno federal las formalice de alguna manera, como ocurrió en su momento con otras expresiones juveniles absorbidas por la política cultural.",
    None)
