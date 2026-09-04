"""Normas / Contexto / fuente: Crypto. 12 activos al 2026-09-04."""
from market_content._common import FUENTE_CAIDA, binario_rules, entry

CF = "https://www.cfbenchmarks.com"
COINGECKO = "https://www.coingecko.com"
FIN_2026 = "2026-12-31T23:59:00+00:00"

CONTENT: dict[str, dict] = {}

CONTENT["bitcoin-150k"] = entry(
    binario_rules(f"""
Resuelve SÍ si el precio de Bitcoin, calculado como el promedio simple del precio spot BTC/USD en Binance y en Coinbase (Coinbase Advanced, antes Coinbase Pro) en el mismo instante, supera los US$150,000 en cualquier momento antes del 1 de diciembre de 2026 (00:00 UTC). Basta con que el promedio toque US$150,000.01 una vez; no hace falta un cierre diario por encima. Un pico en un solo exchange que no se refleje en el otro (por ejemplo, una mecha por baja liquidez) no cuenta.

{FUENTE_CAIDA}
""", "2026-11-30T00:00:00+00:00",
        como="no hay un índice oficial único para esta condición; el equipo de VEREDIKT verifica con el historial de precios de Binance y Coinbase (velas de 1 minuto) que el promedio de ambos superó US$150,000 en el mismo instante, y publica las capturas en los comentarios al resolver."),
    "Bitcoin superó por primera vez los US$100,000 en diciembre de 2024 y marcó máximos históricos por encima de US$120,000 en 2025, impulsado por los ETF spot y la compra de tesorerías corporativas. Este mercado, creado a mediados de 2026, apuesta a que el ciclo alcista lleve el precio hasta US$150,000 antes de diciembre de 2026.",
    None)

CONTENT["btc-cierre-100k-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el valor de la CME CF Bitcoin Reference Rate (BRR, la referencia diaria de las 4:00 p.m. hora de Londres) del 31 de diciembre de 2026, publicada por CF Benchmarks, es igual o mayor a US$100,000. Se usa esa referencia y no el precio de un exchange en particular. {FUENTE_CAIDA}
""", FIN_2026, anticipado=False),
    "La CME CF Bitcoin Reference Rate es el índice con el que se liquidan los futuros de Bitcoin del CME y es la referencia institucional más usada. Bitcoin cerró 2024 cerca de US$94,000 y 2025 por encima de US$100,000. El mercado apuesta a que termine 2026 en seis cifras.",
    CF)

CONTENT["btc-cierre-diario-60k-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si cualquier valor diario de la CME CF Bitcoin Reference Rate (BRR) publicado por CF Benchmarks entre el 27 de agosto y el 31 de diciembre de 2026 es inferior a US$60,000. Se toma la referencia diaria, no mínimos intradía. {FUENTE_CAIDA}
""", FIN_2026),
    "Un valor de referencia por debajo de US$60,000 implicaría una caída de más del 40% desde los máximos de 2025, algo que Bitcoin ha vivido en cada ciclo anterior (2018, 2022). Este mercado apuesta a que ese escenario de corrección profunda ocurra en los últimos cuatro meses de 2026.",
    CF)

CONTENT["btc-dominancia-60-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el dato de dominancia de Bitcoin (participación de Bitcoin en la capitalización total del mercado cripto) que muestra CoinGecko el 31 de diciembre de 2026 a las 23:59 UTC es igual o mayor a 60.0%. Se usa el dato de la página global de CoinGecko capturado a esa hora, o su historial si la captura falla. {FUENTE_CAIDA}
""", FIN_2026, anticipado=False),
    "La dominancia de Bitcoin mide cuánto del valor total del mercado cripto está en Bitcoin. Subió de cerca del 40% en 2022 a más del 60% en 2025, a medida que los ETF concentraron el dinero institucional en Bitcoin y las altcoins se rezagaron. Un «altseason» la haría bajar. El mercado apuesta a que cierre 2026 en 60% o más.",
    COINGECKO)

CONTENT["btc-toca-120k-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el índice CME CF Bitcoin Real Time Index (BRTI), publicado por CF Benchmarks, registra un valor de al menos US$120,000 en cualquier momento entre el 27 de agosto y el 31 de diciembre de 2026. Basta con tocar el nivel una vez. {FUENTE_CAIDA}
""", FIN_2026),
    "Bitcoin marcó máximos históricos por encima de US$120,000 en 2025. Este mercado, creado a finales de agosto de 2026, apuesta a que el precio vuelva a alcanzar ese nivel en el índice en tiempo real del CME antes de terminar el año, sin importar dónde cierre después.",
    CF)

