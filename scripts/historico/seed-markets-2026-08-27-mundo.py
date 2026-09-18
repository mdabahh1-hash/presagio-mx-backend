"""
Seed script: 65 mercados BINARIOS (sí/no) — clima MX, cripto, política mundial, EEUU,
geopolítica, Trump, Israel y elecciones mundiales (agosto 2026).

Mirrors app/services/seed.py (convención binaria: SELECT previo, init_q_for_price, PriceHistory).
Run from the backend directory (prod):
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python seed-markets-2026-08-27-mundo.py'

Regla general de plazo: si la condición no ocurre antes del cierre indicado, resuelve NO
(se anexa a cada resolution_criteria que no la traiga ya implícita).
Resolución: manual vía endpoint admin de resolución.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr

B = 100.0
PLAZO = " Si la condición no ocurre antes del cierre indicado, resuelve NO."

# (id, question, category, subcategory, ends_at_iso, initial_yes_price, trending, resolution_criteria)
MARKETS = [
    # ---------- CLIMA MÉXICO ----------
    ("clima-dos-ciclones-tierra-2026", "¿Dos o más ciclones con nombre tocarán tierra en México entre el 27 de agosto y el 30 de noviembre de 2026?",
     MarketCategory.CLIMA, None, "2026-11-30T23:59:00Z", 80.0, True,
     "Resuelve SÍ si el SMN o el NHC confirman al menos dos ciclones tropicales con nombre cuyo centro cruce la costa mexicana entre el 27 de agosto y el 30 de noviembre de 2026."),
    ("clima-huracan-cat3-mexico-2026", "¿Un huracán categoría 3 o superior tocará tierra en México antes de terminar la temporada 2026?",
     MarketCategory.CLIMA, None, "2026-11-30T23:59:00Z", 55.0, True,
     "Resuelve SÍ si un huracán con categoría 3 o superior al momento del impacto, según SMN o NHC, toca tierra en México antes del 30 de noviembre de 2026."),
    ("clima-sequia-20pct-dic-2026", "¿Al menos 20% del territorio mexicano estará en sequía D1-D4 al terminar 2026?",
     MarketCategory.CLIMA, None, "2026-12-31T23:59:00Z", 80.0, False,
     "Resuelve SÍ si el último Monitor de Sequía de México de Conagua-SMN con fecha de corte en diciembre de 2026 registra 20% o más del territorio nacional en categorías D1 a D4."),
    ("clima-temp-sobre-normal-sep-dic-2026", "¿La temperatura media nacional superará la normal 1991-2020 en al menos tres meses entre septiembre y diciembre de 2026?",
     MarketCategory.CLIMA, None, "2026-12-31T23:59:00Z", 88.0, False,
     "Resuelve SÍ si los resúmenes mensuales del SMN registran temperatura media nacional por encima de la normal 1991-2020 en al menos 3 de los 4 meses de septiembre a diciembre de 2026. Cierra la operación el 31 dic; resuelve cuando el SMN publique el resumen de diciembre."),

    # ---------- CRIPTO ----------
    ("btc-cierre-100k-2026", "¿Bitcoin cerrará 2026 en US$100,000 o más?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 20.0, True,
     "Resuelve SÍ si la referencia CME CF Bitcoin Reference Rate del 31 de diciembre de 2026 es igual o mayor a US$100,000."),
    ("btc-toca-120k-2026", "¿Bitcoin alcanzará US$120,000 en algún momento entre el 27 de agosto y el 31 de diciembre de 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 10.0, True,
     "Resuelve SÍ si el índice CME CF de Bitcoin registra al menos US$120,000 en cualquier momento entre el 27 de agosto y el 31 de diciembre de 2026."),
    ("btc-cierre-diario-60k-2026", "¿Bitcoin tendrá un cierre diario inferior a US$60,000 antes del 31 de diciembre de 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 20.0, False,
     "Resuelve SÍ si cualquier referencia diaria CME CF de Bitcoin desde el 27 de agosto de 2026 es inferior a US$60,000."),
    ("eth-cierre-3000-2026", "¿Ethereum cerrará 2026 en US$3,000 o más?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 30.0, False,
     "Resuelve SÍ si la referencia diaria CME CF de Ethereum del 31 de diciembre de 2026 es igual o mayor a US$3,000."),
    ("sol-cierre-150-2026", "¿Solana cerrará 2026 en US$150 o más?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 25.0, False,
     "Resuelve SÍ si la referencia diaria CME CF de Solana del 31 de diciembre de 2026 es igual o mayor a US$150."),
    ("cripto-cap-4t-2026", "¿La capitalización total del mercado cripto superará US$4 billones entre el 27 de agosto y el final de 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 8.0, False,
     "Resuelve SÍ si CoinGecko registra una capitalización total del mercado cripto de al menos US$4 trillion (US$4 billones en español) en cualquier momento entre el 27 de agosto y el 31 de diciembre de 2026."),
    ("btc-dominancia-60-2026", "¿La dominancia de Bitcoin será de 60% o más al cierre de 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 50.0, False,
     "Resuelve SÍ si el dato de dominancia de Bitcoin de CoinGecko del 31 de diciembre de 2026 a las 23:59 UTC es igual o mayor a 60%."),
    ("stablecoins-350b-2026", "¿La capitalización de stablecoins alcanzará US$350,000 millones antes de terminar 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 45.0, False,
     "Resuelve SÍ si el dato agregado de capitalización de stablecoins publicado por DefiLlama alcanza US$350,000 millones en cualquier momento antes del 31 de diciembre de 2026."),
    ("cinco-criptos-100b-2026", "¿Cinco o más criptomonedas tendrán capitalización superior a US$100,000 millones al cierre de 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 15.0, False,
     "Resuelve SÍ si la clasificación de CoinGecko del 31 de diciembre de 2026, excluyendo stablecoins, muestra al menos cinco criptomonedas con capitalización superior a US$100,000 millones."),
    ("eeuu-compra-bitcoin-2026", "¿EEUU adquirirá Bitcoin para su reserva mediante una compra que no provenga de decomisos antes del final de 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 10.0, True,
     "Resuelve SÍ si hay anuncio oficial del Tesoro o la Casa Blanca y una compra ejecutada de Bitcoin para la reserva estratégica que no provenga de activos decomisados, antes del 31 de diciembre de 2026."),
    ("ley-estructura-mercado-cripto-2026", "¿Trump firmará una ley federal de estructura integral del mercado cripto en 2026?",
     MarketCategory.CRYPTO, None, "2026-12-31T23:59:00Z", 45.0, True,
     "Resuelve SÍ si el presidente de EEUU firma antes del 31 de diciembre de 2026 una ley federal que regule de forma sustancial la jurisdicción de SEC y CFTC sobre activos digitales."),

    # ---------- POLÍTICA MUNDIAL ----------
    ("burnham-pm-fin-2026", "¿Andy Burnham seguirá siendo primer ministro del Reino Unido al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 93.0, True,
     "Resuelve SÍ si Andy Burnham ostenta oficialmente el cargo de primer ministro del Reino Unido a las 23:59 de Londres del 31 de diciembre de 2026."),
    ("uk-eleccion-anticipada-2026", "¿El Reino Unido convocará una elección general anticipada antes del final de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 4.0, False,
     "Resuelve SÍ si se publica formalmente la convocatoria a una elección general anticipada del Reino Unido antes del 31 de diciembre de 2026."),
    ("macron-presidente-fin-2026", "¿Emmanuel Macron seguirá siendo presidente de Francia al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 92.0, False,
     "Resuelve SÍ si el registro oficial del Palacio del Elíseo muestra a Emmanuel Macron como presidente de Francia el 31 de diciembre de 2026."),
    ("francia-disolucion-asamblea-2026", "¿Francia disolverá nuevamente su Asamblea Nacional antes del 31 de diciembre de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 20.0, False,
     "Resuelve SÍ si se publica un decreto oficial de disolución de la Asamblea Nacional francesa emitido después del 26 de agosto y antes del 31 de diciembre de 2026."),
    ("merz-canciller-fin-2026", "¿Friedrich Merz seguirá siendo canciller de Alemania al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 90.0, False,
     "Resuelve SÍ si Friedrich Merz es el canciller en funciones de Alemania a las 23:59 hora local del 31 de diciembre de 2026."),
    ("takaichi-pm-fin-2026", "¿Sanae Takaichi seguirá siendo primera ministra de Japón al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 85.0, False,
     "Resuelve SÍ si Sanae Takaichi ostenta el cargo oficial de primera ministra de Japón a las 23:59 hora local del 31 de diciembre de 2026."),
    ("carney-pm-fin-2026", "¿Mark Carney seguirá siendo primer ministro de Canadá al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 95.0, False,
     "Resuelve SÍ si Mark Carney ostenta el cargo oficial de primer ministro de Canadá a las 23:59 de Ottawa del 31 de diciembre de 2026."),
    ("zelenski-presidente-fin-2026", "¿Volodímir Zelenski seguirá siendo presidente de Ucrania al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 90.0, False,
     "Resuelve SÍ si Volodímir Zelenski es el presidente reconocido oficialmente por Ucrania el 31 de diciembre de 2026."),
    ("vonderleyen-ce-fin-2026", "¿Ursula von der Leyen seguirá presidiendo la Comisión Europea al terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 93.0, False,
     "Resuelve SÍ si Ursula von der Leyen es la presidenta en funciones de la Comisión Europea el 31 de diciembre de 2026."),
    ("onu-sg-mujer-2027", "¿La persona seleccionada como próximo secretario general de la ONU será una mujer?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 55.0, True,
     "Resuelve SÍ si la persona designada por la Asamblea General de la ONU como secretaria general para el periodo que comienza en 2027 es una mujer. Si la designación no ocurre antes del 31 de diciembre de 2026, el mercado se extiende hasta la designación oficial."),

    # ---------- ESTADOS UNIDOS ----------
    ("demos-camara-congreso-120", "¿Los demócratas controlarán la Cámara de Representantes en el 120.º Congreso?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 75.0, True,
     "Resuelve SÍ si, con el resultado certificado de las elecciones del 3 de noviembre de 2026, los demócratas tienen la mayoría de escaños de la Cámara de Representantes al instalarse el 120.º Congreso el 3 de enero de 2027."),
    ("republicanos-senado-congreso-120", "¿Los republicanos conservarán el control del Senado de EEUU?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 80.0, True,
     "Resuelve SÍ si los republicanos controlan el Senado al instalarse el 120.º Congreso, contando a los independientes según el partido con el que se agrupen."),
    ("demos-voto-popular-camara-2026", "¿Los demócratas obtendrán la mayoría del voto popular nacional para la Cámara en 2026?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 80.0, False,
     "Resuelve SÍ si la suma oficial de votos emitidos en los 435 distritos de la Cámara en las elecciones de noviembre de 2026 da más votos a candidatos demócratas que a los de cualquier otro partido."),
    ("demos-ganancia-20-escanos-2026", "¿Los demócratas lograrán una ganancia neta de 20 o más escaños en la Cámara?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 40.0, False,
     "Resuelve SÍ si la comparación entre la composición inicial del 119.º y del 120.º Congreso muestra una ganancia neta demócrata de 20 o más escaños en la Cámara de Representantes."),
    ("republicanos-52-senadores-2027", "¿Los republicanos tendrán al menos 52 senadores al iniciar el 120.º Congreso?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 65.0, False,
     "Resuelve SÍ si los republicanos cuentan con al menos 52 senadores electos y en funciones el 3 de enero de 2027."),
    ("control-unificado-congreso-2027", "¿Un solo partido controlará simultáneamente la Cámara y el Senado después de las elecciones de 2026?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 35.0, False,
     "Resuelve SÍ si el mismo partido, republicano o demócrata, controla ambas cámaras del Congreso al instalarse el 120.º Congreso el 3 de enero de 2027."),
    ("california-gobernador-demo-2026", "¿California elegirá a un gobernador demócrata en 2026?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 95.0, False,
     "Resuelve SÍ si el resultado oficial certificado por el estado de California da el triunfo en la elección de gobernador de 2026 a la candidatura demócrata."),
    ("texas-gobernador-rep-2026", "¿Texas elegirá a un gobernador republicano en 2026?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 90.0, False,
     "Resuelve SÍ si el resultado oficial certificado por el estado de Texas da el triunfo en la elección de gobernador de 2026 a la candidatura republicana."),
    ("florida-gobernador-rep-2026", "¿Florida elegirá a un gobernador republicano en 2026?",
     MarketCategory.GLOBAL, None, "2026-11-03T12:00:00Z", 85.0, False,
     "Resuelve SÍ si el resultado oficial certificado por el estado de Florida da el triunfo en la elección de gobernador de 2026 a la candidatura republicana."),
    ("shutdown-eeuu-24h-2026", "¿Habrá un cierre del gobierno federal de EEUU de al menos 24 horas entre el 27 de agosto y el 31 de diciembre de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 55.0, True,
     "Resuelve SÍ si hay confirmación oficial de una interrupción parcial o total del gobierno federal de EEUU por falta de fondos, de al menos 24 horas continuas, entre el 27 de agosto y el 31 de diciembre de 2026. Cierres previos al 27 de agosto de 2026 no cuentan."),

    # ---------- GEOPOLÍTICA ----------
    ("rusia-ucrania-altofuego-2026", "¿Entrará en vigor un alto el fuego nacional entre Rusia y Ucrania antes de terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 12.0, True,
     "Resuelve SÍ si entra en vigor antes del 31 de diciembre de 2026 un alto el fuego de alcance nacional reconocido por ambos gobiernos o por la ONU. Treguas breves por festividades no cuentan como alto el fuego nacional."),
    ("rusia-ucrania-altofuego-30dias", "¿Un alto el fuego nacional Rusia-Ucrania permanecerá vigente 30 días consecutivos?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 7.0, False,
     "Resuelve SÍ si un alto el fuego nacional entre Rusia y Ucrania que entre en vigor antes del 31 de diciembre de 2026 se mantiene 30 días consecutivos, aunque el conteo termine en 2027. Si no entra en vigor ningún alto el fuego nacional antes de esa fecha, resuelve NO."),
    ("rusia-ucrania-acuerdo-paz-2026", "¿Rusia y Ucrania firmarán un acuerdo formal de paz antes del final de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 5.0, False,
     "Resuelve SÍ si existe un documento de acuerdo de paz firmado por los gobiernos de Rusia y Ucrania antes del 31 de diciembre de 2026."),
    ("eeuu-iran-acuerdo-nuclear-2026", "¿EEUU e Irán firmarán un nuevo acuerdo nuclear antes del 31 de diciembre de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 8.0, False,
     "Resuelve SÍ si EEUU e Irán firman antes del 31 de diciembre de 2026 un documento bilateral o multilateral vinculante sobre el programa nuclear iraní."),
    ("corea-norte-prueba-nuclear-2026", "¿Corea del Norte realizará una prueba nuclear antes del final de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 8.0, False,
     "Resuelve SÍ si CTBTO, la ONU o los gobiernos de Corea del Sur o EEUU confirman una prueba nuclear norcoreana antes del 31 de diciembre de 2026."),
    ("china-taiwan-fuego-real-24nm-2026", "¿China realizará ejercicios con fuego real dentro de las 24 millas náuticas de la isla principal de Taiwán antes de terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 20.0, False,
     "Resuelve SÍ si China, Taiwán o ambas partes confirman oficialmente ejercicios militares chinos con fuego real dentro de las 24 millas náuticas de la isla principal de Taiwán entre el 27 de agosto y el 31 de diciembre de 2026."),
    ("otan-nuevo-miembro-2026", "¿La OTAN incorporará un nuevo país miembro antes del final de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 3.0, False,
     "Resuelve SÍ únicamente si el protocolo de adhesión de un nuevo país miembro de la OTAN entra en vigor antes del 31 de diciembre de 2026."),
    ("armenia-azerbaiyan-tratado-2026", "¿El tratado de paz entre Armenia y Azerbaiyán será ratificado y entrará en vigor en 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 30.0, False,
     "Resuelve SÍ si el tratado de paz entre Armenia y Azerbaiyán es ratificado formalmente por ambos países y entra en vigor antes del 31 de diciembre de 2026."),
    ("sudan-altofuego-30dias-2026", "¿Sudán tendrá un alto el fuego nacional reconocido por la ONU durante 30 días consecutivos en 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 10.0, False,
     "Resuelve SÍ si un alto el fuego nacional en Sudán, reconocido por la ONU y que cubra a las principales partes beligerantes, se mantiene 30 días consecutivos con inicio antes del 31 de diciembre de 2026."),
    ("israel-iran-ataques-directos-2026", "¿Israel e Irán realizarán nuevos ataques militares directos entre sí después del 26 de agosto de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 30.0, True,
     "Resuelve SÍ si fuerzas regulares de Israel atacan territorio iraní o fuerzas regulares de Irán atacan territorio israelí después del 26 de agosto y antes del 31 de diciembre de 2026. No cuentan ataques de grupos aliados o proxies."),

    # ---------- TRUMP ----------
    ("trump-65-ordenes-ejecutivas-2026", "¿Trump firmará 65 o más órdenes ejecutivas durante todo 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 85.0, False,
     "Resuelve SÍ si el conteo final del Federal Register de órdenes ejecutivas firmadas por Donald Trump entre el 1 de enero y el 31 de diciembre de 2026 es de 65 o más."),
    ("trump-veto-2026", "¿Trump vetará al menos un proyecto de ley después del 26 de agosto y antes de terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 12.0, False,
     "Resuelve SÍ si Trump emite al menos un veto presidencial formal devuelto al Congreso entre el 27 de agosto y el 31 de diciembre de 2026."),
    ("trump-gabinete-salida-post-ago-2026", "¿Al menos un secretario titular del gabinete de Trump dejará su cargo después del 26 de agosto y antes del final de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 60.0, True,
     "Resuelve SÍ si al menos un secretario titular confirmado del gabinete de Trump deja el cargo por renuncia, destitución o fallecimiento entre el 27 de agosto y el 31 de diciembre de 2026. No cuentan funcionarios interinos ni salidas previas al 27 de agosto."),
    ("trump-putin-reunion-post-ago-2026", "¿Trump y Putin se reunirán personalmente después del 26 de agosto y antes de terminar 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 25.0, True,
     "Resuelve SÍ si Trump y Putin sostienen una reunión confirmada con ambos físicamente presentes entre el 27 de agosto y el 31 de diciembre de 2026. Reuniones previas al 27 de agosto no cuentan."),
    ("trump-ley-insurreccion-2026", "¿Trump invocará formalmente la Ley de Insurrección antes del final de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 22.0, True,
     "Resuelve SÍ si Trump emite antes del 31 de diciembre de 2026 una orden o proclamación que cite expresamente la Insurrection Act. Amenazas verbales o despliegues bajo otras autoridades no cuentan."),
    ("trump-aprobacion-gallup-45-2026", "¿La aprobación de Trump será de 45% o más en la última medición Gallup publicada en 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 10.0, False,
     "Resuelve SÍ si la cifra general de aprobación presidencial de la última encuesta Gallup publicada en 2026 es igual o mayor a 45%."),
    ("trump-arancel-general-10pct-post-ago", "¿Trump impondrá después del 26 de agosto un nuevo arancel general mínimo de 10% a importaciones de todos o casi todos los países?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 12.0, False,
     "Resuelve SÍ si mediante orden, proclamación o regulación efectiva emitida entre el 27 de agosto y el 31 de diciembre de 2026 se impone un NUEVO arancel general mínimo de 10% a importaciones de todos o casi todos los países, adicional a los aranceles ya vigentes al 26 de agosto de 2026."),

    # ---------- ISRAEL ----------
    ("likud-mas-escanos-2026", "¿Likud obtendrá más escaños que cualquier otro partido en la elección israelí del 27 de octubre de 2026?",
     MarketCategory.GLOBAL, None, "2026-10-27T05:00:00Z", 55.0, True,
     "Resuelve SÍ si el resultado oficial definitivo de la elección a la 26.ª Knéset da a Likud más escaños que a cualquier otro partido individual. Un empate en el primer lugar resuelve NO."),
    ("likud-aliados-61-escanos-2026", "¿Likud y sus aliados declarados alcanzarán al menos 61 escaños en la 26.ª Knéset?",
     MarketCategory.GLOBAL, None, "2026-10-27T05:00:00Z", 30.0, True,
     "Resuelve SÍ si Likud y los partidos cuya afiliación de coalición con Likud haya sido anunciada antes de la elección suman al menos 61 de los 120 escaños en el resultado oficial definitivo."),
    ("israel-participacion-70-2026", "¿La participación en la elección israelí de 2026 será de 70% o más?",
     MarketCategory.GLOBAL, None, "2026-10-27T05:00:00Z", 60.0, False,
     "Resuelve SÍ si el porcentaje oficial de participación publicado por la Comisión Electoral Central de Israel para la elección del 27 de octubre de 2026 es igual o mayor a 70%."),
    ("netanyahu-pm-fin-2026", "¿Benjamin Netanyahu seguirá siendo primer ministro de Israel el 31 de diciembre de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 75.0, True,
     "Resuelve SÍ si Netanyahu conserva el cargo de primer ministro el 31 de diciembre de 2026, incluso como primer ministro interino o de transición mientras se forma un nuevo gobierno."),

    # ---------- ELECCIONES MUNDIALES ----------
    ("suecia-sap-mas-votos-2026", "¿El Partido Socialdemócrata obtendrá la mayor cantidad de votos en la elección de Suecia?",
     MarketCategory.GLOBAL, None, "2026-09-13T06:00:00Z", 90.0, False,
     "Resuelve SÍ si el resultado nacional oficial de la elección al Riksdag del 13 de septiembre de 2026 da al Partido Socialdemócrata más votos que a cualquier otro partido."),
    ("lula-gana-brasil-2026", "¿Lula da Silva ganará la elección presidencial de Brasil de 2026?",
     MarketCategory.GLOBAL, None, "2026-10-25T11:00:00Z", 60.0, True,
     "Resuelve SÍ si Lula da Silva es proclamado presidente electo de Brasil por el TSE, en primera o segunda vuelta. Si gana en primera vuelta, el mercado se resuelve anticipadamente."),
    ("brasil-segunda-vuelta-2026", "¿La elección presidencial de Brasil necesitará segunda vuelta?",
     MarketCategory.GLOBAL, None, "2026-10-04T11:00:00Z", 70.0, True,
     "Resuelve SÍ si ningún candidato cumple el 4 de octubre de 2026 el requisito de mayoría absoluta de votos válidos para ganar en primera vuelta, según el resultado oficial del TSE."),
    ("nz-national-mas-votos-2026", "¿El Partido Nacional obtendrá más voto partidario que cualquier otro partido en Nueva Zelanda?",
     MarketCategory.GLOBAL, None, "2026-11-06T20:00:00Z", 45.0, False,
     "Resuelve SÍ si el party vote oficial de la elección general neozelandesa del 7 de noviembre de 2026 da al Partido Nacional más votos que a cualquier otro partido."),
    ("nz-bloque-derecha-mayoria-2026", "¿El bloque National-ACT-New Zealand First conservará una mayoría parlamentaria en Nueva Zelanda?",
     MarketCategory.GLOBAL, None, "2026-11-06T20:00:00Z", 35.0, False,
     "Resuelve SÍ si National, ACT y New Zealand First suman al menos 50% más uno de los escaños definitivos del nuevo Parlamento neozelandés."),
    ("marruecos-rni-mas-escanos-2026", "¿El RNI obtendrá más escaños que cualquier otro partido en las elecciones de Marruecos?",
     MarketCategory.GLOBAL, None, "2026-09-23T07:00:00Z", 50.0, False,
     "Resuelve SÍ si el resultado oficial de la elección legislativa marroquí del 23 de septiembre de 2026 da al RNI más escaños que a cualquier otro partido."),
    ("letonia-nueva-unidad-2026", "¿Nueva Unidad obtendrá más escaños que cualquier otro partido en Letonia?",
     MarketCategory.GLOBAL, None, "2026-10-03T04:00:00Z", 55.0, False,
     "Resuelve SÍ si el resultado oficial de la elección parlamentaria letona de 2026 da a Nueva Unidad más escaños que a cualquier otro partido."),
    ("bulgaria-gerb-presidencia-2026", "¿Un candidato apoyado formalmente por GERB ganará la presidencia de Bulgaria?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 40.0, False,
     "Resuelve SÍ si gana la elección presidencial búlgara de 2026 un candidato cuyo apoyo formal por parte de GERB haya sido anunciado antes de la primera vuelta. AJUSTAR ends_at a la fecha oficial de la primera vuelta cuando se confirme (prevista para otoño de 2026)."),
    ("haiti-primera-vuelta-2026", "¿Haití celebrará la primera vuelta de sus elecciones presidenciales antes del 31 de diciembre de 2026?",
     MarketCategory.GLOBAL, None, "2026-12-31T23:59:00Z", 25.0, False,
     "Resuelve SÍ si la votación nacional de primera vuelta presidencial de Haití ocurre antes del 31 de diciembre de 2026. Un aplazamiento más allá de 2026 resuelve NO."),
]

# Descripción neutra por mercado: qué se pregunta y qué fuente resuelve (sin cifras ajenas a la tupla).
DESCRIPTIONS = {
    "clima-dos-ciclones-tierra-2026": "Pregunta si al menos dos ciclones tropicales con nombre cruzarán la costa mexicana en lo que resta de la temporada 2026. Resuelve con las confirmaciones del SMN o del NHC.",
    "clima-huracan-cat3-mexico-2026": "Pregunta si un huracán mayor (categoría 3 o superior al impacto) tocará tierra en México antes del cierre de la temporada el 30 de noviembre. Resuelve con la clasificación del SMN o del NHC.",
    "clima-sequia-20pct-dic-2026": "Pregunta si la sequía en categorías D1 a D4 cubrirá al menos 20% del territorio nacional al cierre de 2026. Resuelve con el último Monitor de Sequía de México de Conagua-SMN con corte en diciembre.",
    "clima-temp-sobre-normal-sep-dic-2026": "Pregunta si la temperatura media nacional estará por encima de la normal 1991-2020 en al menos tres de los cuatro meses de septiembre a diciembre de 2026. Resuelve con los resúmenes mensuales del SMN.",
    "btc-cierre-100k-2026": "Pregunta si Bitcoin terminará 2026 en o por encima de US$100,000. Resuelve con la CME CF Bitcoin Reference Rate del 31 de diciembre de 2026.",
    "btc-toca-120k-2026": "Pregunta si Bitcoin tocará US$120,000 en cualquier momento entre el 27 de agosto y el cierre de 2026. Resuelve con el índice CME CF de Bitcoin.",
    "btc-cierre-diario-60k-2026": "Pregunta si Bitcoin registrará algún cierre diario por debajo de US$60,000 antes del cierre de 2026. Resuelve con las referencias diarias CME CF de Bitcoin desde el 27 de agosto.",
    "eth-cierre-3000-2026": "Pregunta si Ethereum terminará 2026 en o por encima de US$3,000. Resuelve con la referencia diaria CME CF de Ethereum del 31 de diciembre de 2026.",
    "sol-cierre-150-2026": "Pregunta si Solana terminará 2026 en o por encima de US$150. Resuelve con la referencia diaria CME CF de Solana del 31 de diciembre de 2026.",
    "cripto-cap-4t-2026": "Pregunta si la capitalización total del mercado cripto alcanzará US$4 billones (4 trillion en inglés) en cualquier momento entre el 27 de agosto y el cierre de 2026. Resuelve con los datos de CoinGecko.",
    "btc-dominancia-60-2026": "Pregunta si la participación de Bitcoin en la capitalización total del mercado cripto será de 60% o más al cierre de 2026. Resuelve con el dato de dominancia de CoinGecko del 31 de diciembre a las 23:59 UTC.",
    "stablecoins-350b-2026": "Pregunta si la capitalización agregada de stablecoins tocará US$350,000 millones antes del cierre de 2026. Resuelve con el dato agregado publicado por DefiLlama.",
    "cinco-criptos-100b-2026": "Pregunta si al cierre de 2026 habrá al menos cinco criptomonedas, sin contar stablecoins, con capitalización superior a US$100,000 millones. Resuelve con la clasificación de CoinGecko del 31 de diciembre.",
    "eeuu-compra-bitcoin-2026": "Pregunta si el gobierno de EEUU comprará Bitcoin para su reserva estratégica con fondos distintos a activos decomisados antes del cierre de 2026. Resuelve con anuncios oficiales del Tesoro o la Casa Blanca y una compra ejecutada.",
    "ley-estructura-mercado-cripto-2026": "Pregunta si en 2026 se firmará una ley federal de estructura del mercado cripto que defina de forma sustancial la jurisdicción de SEC y CFTC sobre activos digitales. Resuelve con la firma presidencial antes del 31 de diciembre.",
    "burnham-pm-fin-2026": "Pregunta si Andy Burnham conservará el cargo de primer ministro del Reino Unido al terminar 2026. Resuelve con el registro oficial del cargo a las 23:59 de Londres del 31 de diciembre.",
    "uk-eleccion-anticipada-2026": "Pregunta si el Reino Unido convocará formalmente una elección general anticipada antes del cierre de 2026. Resuelve con la publicación oficial de la convocatoria.",
    "macron-presidente-fin-2026": "Pregunta si Emmanuel Macron seguirá siendo presidente de Francia al terminar 2026. Resuelve con el registro oficial del Palacio del Elíseo el 31 de diciembre.",
    "francia-disolucion-asamblea-2026": "Pregunta si Francia volverá a disolver su Asamblea Nacional entre el 27 de agosto y el 31 de diciembre de 2026. Resuelve con la publicación de un decreto oficial de disolución.",
    "merz-canciller-fin-2026": "Pregunta si Friedrich Merz seguirá siendo canciller de Alemania al terminar 2026. Resuelve con el registro oficial del cargo a las 23:59 hora local del 31 de diciembre.",
    "takaichi-pm-fin-2026": "Pregunta si Sanae Takaichi seguirá siendo primera ministra de Japón al terminar 2026. Resuelve con el registro oficial del cargo a las 23:59 hora local del 31 de diciembre.",
    "carney-pm-fin-2026": "Pregunta si Mark Carney seguirá siendo primer ministro de Canadá al terminar 2026. Resuelve con el registro oficial del cargo a las 23:59 de Ottawa del 31 de diciembre.",
    "zelenski-presidente-fin-2026": "Pregunta si Volodímir Zelenski seguirá siendo el presidente de Ucrania al terminar 2026. Resuelve con el reconocimiento oficial del Estado ucraniano el 31 de diciembre.",
    "vonderleyen-ce-fin-2026": "Pregunta si Ursula von der Leyen seguirá presidiendo la Comisión Europea al terminar 2026. Resuelve con el registro oficial de la Comisión el 31 de diciembre.",
    "onu-sg-mujer-2027": "Pregunta si la persona designada para encabezar la ONU a partir de 2027 será una mujer. Resuelve con la designación oficial de la Asamblea General; si no ocurre antes del cierre de 2026, el mercado se extiende hasta la designación.",
    "demos-camara-congreso-120": "Pregunta si los demócratas tendrán mayoría en la Cámara de Representantes al instalarse el 120.º Congreso. Resuelve con los resultados certificados de las elecciones del 3 de noviembre de 2026.",
    "republicanos-senado-congreso-120": "Pregunta si los republicanos mantendrán el control del Senado tras las elecciones de 2026. Resuelve con la composición del Senado al instalarse el 120.º Congreso, agrupando a los independientes según su bancada.",
    "demos-voto-popular-camara-2026": "Pregunta si los candidatos demócratas sumarán más votos que los de cualquier otro partido en los 435 distritos de la Cámara en noviembre de 2026. Resuelve con la suma oficial de votos.",
    "demos-ganancia-20-escanos-2026": "Pregunta si los demócratas ganarán 20 o más escaños netos en la Cámara de Representantes en 2026. Resuelve comparando la composición inicial del 119.º y del 120.º Congreso.",
    "republicanos-52-senadores-2027": "Pregunta si los republicanos tendrán al menos 52 senadores al iniciar el 120.º Congreso. Resuelve con los senadores electos y en funciones el 3 de enero de 2027.",
    "control-unificado-congreso-2027": "Pregunta si un mismo partido controlará la Cámara y el Senado tras las elecciones de 2026. Resuelve con la composición de ambas cámaras al instalarse el 120.º Congreso.",
    "california-gobernador-demo-2026": "Pregunta si la candidatura demócrata ganará la gubernatura de California en 2026. Resuelve con el resultado oficial certificado por el estado.",
    "texas-gobernador-rep-2026": "Pregunta si la candidatura republicana ganará la gubernatura de Texas en 2026. Resuelve con el resultado oficial certificado por el estado.",
    "florida-gobernador-rep-2026": "Pregunta si la candidatura republicana ganará la gubernatura de Florida en 2026. Resuelve con el resultado oficial certificado por el estado.",
    "shutdown-eeuu-24h-2026": "Pregunta si el gobierno federal de EEUU sufrirá un cierre por falta de fondos de al menos 24 horas continuas entre el 27 de agosto y el 31 de diciembre de 2026. Resuelve con la confirmación oficial de la interrupción.",
    "rusia-ucrania-altofuego-2026": "Pregunta si entrará en vigor un alto el fuego de alcance nacional entre Rusia y Ucrania antes del cierre de 2026. Resuelve con el reconocimiento de ambos gobiernos o de la ONU; las treguas breves no cuentan.",
    "rusia-ucrania-altofuego-30dias": "Pregunta si un alto el fuego nacional entre Rusia y Ucrania iniciado antes del cierre de 2026 se sostendrá 30 días consecutivos. Resuelve con el seguimiento oficial, aunque el conteo termine en 2027.",
    "rusia-ucrania-acuerdo-paz-2026": "Pregunta si Rusia y Ucrania firmarán un acuerdo formal de paz antes del cierre de 2026. Resuelve con la existencia de un documento firmado por ambos gobiernos.",
    "eeuu-iran-acuerdo-nuclear-2026": "Pregunta si EEUU e Irán firmarán un nuevo acuerdo vinculante sobre el programa nuclear iraní antes del cierre de 2026. Resuelve con la firma oficial de un documento bilateral o multilateral.",
    "corea-norte-prueba-nuclear-2026": "Pregunta si Corea del Norte realizará una prueba nuclear antes del cierre de 2026. Resuelve con la confirmación de CTBTO, la ONU o los gobiernos de Corea del Sur o EEUU.",
    "china-taiwan-fuego-real-24nm-2026": "Pregunta si China realizará ejercicios con fuego real dentro de las 24 millas náuticas de la isla principal de Taiwán entre el 27 de agosto y el cierre de 2026. Resuelve con la confirmación oficial de China o Taiwán.",
    "otan-nuevo-miembro-2026": "Pregunta si algún país se incorporará formalmente a la OTAN antes del cierre de 2026. Resuelve únicamente con la entrada en vigor del protocolo de adhesión.",
    "armenia-azerbaiyan-tratado-2026": "Pregunta si el tratado de paz entre Armenia y Azerbaiyán será ratificado por ambos países y entrará en vigor antes del cierre de 2026. Resuelve con las ratificaciones formales.",
    "sudan-altofuego-30dias-2026": "Pregunta si Sudán tendrá un alto el fuego nacional reconocido por la ONU que se sostenga 30 días consecutivos, iniciado antes del cierre de 2026. Resuelve con el seguimiento oficial de la ONU.",
    "israel-iran-ataques-directos-2026": "Pregunta si habrá nuevos ataques militares directos entre fuerzas regulares de Israel e Irán entre el 27 de agosto y el 31 de diciembre de 2026. Los ataques de grupos aliados o proxies no cuentan.",
    "trump-65-ordenes-ejecutivas-2026": "Pregunta si Donald Trump firmará 65 o más órdenes ejecutivas a lo largo de 2026. Resuelve con el conteo final del Federal Register.",
    "trump-veto-2026": "Pregunta si Trump emitirá al menos un veto presidencial formal entre el 27 de agosto y el 31 de diciembre de 2026. Resuelve con el registro de vetos devueltos al Congreso.",
    "trump-gabinete-salida-post-ago-2026": "Pregunta si algún secretario titular confirmado del gabinete de Trump dejará el cargo entre el 27 de agosto y el 31 de diciembre de 2026, por renuncia, destitución o fallecimiento. Los interinos no cuentan.",
    "trump-putin-reunion-post-ago-2026": "Pregunta si Trump y Putin sostendrán una reunión presencial confirmada entre el 27 de agosto y el 31 de diciembre de 2026. Las reuniones previas al 27 de agosto no cuentan.",
    "trump-ley-insurreccion-2026": "Pregunta si Trump invocará formalmente la Insurrection Act antes del cierre de 2026. Resuelve con una orden o proclamación que la cite expresamente; amenazas verbales no cuentan.",
    "trump-aprobacion-gallup-45-2026": "Pregunta si la aprobación presidencial de Trump será de 45% o más en la última encuesta Gallup publicada en 2026. Resuelve con la cifra general de esa medición.",
    "trump-arancel-general-10pct-post-ago": "Pregunta si entre el 27 de agosto y el 31 de diciembre de 2026 se impondrá un nuevo arancel general mínimo de 10% a importaciones de todos o casi todos los países, adicional a los vigentes al 26 de agosto. Resuelve con la orden, proclamación o regulación efectiva.",
    "likud-mas-escanos-2026": "Pregunta si Likud será el partido con más escaños en la elección a la 26.ª Knéset del 27 de octubre de 2026. Resuelve con el resultado oficial definitivo; un empate en el primer lugar resuelve NO.",
    "likud-aliados-61-escanos-2026": "Pregunta si Likud y los partidos que anuncien coalición con él antes de la elección sumarán al menos 61 de los 120 escaños de la 26.ª Knéset. Resuelve con el resultado oficial definitivo.",
    "israel-participacion-70-2026": "Pregunta si la participación en la elección israelí del 27 de octubre de 2026 alcanzará 70% o más. Resuelve con el porcentaje oficial de la Comisión Electoral Central de Israel.",
    "netanyahu-pm-fin-2026": "Pregunta si Benjamin Netanyahu seguirá siendo primer ministro de Israel el 31 de diciembre de 2026, incluso en calidad de interino o de transición. Resuelve con el registro oficial del cargo.",
    "suecia-sap-mas-votos-2026": "Pregunta si el Partido Socialdemócrata será el más votado en la elección al Riksdag del 13 de septiembre de 2026. Resuelve con el resultado nacional oficial.",
    "lula-gana-brasil-2026": "Pregunta si Lula da Silva será proclamado presidente electo de Brasil en 2026, en primera o segunda vuelta. Resuelve con la proclamación del TSE; una victoria en primera vuelta resuelve anticipadamente.",
    "brasil-segunda-vuelta-2026": "Pregunta si la elección presidencial de Brasil del 4 de octubre de 2026 irá a segunda vuelta por falta de mayoría absoluta de votos válidos. Resuelve con el resultado oficial del TSE.",
    "nz-national-mas-votos-2026": "Pregunta si el Partido Nacional obtendrá más party vote que cualquier otro partido en la elección general neozelandesa del 7 de noviembre de 2026. Resuelve con el resultado oficial.",
    "nz-bloque-derecha-mayoria-2026": "Pregunta si National, ACT y New Zealand First sumarán mayoría parlamentaria tras la elección de 2026 en Nueva Zelanda. Resuelve con la asignación definitiva de escaños del nuevo Parlamento.",
    "marruecos-rni-mas-escanos-2026": "Pregunta si el RNI será el partido con más escaños en la elección legislativa marroquí del 23 de septiembre de 2026. Resuelve con el resultado oficial.",
    "letonia-nueva-unidad-2026": "Pregunta si Nueva Unidad será el partido con más escaños en la elección parlamentaria letona de 2026. Resuelve con el resultado oficial.",
    "bulgaria-gerb-presidencia-2026": "Pregunta si la presidencia de Bulgaria en 2026 la ganará un candidato con apoyo formal de GERB anunciado antes de la primera vuelta. Resuelve con el resultado oficial; el cierre se ajustará a la fecha oficial de la primera vuelta cuando se confirme.",
    "haiti-primera-vuelta-2026": "Pregunta si Haití celebrará la votación nacional de primera vuelta presidencial antes del cierre de 2026. Un aplazamiento más allá de 2026 resuelve NO.",
}

_PLAZO_IMPLICITO = ("resuelve NO", "resuelve no", "el mercado se extiende", "Cualquier otro resultado")


def with_plazo(criteria: str) -> str:
    if any(k in criteria for k in _PLAZO_IMPLICITO):
        return criteria
    return criteria + PLAZO


async def main() -> None:
    inserted = 0
    skipped = 0
    missing = [mid for (mid, *_r) in MARKETS if mid not in DESCRIPTIONS]
    if missing:
        raise SystemExit(f"Faltan descripciones para: {missing}")

    async with AsyncSessionLocal() as db:
        for (mid, question, category, subcategory, ends_at_iso,
             initial_yes_price, trending, resolution_criteria) in MARKETS:

            exists = await db.execute(select(Market).where(Market.id == mid))
            if exists.scalar_one_or_none():
                print(f"  SKIP   {mid} (already exists)")
                skipped += 1
                continue

            initial_price = initial_yes_price / 100.0
            q_yes, q_no = lmsr.init_q_for_price(initial_price, B)
            yes_price_val = lmsr.yes_price_pct(q_yes, q_no, B)
            ends_at = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))

            # Nunca sembrar un mercado ya cerrado: si fue borrado a propósito
            # (cleanup-mercados-vencidos-sin-predicciones-*), no debe resucitar.
            if ends_at < datetime.now(timezone.utc):
                print(f"  SKIP   {mid} (ya vencido: ends_at={ends_at_iso}; no se siembran mercados cerrados)")
                skipped += 1
                continue

            market = Market(
                id=mid,
                question=question,
                description=DESCRIPTIONS[mid],
                category=category,
                subcategory=subcategory,
                resolution_criteria=with_plazo(resolution_criteria),
                ends_at=ends_at,
                b=B,
                q_yes=q_yes,
                q_no=q_no,
                yes_price=yes_price_val,
                volume=0.0,
                num_trades=0,
                status=MarketStatus.OPEN,
                trending=trending,
                market_type="binary",
            )
            db.add(market)
            db.add(PriceHistory(
                market_id=market.id,
                yes_price=yes_price_val,
                volume_snapshot=0.0,
            ))
            inserted += 1
            print(f"  INSERT {mid}  yes_price={yes_price_val:.2f}%  b={B}  category={category.name}  ends_at={ends_at_iso}")

        await db.commit()
        print(f"\nListo: {inserted} insertados, {skipped} saltados, {len(MARKETS)} en total")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
