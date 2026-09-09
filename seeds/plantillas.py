"""Tablas de referencia del sembrador.

COMPETENCIAS alimenta el atajo `tipo: partido` (1X2 de fútbol): la clave es el
nombre exacto de la subcategoría del frontend (src/lib/categories.ts). El
`nombre` lleva la temporada y se actualiza una vez al año.

Origen: market_content/futbol_partidos.py:COMP (2026-09-04) + Ligue 1 y Leagues Cup.
No importamos ese módulo porque arrastra todo market_content/ (10 módulos + assert).
"""
from dataclasses import dataclass

B_DEFAULT = 1000.0


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
SUBCATEGORIAS_CONOCIDAS: set[str] = {
    # Deportes
    "Liga MX", "Leagues Cup", "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
    "Liga Portugal", "MLS", "Champions League", "Saudi Pro League", "NFL", "F1", "Boxeo",
    # Política / sociedad
    "Elecciones", "Sheinbaum", "Influencers", "Migración",
}
