"""Revisiones de un mercado activo contra lo que debe tener en producción (veredikt.md §5).

Puro: recibe la fila (o cualquier objeto con los mismos atributos), sin BD ni red.
Cada hallazgo es {id, market_id, pregunta, check, mensaje, fix}; `fix` es
{campo, antes, despues} cuando el agente puede arreglarlo solo (casilla en el
correo) o None cuando es un aviso para revisar a mano.

Sin revisión de título: toda vía de alta (runner, MarketCreate, MarketPatch) ya
rechaza > 70 y los largos que quedan los decidió Mark (scripts/titulos-largos.json).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.services.resolucion.sujeto import requiere_sujeto, validar_sujeto
from seeds.plantillas import (
    COMPETENCIAS, MERCADOS_CON_IMAGEN, SUBCATEGORIAS_CON_IMAGEN, SUBCATEGORIAS_CONOCIDAS,
)
from seeds.schema import CATEGORIAS_PROHIBIDAS, CONTEXT_MIN, RULES_MIN

SUBCATEGORIA_MAX = 18       # «Explora por tema» la pinta en un renglón (§7)
PENDIENTE_DIAS = 3          # pendiente de resolución más de esto → aviso
CAMPOS_FIX = ("resolution_source_url", "kickoff_at", "image_url")  # lo único que el agente escribe
_ESCALERA = re.compile(r"cerrarán? \w+ en US\$[\d,.]+( mil millones| millones)? o más")

NOMBRES = {
    "fuente": "Sin fuente de resolución", "kickoff": "Partido sin hora de inicio",
    "kickoff_orden": "Hora de inicio incoherente", "imagen_invalida": "Imagen inválida",
    "imagen_generica": "Solo ícono genérico de la categoría", "normas": "Normas cortas",
    "contexto": "Contexto corto", "criterios": "Sin criterios de resolución",
    "subcategoria": "Subcategoría", "categoria": "Categoría o tipo",
    "multi": "Multi incompleto", "sujeto": "Accesorio sin sujeto", "receta": "Escalera sin receta",
    "pendiente_viejo": "Pendiente de resolver",
}


def agrupar(avisos: list[dict]) -> list[tuple[str, list[str]]]:
    """[(título del grupo, renglones)] para el correo y la página. La imagen genérica
    va por subcategoría (son decenas por tema); lo demás, un renglón por mercado."""
    grupos: dict[str, list[dict]] = {}
    for x in avisos:
        grupos.setdefault(x["check"], []).append(x)
    out = []
    for c, xs in sorted(grupos.items()):
        if c == "imagen_generica":
            por_sub: dict[str, int] = {}
            for x in xs:
                por_sub[x["sub"] or "sin subcategoría"] = por_sub.get(x["sub"] or "sin subcategoría", 0) + 1
            filas = [f"{s}: {n} mercado{'s' if n > 1 else ''}" for s, n in sorted(por_sub.items(), key=lambda t: -t[1])]
        else:
            filas = [f"{x['pregunta']} — {x['mensaje']}" for x in xs]
        out.append((f"{NOMBRES.get(c, c)} ({len(xs)})", filas))
    return out


def valor(v):
    """Forma JSON de un valor de columna (para `antes`/`despues` y compararlos al aplicar)."""
    return v.isoformat() if isinstance(v, datetime) else v


def revisar(m, n_outcomes: int, ahora: datetime) -> list[dict]:
    out: list[dict] = []
    cat = getattr(m.category, "name", m.category)
    sub = m.subcategory

    def h(check: str, mensaje: str, campo: str | None = None, despues=None) -> None:
        fix = {"campo": campo, "antes": valor(getattr(m, campo)), "despues": valor(despues)} if campo else None
        out.append({"id": f"{m.id}:{check}", "market_id": m.id, "pregunta": m.question, "sub": sub,
                    "check": check, "mensaje": mensaje, "fix": fix})

    rules = m.rules or ""
    if not m.resolution_source_url and not rules.startswith("Cómo se resuelve:"):
        comp = COMPETENCIAS.get(sub or "")
        if m.kind == "partido" and comp:
            h("fuente", f"Sin fuente: poner la oficial de {sub}", "resolution_source_url", comp.url)
        else:
            h("fuente", "Sin resolution_source_url y las normas no abren con «Cómo se resuelve:»")

    if m.kind == "partido" and m.kickoff_at is None:
        h("kickoff", "Partido sin kickoff_at: un partido cierra al silbatazo (kickoff = cierre)",
          "kickoff_at", m.ends_at)
    if m.kickoff_at is not None and (cat != "DEPORTES" or m.kickoff_at > m.ends_at):
        h("kickoff_orden", "kickoff_at fuera de Deportes o posterior al cierre")

    img = m.image_url
    if img and not (img.startswith("https://") or img.startswith("/img/")):
        h("imagen_invalida", f"image_url no es https:// ni /img/ ({img[:60]}): quitarla para usar el respaldo",
          "image_url", None)
    elif not img and m.id not in MERCADOS_CON_IMAGEN and (sub or "") not in SUBCATEGORIAS_CON_IMAGEN:
        h("imagen_generica", f"Sin imagen propia para «{sub or 'sin subcategoría'}»: el sitio pinta el ícono de la categoría")

    if len(rules) < RULES_MIN:
        h("normas", f"Normas de {len(rules)} caracteres (mínimo {RULES_MIN})")
    if len(m.context or "") < CONTEXT_MIN:
        h("contexto", f"Contexto de {len(m.context or '')} caracteres (mínimo {CONTEXT_MIN})")
    if not (m.resolution_criteria or "").strip():
        h("criterios", "Sin criterios de resolución")

    if not sub:
        h("subcategoria", "Sin subcategoría (no sale en su tema ni en «Explora por tema»)")
    elif sub not in SUBCATEGORIAS_CONOCIDAS:
        h("subcategoria", f"Subcategoría «{sub}» no está en el frontend (SUBCATEGORIES)")
    elif len(sub) > SUBCATEGORIA_MAX:
        h("subcategoria", f"Subcategoría «{sub}» pasa de {SUBCATEGORIA_MAX} caracteres")

    if cat in CATEGORIAS_PROHIBIDAS or (m.kind is not None and cat != "DEPORTES"):
        h("categoria", f"Categoría {cat} retirada o kind '{m.kind}' fuera de Deportes")

    if m.market_type == "multi" and n_outcomes < 2:
        h("multi", f"Multi con {n_outcomes} opciones")

    spec = requiere_sujeto(cat, m.market_type, sub, m.question)
    if spec and (not m.sujeto or validar_sujeto(spec, m.sujeto, sub)):
        h("sujeto", f"Accesorio de jugador sin sujeto válido: `sembrar-mercados.py identificar --only {m.id}`")

    if m.market_type == "binary" and not m.auto_resolucion and _ESCALERA.search(m.question):
        h("receta", "Peldaño de escalera cripto sin auto_resolucion")

    status = getattr(m.status, "name", m.status)
    if status == "PENDING_RESOLUTION" and m.ends_at < ahora - timedelta(days=PENDIENTE_DIAS):
        h("pendiente_viejo", f"Cerró hace más de {PENDIENTE_DIAS} días y sigue sin resolver")
    return out
