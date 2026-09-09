# seed-markets-2026-09-04-sociedad.py
#
# PLANTILLA PARA SEEDS NUEVOS (desde 2026-09-04): cada dict debe traer, además
# de resolution_criteria, los tres campos del bloque "Criterios | Normas |
# Contexto" del detalle del mercado:
#   "resolution_source_url": URL https de la página oficial que decide (o None),
#   "rules":   Normas (aplazamientos, zona horaria, qué fuente manda; si no hay
#              URL, el primer párrafo empieza con "Cómo se resuelve:"),
#   "context": Contexto del mercado (antecedentes, por qué importa).
# Los 13 mercados de este archivo se cubrieron con el backfill
# backfill-normas-contexto-fuente-2026-09-04.py (paquete market_content/), por
# eso aquí van vacíos; en un seed nuevo van inline en cada dict.
import asyncio, sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr

UTC = timezone.utc

MARKETS = [
    {
        "id": "registro-celular-politico-sin-senal-oct26",
        "question": "¿Un político mexicano conocido reportará que su línea celular fue suspendida por no registrarla con CURP antes del 31 de octubre de 2026?",
        "description": "La CRT ya suspende líneas no vinculadas con CURP según un calendario escalonado por último dígito (0 el 15 ago, 1 el 31 ago, y así hasta diciembre). ¿Algún político de peso caerá en la trampa?",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si antes del 31 de octubre de 2026 (hora CDMX) un titular de cargo federal o estatal de elección popular (presidenta, gobernador, senador, diputado federal o local, alcalde), integrante del gabinete federal o dirigente nacional de partido declara públicamente, o un medio nacional (El Universal, Milenio, Reforma, Excélsior, El Financiero, Proceso, Infobae México) reporta con nombre, que su línea celular fue deshabilitada por no completar el registro CURP de la CRT. Un político hablando del tema en general no cuenta. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2026, 11, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 15.0,
        "trending": False,
    },
    {
        "id": "fatima-bosch-reality-2027",
        "question": "¿Fátima Bosch participará en un reality show mexicano antes de terminar 2027?",
        "description": "Miss Universo 2025 fue invitada públicamente a La Casa de los Famosos México 4 y no entró. Su reinado termina en noviembre de 2026. ¿Acepta un reality en 2027?",
        "category": MarketCategory.ENTRETENIMIENTO,
        "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si antes del 31 de diciembre de 2027 Fátima Bosch aparece como concursante o integrante del elenco (no conductora, no jurado, no invitada de un solo episodio) en un reality o programa de competencia producido para México y transmitido en TV abierta, TV de paga o plataforma de streaming (por ejemplo La Casa de los Famosos México, MasterChef Celebrity, ¿Quién es la máscara?, Exatlón, Survivor México, o un docu reality centrado en ella). Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2028, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
    {
        "id": "ice-perros-robot-contrato-2026",
        "question": "¿ICE formalizará la compra de perros robot antes de terminar 2026?",
        "description": "ICE registró en el sistema de previsión de adquisiciones del DHS una compra de 1 a 2 millones de dólares en robots Spot de Boston Dynamics para inspecciones en operativos migratorios. ¿Pasa de previsión a contrato este año?",
        "category": MarketCategory.GLOBAL,
        "subcategory": "Migración",
        "resolution_criteria": "Resuelve SÍ si antes del 31 de diciembre de 2026 se publica un contrato adjudicado a nombre de ICE por robots cuadrúpedos (en SAM.gov, USAspending.gov o FPDS), o ICE o el DHS confirman oficialmente la compra o entrega de unidades. Una previsión de adquisición, solicitud de información o declaración de intención no cuenta. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
    {
        "id": "sheinbaum-mananera-perros-robot-ice",
        "question": "¿Sheinbaum será cuestionada en una mañanera sobre los perros robot de ICE antes de terminar 2026?",
        "description": "El plan de ICE de comprar perros robot para operativos migratorios se conoció el 28 de agosto de 2026. ¿Llega el tema a la mañanera?",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Sheinbaum",
        "resolution_criteria": "Resuelve SÍ si en la versión estenográfica oficial de una conferencia mañanera (gob.mx/presidencia) celebrada entre el 4 de septiembre y el 31 de diciembre de 2026 un reportero pregunta explícitamente sobre los perros robot o robots cuadrúpedos de ICE, o la presidenta los menciona por iniciativa propia. Preguntas sobre ICE en general, sin mencionar los robots, no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 35.0,
        "trending": False,
    },
    {
        "id": "mexico-perros-robot-federal-2026",
        "question": "¿Una dependencia federal mexicana anunciará la adquisición de perros robot antes de terminar 2026?",
        "description": "El C5 del Estado de México ya presentó su perro robot K7 en la mañanera del 22 de julio de 2026. ¿Da el salto una dependencia federal de seguridad o migración?",
        "category": MarketCategory.MEXICO,
        "subcategory": None,
        "resolution_criteria": "Resuelve SÍ si antes del 31 de diciembre de 2026 la SSPC, la Guardia Nacional, Sedena, Marina, el INM o la Presidencia anuncia oficialmente (comunicado, mañanera o licitación publicada en CompraNet) la compra o incorporación de robots cuadrúpedos para uso operativo. Robots de gobiernos estatales o municipales no cuentan. Demostraciones, pruebas piloto o donaciones sin anuncio de incorporación no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 25.0,
        "trending": False,
    },
    {
        "id": "sheinbaum-grito-2026-menciona-amlo",
        "question": "¿Sheinbaum mencionará a López Obrador durante el Grito del 15 de septiembre de 2026?",
        "description": "En su primer Grito (2025) Sheinbaum dio 22 vivas dedicadas a heroínas, mujeres indígenas y migrantes, sin mencionar a AMLO. ¿Rompe la tradición en 2026?",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Sheinbaum",
        "resolution_criteria": "Resuelve SÍ si durante la arenga del Grito desde el balcón de Palacio Nacional la noche del 15 de septiembre de 2026 (desde el primer 'Mexicanas, mexicanos' hasta el último '¡Viva México!') Sheinbaum pronuncia 'López Obrador', 'Andrés Manuel' o 'AMLO'. Fuente: transmisión oficial y versión estenográfica de Presidencia. Menciones antes o después de la arenga no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2026, 9, 16, 6, 0, 0, tzinfo=UTC),
        "b": 150.0,
        "initial_yes_price": 4.0,
        "trending": True,
    },
    {
        "id": "sheinbaum-grito-2026-pueblos-indigenas",
        "question": "¿Sheinbaum dirá '¡Vivan los pueblos indígenas!' durante el Grito del 15 de septiembre de 2026?",
        "description": "En 2025 la viva fue '¡Vivan las mujeres indígenas!'. ¿Cambia la fórmula a 'pueblos indígenas' en 2026?",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Sheinbaum",
        "resolution_criteria": "Resuelve SÍ si en la arenga desde el balcón de Palacio Nacional la noche del 15 de septiembre de 2026 Sheinbaum pronuncia una viva que contenga textualmente la frase 'pueblos indígenas' (por ejemplo '¡Vivan los pueblos indígenas!' o '¡Vivan los pueblos indígenas de México!'). Las frases 'mujeres indígenas', 'pueblos originarios' o 'comunidades indígenas' NO cuentan. Fuente: transmisión oficial y versión estenográfica de Presidencia. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2026, 9, 16, 6, 0, 0, tzinfo=UTC),
        "b": 150.0,
        "initial_yes_price": 30.0,
        "trending": True,
    },
    {
        "id": "mx-perro-interrumpe-partido-ap26",
        "question": "¿Un perro interrumpirá un partido de Liga MX antes de terminar el Apertura 2026?",
        "description": "Tunita en San Luis (2020) y el tlacuache de Veracruz (2019) son leyenda. ¿Vuelve un perro a detener un partido de Primera División antes de la final de diciembre?",
        "category": MarketCategory.DEPORTES,
        "subcategory": "Liga MX",
        "resolution_criteria": "Resuelve SÍ si en cualquier partido oficial de la Liga MX varonil correspondiente al Apertura 2026 (fase regular o Liguilla, incluida una final recorrida al 24 y 27 de diciembre) un perro entra al terreno de juego y el árbitro detiene el juego estando el balón en juego, confirmado por video de la transmisión y por al menos un medio nacional (ESPN, TUDN, Récord o Mediotiempo). Liga de Expansión y Liga MX Femenil no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2026, 12, 28, 6, 0, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 15.0,
        "trending": False,
    },
    {
        "id": "mx-mascota-incidente-viral-ap26",
        "question": "¿Una mascota de un club de Liga MX protagonizará un incidente en un partido antes de terminar el Apertura 2026?",
        "description": "Golpes, caídas, expulsiones y sanciones a mascotas pasan cada temporada en la Liga MX. ¿Ocurre uno más antes de la final del Apertura 2026?",
        "category": MarketCategory.DEPORTES,
        "subcategory": "Liga MX",
        "resolution_criteria": "Resuelve SÍ si entre el 4 de septiembre de 2026 y el fin del Apertura 2026 la mascota oficial de un club de Liga MX, dentro del estadio en día de partido, protagoniza un altercado físico con jugador, aficionado, árbitro o personal, una caída o lesión, una expulsión o retiro por seguridad, o una sanción de la Liga MX o del propio club, y el hecho es reportado por al menos dos de ESPN México, TUDN, Récord, Mediotiempo o Fox Sports MX. Bailes, memes o burlas sin incidente físico o sanción no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2026, 12, 28, 6, 0, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 35.0,
        "trending": False,
    },
    {
        "id": "influencer-candidatura-2027-anuncio",
        "question": "¿Un influencer mexicano anunciará que buscará una candidatura para 2027 antes de terminar 2026?",
        "description": "Rumbo a las intermedias de 2027 los partidos ya están fichando famosos. ¿Se destapa un creador de contenido nuevo antes de que cierre el año?",
        "category": MarketCategory.POLITICA_MX,
        "subcategory": "Elecciones",
        "resolution_criteria": "Resuelve SÍ si entre el 4 de septiembre y el 31 de diciembre de 2026 un creador de contenido mexicano con 3 millones o más de seguidores en al menos una plataforma, cuya fama provenga principalmente de redes sociales (no actores, cantantes, conductores de TV ni deportistas), anuncia públicamente que buscará una candidatura o precandidatura en las elecciones de 2027, o un partido lo presenta oficialmente como aspirante, reportado por al menos dos medios nacionales. Anuncios hechos antes del 4 de septiembre de 2026 (por ejemplo Mariana Rodríguez) no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 70.0,
        "trending": False,
    },
    {
        "id": "influencers-demanda-tribunales-2026",
        "question": "¿Un influencer mexicano anunciará una demanda o denuncia contra otro influencer antes de terminar 2026?",
        "description": "Los pleitos entre creadores cada vez terminan más seguido en los juzgados. ¿Se anuncia una demanda nueva entre influencers antes de que acabe el año?",
        "category": MarketCategory.ENTRETENIMIENTO,
        "subcategory": "Influencers",
        "resolution_criteria": "Resuelve SÍ si entre el 4 de septiembre y el 31 de diciembre de 2026 un creador de contenido mexicano con 1 millón o más de seguidores anuncia públicamente (video, publicación o entrevista) que presentó o presentará una demanda civil o denuncia penal contra otro creador con 1 millón o más de seguidores, identificándolo, y el anuncio es reportado por al menos dos medios nacionales. Amenazas genéricas de 'acciones legales' sin identificar al demandado no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 75.0,
        "trending": False,
    },
    {
        "id": "emilio-antun-polemica-2026",
        "question": "¿Emilio Antún protagonizará una nueva polémica sentimental pública antes de terminar 2026?",
        "description": "El creador regio admitió en abril de 2026 una infidelidad a Valentina Velasco, desapareció de redes y reapareció en julio. ¿Hay nuevo capítulo antes de diciembre?",
        "category": MarketCategory.ENTRETENIMIENTO,
        "subcategory": "Influencers",
        "resolution_criteria": "Resuelve SÍ si entre el 4 de septiembre y el 31 de diciembre de 2026 al menos tres medios nacionales (Milenio, Excélsior, El Universal, El Financiero, Infobae México, TVNotas o Quién) publican nota sobre un hecho sentimental NUEVO de Emilio Antún: nueva relación confirmada, ruptura, acusación de infidelidad, reconciliación con Valentina Velasco o declaraciones públicas de una expareja sobre él. Notas que solo repasen la infidelidad de abril de 2026 no cuentan. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 100.0,
        "initial_yes_price": 45.0,
        "trending": False,
    },
    {
        "id": "fofo-marquez-libre-2026",
        "question": "¿Fofo Márquez saldrá de prisión antes de terminar 2026?",
        "description": "Sentenciado a 17 años 6 meses por tentativa de feminicidio, con apelación confirmada y la SCJN negándose a atraer su amparo el 29 de junio de 2026. Le queda un amparo directo en el Tribunal Colegiado.",
        "category": MarketCategory.ENTRETENIMIENTO,
        "subcategory": "Influencers",
        "resolution_criteria": "Resuelve SÍ si antes del 31 de diciembre de 2026 Rodolfo 'Fofo' Márquez abandona físicamente el centro penitenciario por cualquier vía (amparo, libertad anticipada, sustitución de pena o arresto domiciliario). Un amparo concedido que ordene reponer el procedimiento sin excarcelación no cuenta. Fuente: Poder Judicial del Estado de México y medios nacionales. Resuelve NO en cualquier otro caso.",
        "ends_at": datetime(2027, 1, 1, 5, 59, 0, tzinfo=UTC),
        "b": 50.0,
        "initial_yes_price": 4.0,
        "trending": False,
    },
]

async def main():
    async with AsyncSessionLocal() as db:
        for d in MARKETS:
            exists = await db.execute(select(Market).where(Market.id == d["id"]))
            if exists.scalar_one_or_none() is not None:
                print(f"  SKIP   {d['id']} (ya existe)")
                continue
            q_yes, q_no = lmsr.init_q_for_price(d["initial_yes_price"] / 100.0, d["b"])
            yp = lmsr.yes_price_pct(q_yes, q_no, d["b"])
            db.add(Market(
                id=d["id"], question=d["question"], description=d["description"],
                category=d["category"], subcategory=d.get("subcategory"),
                resolution_criteria=d["resolution_criteria"],
                resolution_source_url=d.get("resolution_source_url"),
                rules=d.get("rules"), context=d.get("context"),
                ends_at=d["ends_at"], b=d["b"], q_yes=q_yes, q_no=q_no, yes_price=yp,
                volume=0.0, num_trades=0, status=MarketStatus.OPEN,
                trending=d.get("trending", False), market_type="binary",
            ))
            db.add(PriceHistory(market_id=d["id"], yes_price=yp, volume_snapshot=0.0))
            print(f"  INSERT {d['id']}  yes_price={yp}%  b={d['b']}")
        await db.commit()
        print("\nDone.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
