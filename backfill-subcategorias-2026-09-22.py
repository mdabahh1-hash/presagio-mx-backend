"""
Backfill de subcategoría en los 85 mercados activos que no tenían (2026-09-22).

«Explora por tema» (portada, veredikt-mx PopularTopics) arma sus renglones por
subcategoría, y 85 de 157 activos no tenían (Global entero). Mark aprobó en bloque
la tabla de docs/subcategorias-propuesta-2026-09-22.md (raíz del proyecto); el
mapeo de abajo es esa tabla: id → (categoría esperada, subcategoría).

PATCH /admin/markets/{id} no sirve aquí: MarketPatch no tiene `subcategory` y
Pydantic ignora el campo (respondería 200 sin escribir). Por eso un script, como
backfill-subcategoria-crypto-2026-09-18.py.

Solo escribe donde subcategory IS NULL (idempotente). Si la categoría de un id no
es la esperada, sale con código 1 sin escribir. Todo en una transacción.

Dry-run por defecto; APPLY=1 escribe.
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-subcategorias-2026-09-22.py'
  railway run --service Postgres -- bash -c 'APPLY=1 DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python backfill-subcategorias-2026-09-22.py'
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine
from app.models.market import MarketCategory

APPLY = os.environ.get("APPLY") == "1"

MAPEO = {
    "brasil-segunda-vuelta-2026":                ("Global", "Américas"),
    "carney-pm-fin-2026":                        ("Global", "Américas"),
    "haiti-primera-vuelta-2026":                 ("Global", "Américas"),
    "lula-gana-brasil-2026":                     ("Global", "Américas"),
    "china-taiwan-fuego-real-24nm-2026":         ("Global", "Asia-Pacífico"),
    "corea-norte-prueba-nuclear-2026":           ("Global", "Asia-Pacífico"),
    "nz-bloque-derecha-mayoria-2026":            ("Global", "Asia-Pacífico"),
    "nz-national-mas-votos-2026":                ("Global", "Asia-Pacífico"),
    "takaichi-pm-fin-2026":                      ("Global", "Asia-Pacífico"),
    "california-gobernador-demo-2026":           ("Global", "Elecciones EEUU"),
    "control-unificado-congreso-2027":           ("Global", "Elecciones EEUU"),
    "demos-camara-congreso-120":                 ("Global", "Elecciones EEUU"),
    "demos-ganancia-20-escanos-2026":            ("Global", "Elecciones EEUU"),
    "demos-voto-popular-camara-2026":            ("Global", "Elecciones EEUU"),
    "florida-gobernador-rep-2026":               ("Global", "Elecciones EEUU"),
    "republicanos-52-senadores-2027":            ("Global", "Elecciones EEUU"),
    "republicanos-senado-congreso-120":          ("Global", "Elecciones EEUU"),
    "texas-gobernador-rep-2026":                 ("Global", "Elecciones EEUU"),
    "armenia-azerbaiyan-tratado-2026":           ("Global", "Europa"),
    "bulgaria-gerb-presidencia-2026":            ("Global", "Europa"),
    "burnham-pm-fin-2026":                       ("Global", "Europa"),
    "francia-disolucion-asamblea-2026":          ("Global", "Europa"),
    "letonia-nueva-unidad-2026":                 ("Global", "Europa"),
    "macron-presidente-fin-2026":                ("Global", "Europa"),
    "merz-canciller-fin-2026":                   ("Global", "Europa"),
    "suecia-sap-mas-votos-2026":                 ("Global", "Europa"),
    "uk-eleccion-anticipada-2026":               ("Global", "Europa"),
    "vonderleyen-ce-fin-2026":                   ("Global", "Europa"),
    "eeuu-iran-acuerdo-nuclear-2026":            ("Global", "Medio Oriente"),
    "israel-iran-ataques-directos-2026":         ("Global", "Medio Oriente"),
    "israel-participacion-70-2026":              ("Global", "Medio Oriente"),
    "likud-aliados-61-escanos-2026":             ("Global", "Medio Oriente"),
    "likud-mas-escanos-2026":                    ("Global", "Medio Oriente"),
    "netanyahu-pm-fin-2026":                     ("Global", "Medio Oriente"),
    "onu-sg-mujer-2027":                         ("Global", "ONU y OTAN"),
    "otan-nuevo-miembro-2026":                   ("Global", "ONU y OTAN"),
    "rusia-ucrania-acuerdo-paz-2026":            ("Global", "Rusia-Ucrania"),
    "rusia-ucrania-altofuego-2026":              ("Global", "Rusia-Ucrania"),
    "rusia-ucrania-altofuego-30dias":            ("Global", "Rusia-Ucrania"),
    "zelenski-presidente-fin-2026":              ("Global", "Rusia-Ucrania"),
    "shutdown-eeuu-24h-2026":                    ("Global", "Trump"),
    "trump-65-ordenes-ejecutivas-2026":          ("Global", "Trump"),
    "trump-aprobacion-gallup-45-2026":           ("Global", "Trump"),
    "trump-arancel-general-10pct-post-ago":      ("Global", "Trump"),
    "trump-gabinete-salida-post-ago-2026":       ("Global", "Trump"),
    "trump-ley-insurreccion-2026":               ("Global", "Trump"),
    "trump-putin-reunion-post-ago-2026":         ("Global", "Trump"),
    "trump-veto-2026":                           ("Global", "Trump"),
    "marruecos-rni-mas-escanos-2026":            ("Global", "África"),
    "sudan-altofuego-30dias-2026":               ("Global", "África"),
    "tmec-extension-16-anos-2026":               ("Economía", "Aranceles / T-MEC"),
    "imss-empleo-sep26-135k":                    ("Economía", "Empleo / IMSS"),
    "salario-minimo-2027-13":                    ("Economía", "Empleo / IMSS"),
    "inflacion-sep26-menor-340":                 ("Economía", "Inflación (INPC)"),
    "mexico-inflacion-2026":                     ("Economía", "Inflación (INPC)"),
    "bono10-oct26-5pct":                         ("Economía", "Mercados EEUU"),
    "sp500-cierre-oct26-record":                 ("Economía", "Mercados EEUU"),
    "pib-3t26-crece":                            ("Economía", "PIB México"),
    "remesas-sep26-5350":                        ("Economía", "Remesas"),
    "banxico-mantiene-tasa-sep26":               ("Economía", "Tasas Banxico"),
    "banxico-recorte-tasa-2026-q3":              ("Economía", "Tasas Banxico"),
    "banxico-sin-cambio-nov26":                  ("Economía", "Tasas Banxico"),
    "ine-presupuesto-2027-menor":                ("Política", "Congreso"),
    "pef-2027-aprobacion-15-nov":                ("Política", "Congreso"),
    "pelea-legisladores-federales-sep26":        ("Política", "Congreso"),
    "registro-celular-politico-sin-senal-oct26": ("Política", "Regulación digital"),
    "regulacion-scroll-infinito-2026":           ("Política", "Regulación digital"),
    "paso-cortes-proceso-oficial-oct26":         ("Política", "Sheinbaum"),
    "sheinbaum-cancion-mananera-sep26":          ("Política", "Sheinbaum"),
    "andy-recupera-visa-eu-2026":                ("Política", "Visas de EEUU"),
    "andy-solicita-visa-eu-2026":                ("Política", "Visas de EEUU"),
    "norona-rompe-visa-sep26":                   ("Política", "Visas de EEUU"),
    "clima-dos-ciclones-tierra-2026":            ("Clima", "Huracanes"),
    "clima-huracan-cat3-mexico-2026":            ("Clima", "Huracanes"),
    "clima-sequia-20pct-dic-2026":               ("Clima", "Sequía y calor"),
    "clima-temp-sobre-normal-sep-dic-2026":      ("Clima", "Sequía y calor"),
    "anthropic-ipo-2026":                        ("Tech", "IA"),
    "nvidia-1000":                               ("Tech", "IA"),
    "openai-ipo-2026":                           ("Tech", "IA"),
    "cdmx-interviene-batalla-aura-sep26":        ("México", "Batallas de aura"),
    "gobierno-reconoce-batallas-aura-2026":      ("México", "Batallas de aura"),
    "mexico-perros-robot-federal-2026":          ("México", "Seguridad"),
    "cinco-criptos-100b-2026":                   ("Crypto", "Mercado cripto"),
    "cripto-cap-4t-2026":                        ("Crypto", "Mercado cripto"),
    "fatima-bosch-reality-2027":                 ("Entretenimiento", "Reality shows"),
}


async def main() -> int:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, category, subcategory, status FROM markets "
            "WHERE status IN ('OPEN', 'PENDING_RESOLUTION') ORDER BY category, id"
        ))).all()
    por_id = {r[0]: r for r in rows}

    pendientes, ya_tienen, discrepan = [], [], []
    print(f"{'id':44} {'categoría':16} {'subcategoría':22} estado")
    for id_, (cat_esperada, sub) in sorted(MAPEO.items(), key=lambda kv: (kv[1], kv[0])):
        r = por_id.get(id_)
        if r is None:
            continue
        _, cat, actual, status = r
        cat_display = MarketCategory[cat].value
        if cat_display != cat_esperada:
            discrepan.append(id_)
            etiqueta = f"DISCREPA: es {cat_display}"
        elif actual is not None:
            ya_tienen.append(id_)
            etiqueta = f"ya tiene {actual}"
        else:
            pendientes.append(id_)
            etiqueta = f"-> {sub}"
        print(f"{id_:44} {cat_display:16} {etiqueta:22} {status}")

    faltan = sorted(set(MAPEO) - set(por_id))
    sin_sub_fuera = sorted(r[0] for r in rows if r[2] is None and r[0] not in MAPEO)
    if faltan:
        print(f"\nDel mapeo, ya no están activos (resueltos o borrados), se saltan: {faltan}")
    if ya_tienen:
        print(f"\nYa tienen subcategoría, se saltan: {ya_tienen}")
    if sin_sub_fuera:
        print(f"\nActivos sin subcategoría que NO están en la tabla (se quedan así): {sin_sub_fuera}")
    print(f"\n{len(pendientes)} mercados recibirían subcategoría.")

    if discrepan:
        print(f"DISCREPA la categoría de {discrepan}: revisar antes de aplicar. No se escribe nada.")
        await engine.dispose()
        return 1
    if not APPLY:
        print("Dry-run. Correr con APPLY=1 para escribir.")
        await engine.dispose()
        return 0

    async with engine.begin() as conn:
        n = 0
        for id_ in pendientes:
            r = await conn.execute(text(
                "UPDATE markets SET subcategory = :sub WHERE id = :id AND subcategory IS NULL"
            ), {"sub": MAPEO[id_][1], "id": id_})
            n += r.rowcount
        if n != len(pendientes):
            raise RuntimeError(f"Se esperaban {len(pendientes)} filas y se tocaron {n}: rollback.")
    print(f"Actualizados: {n}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
