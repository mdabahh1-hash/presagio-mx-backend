"""Curaduría editorial de Política (landing /mercados?cat=Política). NO se calcula: lo edita Mark.

Formato en `contenido_categorias/__init__.py` y `app/schemas/contenido.py`. Los números de la
proyección y las fechas de la cronología marcados EDITORIAL vienen del mock del diseño y
hay que confirmarlos contra el INE antes de darlos por buenos.
"""

CONTENIDO: dict = {
    "categoria": "POLITICA_MX",
    "actualizado": "2026-09-15",
    "resumen": (
        "El 6 de junio de 2027 se renuevan las 500 diputaciones federales y 17 gubernaturas. "
        "Estos mercados siguen la mayoría en la Cámara, la participación y la agenda de la presidenta."
    ),
    "hero": {
        # Segunda línea (gris) de la gráfica de 90 días; el destacado lo decide el trending.
        "secundario_id": "morena-250-diputados-2027",
    },
    "proyeccion": {
        "titulo": "Cámara de Diputados · proyección del mercado",
        "total": 500,
        "umbral": 334,
        "umbral_etiqueta": "mayoría calificada",
        "mercado_umbral_id": "coalicion-morena-334-diputados-2027",
        # EDITORIAL: confirmar. Cifras ilustrativas del mock; el resto hasta 500 se pinta neutro.
        "bloques": [
            {"partido": "Morena", "escanos": 248},
            {"partido": "PVEM", "escanos": 59},
            {"partido": "PT", "escanos": 40},
            {"partido": "PAN", "escanos": 72},
            {"partido": "PRI", "escanos": 35},
            {"partido": "MC", "escanos": 29},
        ],
        "coalicion": ["Morena", "PVEM", "PT"],
        "nota": "Proyección editorial a partir de los mercados, no una encuesta.",
    },
    "cronologia": {
        "titulo": "Rumbo al 6 de junio de 2027",
        "subtitulo": "Cronología electoral",
        # EDITORIAL: confirmar fechas de registro, campañas y asignación contra el calendario del INE.
        "hitos": [
            {"fecha": "2026-11-15", "etiqueta": "15 nov 2026", "texto": "Límite para aprobar el PEF 2027", "clave": False},
            {"fecha": "2026-12-15", "etiqueta": "Dic 2026", "texto": "Presupuesto del INE publicado en el DOF", "clave": False},
            {"fecha": "2027-04-01", "etiqueta": "Abr 2027", "texto": "Cierre de registro de candidaturas", "clave": False},
            {"fecha": "2027-04-15", "etiqueta": "Abr–may 2027", "texto": "Campañas federales y locales", "clave": False},
            {"fecha": "2027-06-06", "etiqueta": "6 jun 2027", "texto": "Jornada electoral · 500 diputaciones y 17 gubernaturas", "clave": True},
            {"fecha": "2027-08-15", "etiqueta": "Ago 2027", "texto": "Asignación definitiva validada por el INE", "clave": False},
        ],
    },
    # `clave` es la que usan `bloques`, `coalicion` y `src/lib/partyColors.ts` en el frontend.
    "partidos": [
        {"clave": "Morena", "nombre": "Morena", "siglas": "MOR"},
        {"clave": "PAN", "nombre": "PAN", "siglas": "PAN"},
        {"clave": "PVEM", "nombre": "PVEM", "siglas": "PVEM"},
        {"clave": "PT", "nombre": "PT", "siglas": "PT"},
        {"clave": "PRI", "nombre": "PRI", "siglas": "PRI"},
        {"clave": "MC", "nombre": "Movimiento Ciudadano", "siglas": "MC"},
    ],
    # Etiqueta corta por host de `resolution_source_url` (comparar sin "www.").
    "fuentes": [
        {"host": "ine.mx", "etiqueta": "INE"},
        {"host": "iecm.mx", "etiqueta": "IECM"},
        {"host": "gob.mx", "etiqueta": "Presidencia"},
        {"host": "dof.gob.mx", "etiqueta": "DOF"},
        {"host": "gaceta.diputados.gob.mx", "etiqueta": "Gaceta Parlamentaria"},
    ],
    # Tercer dato de la meta de la fila (umbral o hecho estable, ≈40 caracteres).
    "notas": {
        "coalicion-morena-334-diputados-2027": "Mayoría calificada · 334 de 500",
        "morena-250-diputados-2027": "Morena solo · 250 de 500",
        "morena-2027": "Mayoría absoluta · más de 251",
        "morena-10-gubernaturas-2027": "17 gubernaturas en juego",
        "participacion-federal-2027-60": "La intermedia de 2021 rondó 52%",
        "pef-2027-aprobacion-15-nov": "Límite constitucional: 15 de noviembre",
    },
}
