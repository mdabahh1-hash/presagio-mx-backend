"""Atajo `tipo: partido` → documento `multi` completo (1X2 de fútbol).

Un partido en el YAML solo trae: id, competencia, local, visitante, kickoff,
pct [local, empate, visitante], ventana, context (+ trending, copa, image_url,
b, competencia_nombre opcionales). Aquí se derivan pregunta, description,
criterios, normas (partido_rules), categoría, subcategoría, kind y outcomes.
"""
from datetime import datetime

from market_content._common import partido_rules
from seeds.plantillas import B_DEFAULT, COMPETENCIAS

# Mismo texto que usaban los seeds 1X2 (seed-markets-2026-08-27-jornada-1x2-multi.py).
CRITERIOS_1X2 = (
    "Resuelve con el resultado oficial al final de los 90 minutos más tiempo de "
    "compensación según la liga. No cuenta prórroga ni penales. Si el partido se "
    "pospone antes de iniciar, el mercado permanece abierto hasta que se juegue. "
    "Si se abandona, se espera la decisión oficial de la liga."
)

CAMPOS_OBLIGATORIOS = ("id", "competencia", "local", "visitante", "kickoff", "pct", "ventana", "context")


def expandir_partido(doc: dict) -> dict:
    """Lanza KeyError/ValueError si faltan campos o la competencia no existe."""
    faltan = [k for k in CAMPOS_OBLIGATORIOS if not doc.get(k)]
    if faltan:
        raise KeyError(f"faltan campos: {', '.join(faltan)}")
    if doc["competencia"] not in COMPETENCIAS:
        raise ValueError(
            f"competencia '{doc['competencia']}' no está en seeds/plantillas.py "
            f"(opciones: {', '.join(COMPETENCIAS)})"
        )
    comp = COMPETENCIAS[doc["competencia"]]
    local, visitante, ventana = str(doc["local"]), str(doc["visitante"]), str(doc["ventana"])
    nombre = str(doc.get("competencia_nombre") or comp.nombre)
    pct = doc["pct"]
    if not isinstance(pct, (list, tuple)) or len(pct) != 3:
        raise ValueError("pct debe ser una lista [local, empate, visitante]")
    kickoff = doc["kickoff"]
    kickoff_iso = kickoff.isoformat() if isinstance(kickoff, datetime) else str(kickoff)

    return {
        "tipo": "multi",
        "_origen": "partido",
        "id": doc["id"],
        "question": f"¿Quién gana {local} vs {visitante}?",
        "description": f"Mercado 1X2 del partido {local} contra {visitante}, {nombre}, {ventana}.",
        "category": "DEPORTES",
        "subcategory": comp.subcategoria,
        "kind": "partido",
        "image_url": doc.get("image_url"),
        "resolution_criteria": f"{CRITERIOS_1X2} Fuente: {comp.fuente}.",
        "resolution_source_url": comp.url,
        "rules": partido_rules(local, visitante, nombre, comp.fuente, ventana, kickoff_iso,
                               copa=bool(doc.get("copa", False))).strip(),
        "context": doc["context"],
        "ends_at": kickoff,
        "b": doc.get("b", B_DEFAULT),
        "trending": doc.get("trending", False),
        "outcomes": [
            {"key": "local", "label": f"🏠 {local}", "pct": pct[0]},
            {"key": "empate", "label": "🤝 Empate", "pct": pct[1]},
            {"key": "visitante", "label": f"✈️ {visitante}", "pct": pct[2]},
        ],
    }
