"""Curaduría editorial de Política (landing /mercados?cat=Política y píldora Política de la Home).

Formato en `contenido_categorias/__init__.py` y `app/schemas/contenido.py`. Regla editorial (Mark,
2026-09-15): nada ilustrativo en pantalla. Cada cifra sale de un mercado (la proyección se calcula
en vivo con los precios de los seis mercados de rangos) o de una fuente oficial enlazada (la
cronología es el calendario que aprobó el Consejo General del INE el 30 de julio de 2026).
"""

CONTENIDO: dict = {
    "categoria": "POLITICA_MX",
    "actualizado": "2026-09-15",
    "resumen": (
        "El 6 de junio de 2027 se renuevan las 500 diputaciones federales y 17 gubernaturas. "
        "Estos mercados siguen la mayoría en la Cámara, la participación y la agenda de la presidenta."
    ),
    "hero": {
        # Segunda línea (gris) de la gráfica de 90 días; el destacado lo decide el trending. Binario.
        "secundario_id": "morena-250-diputados-2027",
    },
    "proyeccion": {
        "titulo": "Cámara de Diputados · proyección del mercado",
        "total": 500,
        "umbral": 334,
        "umbral_etiqueta": "mayoría calificada",
        # "Prob. de 334+" = yes_price vivo de este mercado (binario; un multi tiene yes_price 0).
        "mercado_umbral_id": "coalicion-morena-334-diputados-2027",
        # Escaños esperados por partido = Σ precio(opción) × escanos_por_opcion[opción], calculado en el
        # frontend con los precios vivos del mercado multi `mercado_id` (mercados-pendientes.yaml,
        # ids diputados-2027-rango-*). Las keys deben ser EXACTAMENTE las outcomes del mercado
        # (lo comprueba tests/test_contenido_categorias.py). Valor por rango: punto medio del rango
        # cerrado; en los abiertos, el borde menos/más la mitad del ancho del rango contiguo.
        "bloques": [
            {"partido": "Morena", "mercado_id": "diputados-2027-rango-morena",
             "escanos_por_opcion": {"r_menos_200": 188, "r_200_224": 212, "r_225_249": 237, "r_250_274": 262, "r_275_mas": 288}},
            {"partido": "PVEM", "mercado_id": "diputados-2027-rango-pvem",
             "escanos_por_opcion": {"r_menos_30": 22, "r_30_44": 37, "r_45_59": 52, "r_60_74": 67, "r_75_mas": 83}},
            {"partido": "PT", "mercado_id": "diputados-2027-rango-pt",
             "escanos_por_opcion": {"r_menos_20": 12, "r_20_34": 27, "r_35_49": 42, "r_50_64": 57, "r_65_mas": 73}},
            {"partido": "PAN", "mercado_id": "diputados-2027-rango-pan",
             "escanos_por_opcion": {"r_menos_50": 42, "r_50_64": 57, "r_65_79": 72, "r_80_94": 87, "r_95_mas": 103}},
            {"partido": "PRI", "mercado_id": "diputados-2027-rango-pri",
             "escanos_por_opcion": {"r_menos_20": 15, "r_20_29": 25, "r_30_39": 35, "r_40_49": 45, "r_50_mas": 55}},
            {"partido": "MC", "mercado_id": "diputados-2027-rango-mc",
             "escanos_por_opcion": {"r_menos_20": 15, "r_20_29": 25, "r_30_39": 35, "r_40_49": 45, "r_50_mas": 55}},
        ],
        "coalicion": ["Morena", "PVEM", "PT"],
        "nota": (
            "Escaños esperados: suma de probabilidad × punto medio de cada rango, con los precios vivos de "
            "seis mercados independientes (uno por partido). No es una encuesta."
        ),
    },
    "cronologia": {
        "titulo": "Rumbo al 6 de junio de 2027",
        "subtitulo": "Calendario del INE",
        # Plan Integral y Calendario del PEF 2026-2027, aprobado por el Consejo General del INE el
        # 30 de julio de 2026 (nota oficial de Central Electoral). `fecha` = inicio del periodo.
        "fuente_url": "https://centralelectoral.ine.mx/2026/07/31/planeara-y-organizara-ine-mas-de-500-actividades-del-proceso-electoral-federal-2026%E2%80%912027/",
        "hitos": [
            {"fecha": "2026-09-10", "etiqueta": "10 sep 2026", "texto": "Inicio del Proceso Electoral Federal 2026-2027", "clave": False},
            {"fecha": "2027-01-04", "etiqueta": "4 ene – 12 feb", "texto": "Precampañas", "clave": False},
            {"fecha": "2027-03-22", "etiqueta": "22 mar – 3 abr", "texto": "Registro de candidaturas", "clave": False},
            {"fecha": "2027-04-04", "etiqueta": "4 abr – 2 jun", "texto": "Campañas electorales", "clave": False},
            {"fecha": "2027-06-06", "etiqueta": "6 jun 2027", "texto": "Jornada electoral · 500 diputaciones y 17 gubernaturas", "clave": True},
            {"fecha": "2027-06-09", "etiqueta": "9 – 11 jun", "texto": "Cómputos distritales", "clave": False},
            {"fecha": "2027-08-01", "etiqueta": "1 – 23 ago", "texto": "Asignación de diputaciones de representación proporcional", "clave": False},
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
    # Tercer dato de la meta de la fila (umbral o hecho estable, ≈40 caracteres). Solo ids con
    # normas en market_content (lo exige el test); los multi de rangos no llevan nota.
    "notas": {
        "coalicion-morena-334-diputados-2027": "Mayoría calificada · 334 de 500",
        "morena-250-diputados-2027": "Morena solo · 250 de 500",
        "morena-2027": "Morena + aliados · más de 251",
        "morena-10-gubernaturas-2027": "17 gubernaturas en juego",
        "participacion-federal-2027-60": "La intermedia de 2021 rondó 52%",
        "pef-2027-aprobacion-15-nov": "Límite constitucional: 15 de noviembre",
    },
}
