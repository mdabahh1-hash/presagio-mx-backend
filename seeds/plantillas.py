"""Tablas de referencia del sembrador.

COMPETENCIAS alimenta el atajo `tipo: partido` (1X2 de fútbol): la clave es el
nombre exacto de la subcategoría del frontend (src/lib/categories.ts). El
`nombre` lleva la temporada y se actualiza una vez al año.

Origen: market_content/futbol_partidos.py:COMP (2026-09-04) + Ligue 1 y Leagues Cup.
No importamos ese módulo porque arrastra todo market_content/ (10 módulos + assert).
"""
from dataclasses import dataclass

B_DEFAULT = 3000.0


@dataclass(frozen=True)
class Competencia:
    subcategoria: str  # exacto a SUBCATEGORIES.Deportes del frontend
    nombre: str        # para normas y description (lleva temporada)
    fuente: str        # "el acta oficial de …" — se interpola en normas y criterios
    url: str           # resolution_source_url


COMPETENCIAS: dict[str, Competencia] = {
    "LaLiga": Competencia("LaLiga", "LaLiga 2026-27", "el acta oficial de LaLiga (laliga.com)", "https://www.laliga.com"),
    "Liga MX": Competencia("Liga MX", "Apertura 2026 de la Liga MX", "el resultado oficial de la Liga MX (ligamx.net)", "https://ligamx.net"),
    "Premier League": Competencia("Premier League", "Premier League 2026-27", "el acta oficial de la Premier League (premierleague.com)", "https://www.premierleague.com/results"),
    "Serie A": Competencia("Serie A", "Serie A 2026-27", "el acta oficial de la Serie A (legaseriea.it)", "https://www.legaseriea.it"),
    "Bundesliga": Competencia("Bundesliga", "Bundesliga 2026-27", "el acta oficial de la Bundesliga (bundesliga.com)", "https://www.bundesliga.com"),
    "Ligue 1": Competencia("Ligue 1", "Ligue 1 McDonald's 2026-27", "el acta oficial de la Ligue 1 (ligue1.com)", "https://www.ligue1.com"),
    "Champions League": Competencia("Champions League", "fase de liga de la Champions League 2026-27", "el acta oficial de la UEFA (uefa.com)", "https://www.uefa.com/uefachampionsleague/fixtures-results/"),
    "Liga Portugal": Competencia("Liga Portugal", "Liga Portugal Betclic 2026-27", "el acta oficial de la Liga Portugal (ligaportugal.pt)", "https://www.ligaportugal.pt"),
    "MLS": Competencia("MLS", "temporada regular 2026 de la MLS", "el resultado oficial de la MLS (mlssoccer.com)", "https://www.mlssoccer.com/schedule/scores"),
    "Leagues Cup": Competencia("Leagues Cup", "Leagues Cup 2026", "el resultado oficial de la Leagues Cup (leaguescup.com)", "https://www.leaguescup.com"),
    "Saudi Pro League": Competencia("Saudi Pro League", "Saudi Pro League 2026-27", "el resultado oficial de la Saudi Pro League (spl.com.sa)", "https://www.spl.com.sa"),
}

# Espejo de src/lib/categories.ts (SUBCATEGORIES). Una subcategoría fuera de
# esta lista solo produce un AVISO: subcategoría nueva = solo datos, pero hay
# que agregarla al frontend (SUBCATEGORIES y, si es deporte, SPORT_GROUPS).
# Espejo exacto de SUBCATEGORIES en veredikt-mx/src/lib/categories.ts (lo exige el agente de
# siembra: una propuesta con otra subcategoría sale en descartes).
SUBCATEGORIAS_CONOCIDAS: set[str] = {
    # Deportes
    "Liga MX", "Leagues Cup", "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
    "Liga Portugal", "MLS", "Champions League", "Saudi Pro League", "NFL", "F1", "Boxeo",
    # Política
    "Elecciones", "Sheinbaum", "Visas de EEUU", "Congreso", "Regulación digital",
    # Crypto
    "Bitcoin", "Ethereum", "Solana", "Stablecoins", "Regulación", "Adopción México", "Mercado cripto",
    # Entretenimiento, Tech, México, Clima
    "Influencers", "Reality shows", "Música", "Cine y series", "Farándula",
    "IA", "Videojuegos", "Apps y redes", "Huracanes", "Sequía y calor",
    "CDMX", "Cultura", "Estados", "Mascotas y virales", "Batallas de aura", "Seguridad",
    # Global
    "Europa", "Elecciones EEUU", "Trump", "Medio Oriente", "Asia-Pacífico", "Rusia-Ucrania", "Américas",
    "África", "ONU y OTAN", "Migración",
    # Economía (espejo de SUBCATEGORIES['Economía'] del frontend)
    "Tasas Banxico", "Inflación (INPC)", "Tipo de cambio", "PIB México", "Empleo / IMSS",
    "Aranceles / T-MEC", "Fed / tasas EE.UU.", "Bolsa (BMV)", "Mercados EEUU", "Remesas",
}

# Espejo de SUBCATEGORY_IMAGE y MARKET_IMAGE en veredikt-mx/src/lib/marketImage.ts: lo que
# tiene imagen propia en el sitio. Un mercado sin image_url fuera de estas dos listas se
# ve con el ícono genérico de la categoría (lo avisa el agente revisor). Ojo: el frontend
# usa la clave 'Tipo de cambio USD/MXN', distinta de la subcategoría 'Tipo de cambio'.
SUBCATEGORIAS_CON_IMAGEN: set[str] = {
    "Liga MX", "Leagues Cup", "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
    "Liga Portugal", "MLS", "Champions League", "Saudi Pro League", "NFL", "F1", "Boxeo",
    "Elecciones", "Tasas Banxico", "Inflación (INPC)", "Tipo de cambio USD/MXN", "PIB México",
    "Aranceles / T-MEC", "Fed / tasas EE.UU.", "Bolsa (BMV)",
}
MERCADOS_CON_IMAGEN: set[str] = {
    "banxico-mantiene-tasa-sep26", "banxico-recorte-tasa-2026-q3", "mexico-inflacion-2026",
    "tmec-extension-16-anos-2026",
}
