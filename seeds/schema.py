"""Carga y validación de mercados-pendientes.yaml → lista de MarketSpec.

No importa nada de app.* a propósito: `sembrar-mercados.py validar` debe
funcionar sin BD ni SECRET_KEY. Las categorías van como NOMBRE del enum
(POLITICA_MX, no "Política"); un test las ancla a app.models.market.MarketCategory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from market_content._common import binario_rules, multi_rules
from seeds.expand import expandir_partido
from seeds.plantillas import B_DEFAULT, SUBCATEGORIAS_CONOCIDAS

# Nombres del enum MarketCategory permitidos en mercados nuevos.
CATEGORIAS = {
    "POLITICA_MX", "ECONOMIA", "DEPORTES", "GLOBAL", "TECH", "ENTRETENIMIENTO",
    "CRYPTO", "MERCADOS_GLOBALES", "MEXICO", "CLIMA",
}
# Existen en el enum pero no se siembran más (fusionadas en DEPORTES / retiradas).
CATEGORIAS_PROHIBIDAS = {"MUNDIAL_2026", "BOXEO", "MOTOR"}
TIPOS = {"binario", "multi", "partido"}
KINDS = {"partido", "accesorio"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,99}$")
KEY_RE = re.compile(r"^[a-z0-9_]+$")
RULES_MIN, CONTEXT_MIN, TEXT_MAX = 200, 120, 6000  # mismos umbrales que market_content.check()
CAMPOS_TEXTO = ("id", "question", "description", "category", "resolution_criteria", "context")


@dataclass
class OutcomeSpec:
    key: str
    label: str
    pct: float


@dataclass
class MarketSpec:
    id: str
    tipo: str  # "binario" | "multi" (un partido ya llega expandido a multi)
    question: str
    description: str
    category: str  # NOMBRE del enum; el runner hace MarketCategory[category]
    resolution_criteria: str
    rules: str
    context: str
    ends_at: datetime  # tz-aware, UTC
    subcategory: str | None = None
    kind: str | None = None
    image_url: str | None = None
    resolution_source_url: str | None = None
    b: float = B_DEFAULT
    trending: bool = False
    initial_yes_price: float | None = None
    outcomes: list[OutcomeSpec] = field(default_factory=list)
    origen: str = ""  # "partido" si vino del atajo (solo para el reporte)


class SchemaError(Exception):
    def __init__(self, errores: list[str]):
        super().__init__("\n".join(errores))
        self.errores = errores


def cargar(path: str | Path) -> tuple[list[MarketSpec], list[str]]:
    """Lee el stream YAML, expande partidos, normaliza y valida.

    Devuelve (specs, avisos). Lanza SchemaError con TODOS los errores encontrados.
    """
    texto = Path(path).read_text(encoding="utf-8")
    return cargar_texto(texto)


def cargar_texto(texto: str) -> tuple[list[MarketSpec], list[str]]:
    try:
        docs = [d for d in yaml.safe_load_all(texto) if d is not None]
    except yaml.YAMLError as e:
        raise SchemaError([f"YAML inválido: {e}"]) from e

    errores: list[str] = []
    avisos: list[str] = []
    specs: list[MarketSpec] = []
    for i, doc in enumerate(docs, 1):
        if not isinstance(doc, dict):
            errores.append(f"doc #{i}: no es un mapa YAML")
            continue
        ctx = f"doc #{i} ({doc.get('id') or '?'})"
        if doc.get("tipo") not in TIPOS:
            errores.append(f"{ctx}: falta 'tipo' o no es binario|multi|partido")
            continue
        if doc["tipo"] == "partido":
            try:
                doc = expandir_partido(doc)
            except (KeyError, ValueError, TypeError) as e:
                errores.append(f"{ctx}: partido inválido: {e}")
                continue
        spec = _normalizar(doc, ctx, errores)
        if spec is not None:
            specs.append(spec)
    errores += _validar(specs, avisos)
    if errores:
        raise SchemaError(errores)
    return specs, avisos


def _ends_at(valor, ctx: str, errores: list[str]) -> datetime | None:
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            errores.append(f"{ctx}: ends_at no es ISO 8601 ('2026-11-13T05:59:00Z')")
            return None
    if not isinstance(valor, datetime):
        errores.append(f"{ctx}: falta 'ends_at'")
        return None
    if valor.tzinfo is None:
        errores.append(f"{ctx}: ends_at debe llevar zona horaria (termina en Z)")
        return None
    return valor.astimezone(timezone.utc)


def _normalizar(doc: dict, ctx: str, errores: list[str]) -> MarketSpec | None:
    antes = len(errores)
    ends_at = _ends_at(doc.get("ends_at"), ctx, errores)

    for k in CAMPOS_TEXTO:
        if not doc.get(k):
            errores.append(f"{ctx}: falta '{k}'")

    rules = doc.get("rules")
    cuerpo = doc.get("rules_cuerpo")
    if cuerpo and rules:
        errores.append(f"{ctx}: usa 'rules' O 'rules_cuerpo', no ambos")
    elif cuerpo and ends_at is not None:
        helper = binario_rules if doc["tipo"] == "binario" else multi_rules
        rules = helper(str(cuerpo), ends_at.isoformat(), como=doc.get("rules_como"))
    if not rules and not cuerpo:
        errores.append(f"{ctx}: falta 'rules' (o 'rules_cuerpo' + 'rules_como')")

    outcomes: list[OutcomeSpec] = []
    for o in doc.get("outcomes") or []:
        if not isinstance(o, dict):
            errores.append(f"{ctx}: cada outcome debe ser un mapa {{key, label, pct}}")
            continue
        try:
            pct = float(o.get("pct"))
        except (TypeError, ValueError):
            errores.append(f"{ctx}: outcome '{o.get('key')}' sin pct numérico")
            pct = 0.0
        outcomes.append(OutcomeSpec(str(o.get("key") or ""), str(o.get("label") or ""), pct))

    try:
        b = float(doc.get("b", B_DEFAULT))
    except (TypeError, ValueError):
        errores.append(f"{ctx}: b no es numérico")
        b = B_DEFAULT
    prior = doc.get("initial_yes_price")
    if prior is not None:
        try:
            prior = float(prior)
        except (TypeError, ValueError):
            errores.append(f"{ctx}: initial_yes_price no es numérico")
            prior = None

    if len(errores) > antes or ends_at is None:
        return None
    return MarketSpec(
        id=str(doc["id"]), tipo=doc["tipo"], question=str(doc["question"]).strip(),
        description=str(doc["description"]).strip(), category=str(doc["category"]),
        resolution_criteria=str(doc["resolution_criteria"]).strip(), rules=str(rules).strip(),
        context=str(doc["context"]).strip(), ends_at=ends_at,
        subcategory=doc.get("subcategory"), kind=doc.get("kind"), image_url=doc.get("image_url"),
        resolution_source_url=doc.get("resolution_source_url"), b=b,
        trending=bool(doc.get("trending", False)), initial_yes_price=prior,
        outcomes=outcomes, origen=str(doc.get("_origen", "")),
    )


def _validar(specs: list[MarketSpec], avisos: list[str]) -> list[str]:
    e: list[str] = []
    vistos: set[str] = set()
    for s in specs:
        c = s.id
        if s.id in vistos:
            e.append(f"{c}: id duplicado en el archivo")
        vistos.add(s.id)
        if not ID_RE.match(s.id):
            e.append(f"{c}: id inválido (kebab-case ascii, 3-100 chars: ^[a-z0-9][a-z0-9-]{{2,99}}$)")
        if s.category in CATEGORIAS_PROHIBIDAS:
            e.append(f"{c}: categoría {s.category} prohibida para mercados nuevos (usa DEPORTES + subcategory)")
        elif s.category not in CATEGORIAS:
            e.append(f"{c}: categoría desconocida '{s.category}' (nombres del enum: {', '.join(sorted(CATEGORIAS))})")
        if len(s.question) > 500:
            e.append(f"{c}: question > 500 chars")
        if len(s.rules) < RULES_MIN:
            e.append(f"{c}: rules < {RULES_MIN} chars ({len(s.rules)})")
        if len(s.context) < CONTEXT_MIN:
            e.append(f"{c}: context < {CONTEXT_MIN} chars ({len(s.context)})")
        if len(s.rules) > TEXT_MAX or len(s.context) > TEXT_MAX:
            e.append(f"{c}: rules/context > {TEXT_MAX} chars")
        if s.resolution_source_url is None and not s.rules.startswith("Cómo se resuelve:"):
            e.append(f"{c}: sin resolution_source_url las rules deben abrir con 'Cómo se resuelve:' (usa rules_como)")
        if s.resolution_source_url and not str(s.resolution_source_url).startswith("https://"):
            e.append(f"{c}: resolution_source_url debe ser https://")
        if s.image_url and not (str(s.image_url).startswith("https://") or str(s.image_url).startswith("/img/")):
            e.append(f"{c}: image_url debe ser https:// o /img/…")
        if s.b <= 0:
            e.append(f"{c}: b debe ser > 0")
        elif s.b < B_DEFAULT:
            avisos.append(f"{c}: b={s.b:g} (el estándar actual es {B_DEFAULT:g})")
        if s.category == "DEPORTES" and not s.subcategory:
            e.append(f"{c}: DEPORTES requiere subcategory")
        if s.kind is not None and (s.category != "DEPORTES" or s.kind not in KINDS):
            e.append(f"{c}: kind solo puede ser 'partido'|'accesorio' y solo en DEPORTES")
        if s.subcategory and s.subcategory not in SUBCATEGORIAS_CONOCIDAS:
            avisos.append(f"{c}: subcategoría nueva '{s.subcategory}' → agregarla al frontend "
                          "src/lib/categories.ts (SUBCATEGORIES y, si es deporte, SPORT_GROUPS)")
        if s.tipo == "binario":
            if s.outcomes:
                e.append(f"{c}: un binario no lleva outcomes")
            if s.initial_yes_price is None or not 1 <= s.initial_yes_price <= 99:
                e.append(f"{c}: initial_yes_price debe estar entre 1 y 99")
        else:
            if s.initial_yes_price is not None:
                e.append(f"{c}: un multi no lleva initial_yes_price")
            if len(s.outcomes) < 2:
                e.append(f"{c}: un multi necesita al menos 2 outcomes")
            keys = [o.key for o in s.outcomes]
            if len(set(keys)) != len(keys):
                e.append(f"{c}: outcome keys repetidas")
            for o in s.outcomes:
                if not KEY_RE.match(o.key):
                    e.append(f"{c}: key '{o.key}' inválida (^[a-z0-9_]+$)")
                if not o.label or len(o.label) > 200:
                    e.append(f"{c}: label de '{o.key}' vacío o > 200 chars")
                if not 0 < o.pct < 100:
                    e.append(f"{c}: pct de '{o.key}' debe estar entre 0 y 100 (exclusivo)")
            if s.outcomes:
                total = sum(o.pct for o in s.outcomes)
                if abs(total - 100) > 0.5:
                    e.append(f"{c}: los pct suman {total:g}, deben sumar 100")
    return e