CONTENT["cinco-criptos-100b-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si la clasificación por capitalización de mercado de CoinGecko del 31 de diciembre de 2026 (captura a las 23:59 UTC) muestra al menos cinco criptomonedas con capitalización superior a US$100,000 millones, excluyendo stablecoins (USDT, USDC y similares) y tokens envueltos o derivados de otro activo (como WBTC o stETH). {FUENTE_CAIDA}
""", FIN_2026, anticipado=False),
    "En los máximos de 2025 solo Bitcoin, Ethereum, XRP, BNB y Solana rondaron o superaron los US$100,000 millones de capitalización, sin contar a Tether. Que cinco activos no stablecoin superen ese umbral al cierre de 2026 requiere un mercado amplio y no solo un Bitcoin fuerte.",
    COINGECKO)

CONTENT["cripto-cap-4t-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si CoinGecko registra una capitalización total del mercado cripto de al menos US$4 trillion (US$4 billones en la nomenclatura del español) en cualquier momento entre el 27 de agosto y el 31 de diciembre de 2026, según su gráfica histórica de capitalización global. Basta con tocar el nivel una vez. {FUENTE_CAIDA}
""", FIN_2026),
    "La capitalización total del mercado cripto superó por primera vez los US$4 trillion en 2025, con Bitcoin por encima de US$120,000. El mercado apuesta a que ese nivel se vuelva a tocar entre finales de agosto y el cierre de 2026.",
    COINGECKO)

CONTENT["eeuu-compra-bitcoin-2026"] = entry(
    binario_rules("""
Resuelve SÍ si antes del 31 de diciembre de 2026 hay un anuncio oficial del Departamento del Tesoro o de la Casa Blanca de que el gobierno de Estados Unidos ejecutó una compra de Bitcoin para su Reserva Estratégica con fondos que no provengan de activos decomisados, y la compra está efectivamente ejecutada (no solo autorizada). Transferencias de Bitcoin incautado a la reserva, propuestas legislativas o anuncios de intención no cuentan.
""", FIN_2026),
    "En marzo de 2025 Trump creó por orden ejecutiva una Reserva Estratégica de Bitcoin formada con activos decomisados, y encargó al Tesoro estudiar formas «neutrales para el presupuesto» de adquirir más. Hasta ahora no ha habido compras con dinero público. El mercado apuesta a que la primera compra real ocurra antes de terminar 2026.",
    "https://home.treasury.gov")

CONTENT["eth-cierre-3000-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el valor de la CME CF Ether-Dollar Reference Rate (ETHUSD_RR) del 31 de diciembre de 2026, publicada por CF Benchmarks, es igual o mayor a US$3,000. {FUENTE_CAIDA}
""", FIN_2026, anticipado=False),
    "Ethereum, la segunda criptomoneda por capitalización, marcó máximos por encima de US$4,800 en 2025 impulsada por los ETF spot y las tesorerías corporativas de ETH, tras un 2024 en el que se rezagó frente a Bitcoin. El mercado apuesta a que cierre 2026 en US$3,000 o más según la referencia del CME.",
    CF)

CONTENT["ley-estructura-mercado-cripto-2026"] = entry(
    binario_rules("""
Resuelve SÍ si el presidente de Estados Unidos firma antes del 31 de diciembre de 2026 una ley federal que regule de forma sustancial la jurisdicción de la SEC y la CFTC sobre activos digitales (una «ley de estructura de mercado», como el CLARITY Act o equivalente), según el registro de leyes promulgadas de congress.gov. Una ley solo de stablecoins, una regla de una agencia o una orden ejecutiva no cuentan.
""", FIN_2026),
    "En julio de 2025 se promulgó la GENIUS Act, la ley de stablecoins, y la Cámara aprobó el CLARITY Act de estructura de mercado, que define qué activos supervisa la SEC y cuáles la CFTC. Su avance en el Senado ha sido lento por desacuerdos sobre DeFi y conflictos de interés. El mercado apuesta a que la ley se firme antes de terminar 2026.",
    "https://www.congress.gov")

CONTENT["sol-cierre-150-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el valor de la CME CF Solana-Dollar Reference Rate (SOLUSD_RR) del 31 de diciembre de 2026, publicada por CF Benchmarks, es igual o mayor a US$150. {FUENTE_CAIDA}
""", FIN_2026, anticipado=False),
    "Solana es una de las cinco mayores criptomonedas y la red más usada para memecoins y aplicaciones de consumo. Marcó máximos cerca de US$295 en enero de 2025 y luego corrigió con fuerza. El mercado apuesta a que cierre 2026 en US$150 o más según la referencia del CME.",
    CF)

CONTENT["stablecoins-350b-2026"] = entry(
    binario_rules(f"""
Resuelve SÍ si el dato agregado de capitalización total de stablecoins publicado por DefiLlama (defillama.com/stablecoins) alcanza US$350,000 millones en cualquier momento antes del 31 de diciembre de 2026. Basta con tocar el nivel una vez en la gráfica histórica. {FUENTE_CAIDA}
""", FIN_2026),
    "La capitalización de las stablecoins pasó de unos US$130,000 millones a comienzos de 2024 a más de US$250,000 millones en 2025, con Tether y USDC al frente, impulsada por la GENIUS Act y la adopción en pagos. El mercado apuesta a que el total llegue a US$350,000 millones antes de terminar 2026.",
    "https://defillama.com/stablecoins")
