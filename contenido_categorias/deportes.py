"""Curaduría editorial de Deportes (landing /mercados?cat=Deportes y píldora Deportes de la Home).

Formato en `contenido_categorias/__init__.py` y `app/schemas/contenido.py`. Regla editorial (Mark,
2026-09-15): nada ilustrativo en pantalla. La tabla "Probabilidad de título" y el "Favorito al
título" de cada liga se calculan en vivo con los precios del multi de campeón que apunta `titulos`;
si una liga no tiene mercado, la landing no monta ese bloque. Volumen, movimiento, jornada y
marcador salen de la API (`/markets/resumen`, `/markets/movers`, `kickoff_at`, `/markets/en-vivo`).
"""

CONTENIDO: dict = {
    "categoria": "DEPORTES",
    "actualizado": "2026-09-25",
    # Liga (subcategoría exacta de src/lib/categories.ts) → multi de campeón de la temporada.
    # Solo ids con normas en market_content o documentos en mercados-pendientes.yaml (lo exige
    # tests/test_contenido_categorias.py). Al resolverse el multi, quitar la entrada o apuntarla
    # al del torneo siguiente (Clausura 2027, Super Bowl LXII).
    "titulos": {
        "NFL": "nfl-campeon-super-bowl-lxi",
        "College Football": "cfb-campeon-cfp-2026",
        "Liga MX": "mx-campeon-apertura-2026",
        "F1": "f1-campeon-pilotos-2026",
        "MLS": "mls-campeon-cup-2026",
        "Premier League": "pl-campeon-2026-27",
        "LaLiga": "laliga-campeon-2026-27",
        "Champions League": "ucl-campeon-2026-27",
        # Boxeo no tiene liga: un multi por cinturón (el panel pinta uno tras otro)
        "Boxeo": ["box-cmb-168-campeon-2026", "box-amb-168-campeon-2026"],
    },
    # Etiqueta corta por host de `resolution_source_url` (comparar sin "www."). Hosts de
    # seeds/plantillas.py:COMPETENCIAS y de los seeds de NFL, F1 y boxeo.
    "fuentes": [
        {"host": "ligamx.net", "etiqueta": "Liga MX"},
        {"host": "nfl.com", "etiqueta": "NFL"},
        {"host": "uefa.com", "etiqueta": "UEFA"},
        {"host": "premierleague.com", "etiqueta": "Premier League"},
        {"host": "laliga.com", "etiqueta": "LaLiga"},
        {"host": "legaseriea.it", "etiqueta": "Serie A"},
        {"host": "bundesliga.com", "etiqueta": "Bundesliga"},
        {"host": "ligue1.com", "etiqueta": "Ligue 1"},
        {"host": "ligaportugal.pt", "etiqueta": "Liga Portugal"},
        {"host": "mlssoccer.com", "etiqueta": "MLS"},
        {"host": "leaguescup.com", "etiqueta": "Leagues Cup"},
        {"host": "spl.com.sa", "etiqueta": "Saudi Pro League"},
        {"host": "formula1.com", "etiqueta": "Fórmula 1"},
        {"host": "boxrec.com", "etiqueta": "BoxRec"},
        {"host": "espn.com", "etiqueta": "ESPN"},
    ],
    "notas": {},
}
