"""Contenido curado por categoría: lo que una landing de categoría muestra y NO se calcula.

Hermano de `market_content/` (normas por mercado). Cada módulo expone `CONTENIDO: dict`
con la forma de abajo; `CATEGORIAS` los indexa por NOMBRE del enum (`POLITICA_MX`, como la
BD y el YAML). Lo sirve `GET /api/contenido/categorias/{categoria}` (`app/api/contenido.py`)
validado con `app/schemas/contenido.py`. Lo edita Mark a mano; subir `actualizado` al editar.

Este paquete no importa `app/` ni `market_content/` (la API lo carga al arrancar).

Formato (todas las claves en español; `?` = opcional):

    CONTENIDO = {
        "categoria":   "POLITICA_MX",      # NOMBRE del enum MarketCategory
        "actualizado": "2026-09-15",       # ISO
        "resumen"?:    str,                # una línea bajo el h1 de la landing
        "hero": {"secundario_id"?: str},   # mercado de la 2.ª línea (gris) de la gráfica de 90 días
        "proyeccion"?: {                   # barra de escaños + tabla de partidos (calculadas en vivo)
            "titulo": str, "total": int, "umbral": int, "umbral_etiqueta": str,
            "mercado_umbral_id"?: str,     # "Prob. de {umbral}+" = yes_price vivo de este mercado (binario)
            "bloques": [{                  # orden = orden en la barra; un mercado multi por partido
                "partido": str,
                "mercado_id": str,         # multi cuyas outcomes son rangos de escaños
                "escanos_por_opcion": {outcome_key: int},   # escaños representativos de cada rango
            }, ...],                       # esperados = Σ precio × escaños; el frontend lo calcula
            "coalicion": [str, ...],       # claves de partido; la primera es el partido principal
            "nota"?: str,
        },
        "cronologia"?: {
            "titulo": str, "subtitulo"?: str,
            "fuente_url"?: str,            # https; enlace "Fuente" de la tarjeta (calendario oficial)
            "hitos": [{"fecha": "AAAA-MM-DD", "etiqueta": str, "texto": str, "clave": bool}, ...],
        },                                 # asc por fecha; exactamente un hito con clave=True (oro)
        "partidos": [{"clave": str, "nombre": str, "siglas": str}, ...],
        "fuentes":  [{"host": str, "etiqueta": str}, ...],      # host sin "www."
        "notas":    {market_id: str},      # tercer dato de la meta de la fila (≈40 chars)
    }
"""
from datetime import date

from contenido_categorias import politica

MODULOS = (politica,)

CATEGORIAS: dict[str, dict] = {}
for _m in MODULOS:
    _clave = _m.CONTENIDO["categoria"]
    assert _clave not in CATEGORIAS, f"categoría duplicada: {_clave}"
    CATEGORIAS[_clave] = _m.CONTENIDO


def check() -> list[str]:
    """Devuelve una lista de problemas de coherencia (vacía si todo está bien).

    La forma la valida Pydantic (`app/schemas/contenido.py`); aquí van las reglas
    editoriales que un esquema no expresa bien.
    """
    problemas: list[str] = []
    for clave, c in CATEGORIAS.items():
        partidos = {p["clave"] for p in c.get("partidos", [])}

        pr = c.get("proyeccion")
        if pr:
            ids = [b["mercado_id"] for b in pr["bloques"]]
            if len(set(ids)) != len(ids):
                problemas.append(f"{clave}: mercado_id repetido en bloques")
            for b in pr["bloques"]:
                mapa = b.get("escanos_por_opcion") or {}
                if len(mapa) < 2:
                    problemas.append(f"{clave}: {b['partido']} necesita al menos 2 rangos en escanos_por_opcion")
                fuera = [k for k, v in mapa.items() if not 0 <= v <= pr["total"]]
                if fuera:
                    problemas.append(f"{clave}: {b['partido']} con escaños fuera de 0..{pr['total']}: {fuera}")
            if pr["umbral"] > pr["total"]:
                problemas.append(f"{clave}: umbral {pr['umbral']} > total {pr['total']}")
            en_bloques = {b["partido"] for b in pr["bloques"]}
            fuera = set(pr["coalicion"]) - en_bloques
            if fuera:
                problemas.append(f"{clave}: coalición con partidos sin bloque: {sorted(fuera)}")
            sin_ficha = en_bloques - partidos
            if sin_ficha:
                problemas.append(f"{clave}: bloques sin ficha en `partidos`: {sorted(sin_ficha)}")

        cr = c.get("cronologia")
        if cr:
            fechas = [date.fromisoformat(h["fecha"]) for h in cr["hitos"]]
            if fechas != sorted(fechas):
                problemas.append(f"{clave}: hitos fuera de orden cronológico")
            claves = sum(1 for h in cr["hitos"] if h.get("clave"))
            if claves != 1:
                problemas.append(f"{clave}: la cronología debe tener exactamente un hito clave ({claves})")
            fuente = cr.get("fuente_url")
            if fuente and not fuente.startswith("https://"):
                problemas.append(f"{clave}: fuente_url de la cronología debe ser https ({fuente})")

        for f in c.get("fuentes", []):
            if f["host"].startswith("www.") or "/" in f["host"]:
                problemas.append(f"{clave}: host de fuente debe ir sin www. ni ruta ({f['host']})")
    return problemas
