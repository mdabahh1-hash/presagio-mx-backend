"""Revisor de reglas del agente de siembra (CRITERIOS-DE-MERCADOS.md), en Python.

Se aplica a las propuestas que llegan de afuera (la rutina creativa de Claude, por
`POST /api/admin/siembra/planes/proponer`): lo que no pasa sale en descartes con el
motivo, nunca se siembra. Orden fijo (§12.1): lista negra → esquema y 70 caracteres
→ subcategoría → precio → plazo → fuente → evidencia → duplicado → cupo de locos.

Lo que Python no puede juzgar (picante, prueba del titular, redacción neutral, las
5 preguntas de la raya) lo declara la rutina en `evidencia` y Mark lo ve en el correo.
Cupos por categoría y mezcla: pendientes de decidir con Mark (§4, §8).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from app.services.siembra.partidos import _yaml
from seeds.plantillas import SUBCATEGORIAS_CONOCIDAS
from seeds.schema import QUESTION_MAX, SchemaError, cargar_texto

PRIOR_MIN, PRIOR_MAX = 10, 90          # §3 (Mark, 24-sep)
LOCO_MIN, LOCO_MAX, LOCOS_MAX = 1, 15, 5   # §9
SCORE_MIN = 7                          # §11: 7 o más sobre 12
SIMILITUD_MAX = 0.7                    # palabras compartidas con una pregunta abierta
_LISTA_NEGRA = Path(__file__).with_name("lista_negra.txt")
_VACIAS = {"el", "la", "los", "las", "de", "del", "en", "a", "y", "o", "que", "un", "una", "se", "su", "sus", "por",
           "con", "para", "al", "mas", "antes", "este", "esta", "2026", "2027"}


def _plano(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def lista_negra() -> list[str]:
    return [_plano(l) for l in _LISTA_NEGRA.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def _palabras(q: str) -> set[str]:
    return {w for w in _plano(q).split() if w not in _VACIAS and len(w) > 2}


def parecida(pregunta: str, abiertas: list[str]) -> str | None:
    """La pregunta abierta que comparte ≥ 70 % de las palabras (Jaccard), si hay."""
    a = _palabras(pregunta)
    for q in abiertas:
        b = _palabras(q)
        if a and b and len(a & b) / len(a | b) >= SIMILITUD_MAX:
            return q
    return None


def revisar(prop: dict, ahora: datetime, vigentes: set[str], abiertas: list[str], locos_abiertos: int) -> str | None:
    """None si la propuesta pasa; si no, el motivo del primer filtro que falla."""
    doc, ev = prop.get("doc") or {}, prop.get("evidencia") or {}
    texto = " ".join(str(doc.get(k) or "") for k in ("question", "description", "resolution_criteria"))
    plano = f" {_plano(texto)} "
    for p in lista_negra():
        if f" {p} " in plano:
            return f"lista negra: «{p}» (tema sensible, §6)"
    try:
        specs, _ = cargar_texto(_yaml([doc]))
    except SchemaError as e:
        return "; ".join(e.errores)[:300]
    s = specs[0]
    if len(s.question) > QUESTION_MAX:
        return f"pregunta de {len(s.question)} caracteres (máximo {QUESTION_MAX})"
    if s.subcategory not in SUBCATEGORIAS_CONOCIDAS:
        return f"subcategoría desconocida «{s.subcategory}» (usar una de SUBCATEGORIAS_CONOCIDAS)"
    loco = bool(prop.get("loco"))
    if s.tipo == "binario":
        lo, hi = (LOCO_MIN, LOCO_MAX) if loco else (PRIOR_MIN, PRIOR_MAX)
        if not lo <= s.initial_yes_price <= hi:
            return f"precio inicial {s.initial_yes_price:g} fuera de {lo}–{hi}{' (loco)' if loco else ''} (§3)"
    dias = (s.ends_at - ahora).total_seconds() / 86400
    minimo, maximo = (3, 90) if s.tipo == "binario" else (7, 730 if loco else 183)
    if not minimo <= dias <= maximo:
        return f"cierra en {dias:.0f} días; el plazo permitido es de {minimo} a {maximo} (§5)"
    if not s.resolution_source_url:
        return "sin resolution_source_url (§6: fuente de resolución con URL)"
    faltan = [k for k in ("tendencia_url", "fuente_prior") if not ev.get(k)]
    if faltan:
        return f"falta evidencia: {', '.join(faltan)} (§12.2)"
    score = ev.get("score_total")
    if not isinstance(score, (int, float)) or score < SCORE_MIN:
        return f"score de calidad {score} < {SCORE_MIN} (§11)"
    if s.id in vigentes:
        return "ya existe un mercado con ese id"
    igual = parecida(s.question, abiertas)
    if igual:
        return f"duplicado de «{igual}» (§11)"
    if loco and locos_abiertos >= LOCOS_MAX:
        return f"ya hay {locos_abiertos} mercados locos abiertos (máximo {LOCOS_MAX}, §9)"
    return None


def revisar_lote(props: list[dict], ahora: datetime, vigentes: set[str], abiertas: list[str],
                 locos_abiertos: int) -> tuple[list[dict], list[dict]]:
    """(aceptadas en formato del plan, descartes). Cada aceptada cuenta para las
    siguientes: no entran dos casi iguales ni se rebasa el cupo de locos en un lote."""
    ok, desc = [], []
    abiertas = list(abiertas)
    for p in props:
        doc = p.get("doc") or {}
        motivo = revisar(p, ahora, vigentes, abiertas, locos_abiertos)
        grupo = doc.get("subcategory") or doc.get("category") or "?"
        if motivo:
            desc.append({"grupo": grupo, "titulo": doc.get("question") or doc.get("id") or "?", "motivo": motivo})
            continue
        ev = p.get("evidencia") or {}
        precio = (f"{doc['initial_yes_price']}%" if doc.get("tipo") == "binario"
                  else "/".join(str(o.get("pct")) for o in doc.get("outcomes") or []))
        ok.append({"doc": doc, "grupo": grupo, "titulo": doc["question"], "cuando": str(doc["ends_at"]),
                   "precio": precio, "nota": f"score {ev['score_total']}/12 · prior: {ev['fuente_prior']}"[:200],
                   "revisar": list(p.get("revisar") or []) + (["mercado loco"] if p.get("loco") else []),
                   "url": ev["tendencia_url"], "loco": bool(p.get("loco")), "evidencia": ev})
        vigentes = vigentes | {doc["id"]}
        abiertas.append(doc["question"])
        locos_abiertos += bool(p.get("loco"))
    return ok, desc

