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
        "proyeccion"?: {                   # barra de escaños + tabla de partidos
            "titulo": str, "total": int, "umbral": int, "umbral_etiqueta": str,
            "mercado_umbral_id"?: str,     # "Prob. de {umbral}+" = yes_price vivo de este mercado
            "bloques": [{"partido": str, "escanos": int}, ...],   # orden = orden en la barra
            "coalicion": [str, ...],       # claves de partido; la primera es el partido principal
            "nota"?: str,
        },
        "cronologia"?: {
            "titulo": str, "subtitulo"?: str,
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
            suma = sum(b["escanos"] for b in pr["bloques"])
            if suma > pr["total"]:
                problemas.append(f"{clave}: los bloques suman {suma} > total {pr['total']}")
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

        for f in c.get("fuentes", []):
            if f["host"].startswith("www.") or "/" in f["host"]:
                problemas.append(f"{clave}: host de fuente debe ir sin www. ni ruta ({f['host']})")
    return problemas
