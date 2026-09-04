"""Contenido redactado por mercado: Normas (rules), Contexto del mercado (context) y fuente de resolución (source_url).

Cada módulo expone `CONTENT: dict[id, {"rules", "context", "source_url"}]`; `ALL` los une.
Lo aplica `backfill-normas-contexto-fuente-2026-09-04.py`. Al sembrar mercados nuevos,
pasar estos tres campos directamente al `Market(...)` del seed (ver seed-markets-2026-09-04-sociedad.py).

Regla: toda entrada con `source_url=None` debe abrir sus Normas con "Cómo se resuelve:"
(lo garantiza `check()` y lo verifica el backfill antes de escribir).
"""
from market_content import (
    clima,
    crypto,
    economia_mercados,
    entretenimiento_tech,
    f1_boxeo,
    futbol_accesorios,
    futbol_partidos,
    mundo,
    nfl,
    politica_mx,
)

MODULES = [
    futbol_partidos, futbol_accesorios, nfl, f1_boxeo,
    politica_mx, mundo, crypto, economia_mercados, clima, entretenimiento_tech,
]

ALL: dict[str, dict] = {}
for _m in MODULES:
    dup = set(ALL) & set(_m.CONTENT)
    assert not dup, f"ids duplicados entre módulos: {dup}"
    ALL.update(_m.CONTENT)


def check() -> list[str]:
    """Devuelve una lista de problemas (vacía si todo está bien)."""
    problems = []
    for mid, e in ALL.items():
        rules, ctx, url = e["rules"], e["context"], e["source_url"]
        if not rules or len(rules) < 200:
            problems.append(f"{mid}: rules demasiado cortas ({len(rules or '')} chars)")
        if not ctx or len(ctx) < 120:
            problems.append(f"{mid}: context demasiado corto ({len(ctx or '')} chars)")
        if len(rules) > 6000 or len(ctx) > 6000:
            problems.append(f"{mid}: texto > 6000 chars")
        if url is None and not rules.startswith("Cómo se resuelve:"):
            problems.append(f"{mid}: sin source_url y las normas no abren con 'Cómo se resuelve:'")
        if url is not None and not url.startswith("https://"):
            problems.append(f"{mid}: source_url no es https ({url})")
    return problems
