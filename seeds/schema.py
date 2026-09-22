"""Carga y validación de mercados-pendientes.yaml → lista de MarketSpec.

De app.* solo importa módulos puros de app/services/resolucion (sujeto.py, y
recetas.py de forma diferida): `sembrar-mercados.py validar` debe funcionar sin
BD ni SECRET_KEY y sin red (los ids del sujeto se buscan aparte con
`sembrar-mercados.py identificar`). Las categorías van como NOMBRE del enum
(POLITICA_MX, no "Política"); un test las ancla a app.models.market.MarketCategory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.services.resolucion.sujeto import normalizar_sujeto, requiere_sujeto, validar_sujeto
from market_content._common import binario_rules, multi_rules
from seeds.expand import expandir_partido
from seeds.plantillas import B_DEFAULT, SUBCATEGORIAS_CONOCIDAS

# Nombres del enum MarketCategory permitidos en mercados nuevos.
CATEGORIAS = {
    "POLITICA_MX", "ECONOMIA", "DEPORTES", "GLOBAL", "TECH", "ENTRETENIMIENTO",
    "CRYPTO", "MEXICO", "CLIMA",
}
# Existen en el enum pero no se siembran más (fusionadas en DEPORTES / retiradas;
# MERCADOS_GLOBALES fusionada en ECONOMIA el 2026-09-19, el frontend ya no la lista).
CATEGORIAS_PROHIBIDAS = {"MUNDIAL_2026", "BOXEO", "MOTOR", "MERCADOS_GLOBALES"}
TIPOS = {"binario", "multi", "partido"}
KINDS = {"partido", "accesorio"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,99}$")
KEY_RE = re.compile(r"^[a-z0-9_]+$")
RULES_MIN, CONTEXT_MIN, TEXT_MAX = 200, 120, 6000  # mismos umbrales que market_content.check()
# Largo máximo de la pregunta de un mercado nuevo (Mark, 2026-09-22): 70
# obligatorio, meta 65. El conteo es necesario pero no suficiente; la revisión
# final es `npm run titulos` en el repo raíz (veredikt.md §5).
QUESTION_MAX = 70
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
    auto_resolucion: dict | None = None  # receta mecánica (app/services/resolucion/recetas.py)
    sujeto: dict | None = None  # identidad del jugador de un accesorio (app/services/resolucion/sujeto.py)
    kickoff_at: datetime | None = None  # instante del evento; el atajo partido lo pone (= ends_at)


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


def _ends_at(valor, ctx: str, errores: list[str], campo: str = "ends_at",
             requerido: bool = True) -> datetime | None:
    """Fecha ISO 8601 con zona horaria → UTC. `campo` solo cambia los mensajes
    (también sirve para kickoff_at, opcional)."""
    if valor is None and not requerido:
        return None
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            errores.append(f"{ctx}: {campo} no es ISO 8601 ('2026-11-13T05:59:00Z')")
            return None
    if not isinstance(valor, datetime):
        errores.append(f"{ctx}: falta '{campo}'")
        return None
    if valor.tzinfo is None:
        errores.append(f"{ctx}: {campo} debe llevar zona horaria (termina en Z)")
        return None
    return valor.astimezone(timezone.utc)


def _normalizar(doc: dict, ctx: str, errores: list[str]) -> MarketSpec | None:
    antes = len(errores)
    ends_at = _ends_at(doc.get("ends_at"), ctx, errores)
    kickoff_at = _ends_at(doc.get("kickoff_at"), ctx, errores, campo="kickoff_at", requerido=False)

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

    sujeto = doc.get("sujeto")
    if isinstance(sujeto, dict):
        sujeto = normalizar_sujeto(sujeto)  # ids de YAML sin comillas (int) → str

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
        auto_resolucion=doc.get("auto_resolucion"), sujeto=sujeto, kickoff_at=kickoff_at,
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
            sugerencia = "ECONOMIA" if s.category == "MERCADOS_GLOBALES" else "DEPORTES + subcategory"
            e.append(f"{c}: categoría {s.category} prohibida para mercados nuevos (usa {sugerencia})")
        elif s.category not in CATEGORIAS:
            e.append(f"{c}: categoría desconocida '{s.category}' (nombres del enum: {', '.join(sorted(CATEGORIAS))})")
        # Aviso y no error: el límite es para mercados NUEVOS y aquí no se sabe si
        # ya existe (el YAML conserva los sembrados hasta el prune). Lo rechaza el
        # runner al insertar (seeds/runner.py).
        if len(s.question) > QUESTION_MAX:
            avisos.append(f"{c}: question > {QUESTION_MAX} chars ({len(s.question)}) — si es nuevo, `sembrar` lo "
                          f"rechaza; mueve la fecha y el umbral fino a description/rules")
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
        if s.auto_resolucion is not None:
            from app.services.resolucion.recetas import validar_receta

            for err in validar_receta(s.auto_resolucion, "binary" if s.tipo == "binario" else "multi"):
                e.append(f"{c}: auto_resolucion: {err}")
        elif s.b < B_DEFAULT:
            avisos.append(f"{c}: b={s.b:g} (el estándar actual es {B_DEFAULT:g})")
        if s.category == "DEPORTES" and not s.subcategory:
            e.append(f"{c}: DEPORTES requiere subcategory")
        if s.kind is not None and (s.category != "DEPORTES" or s.kind not in KINDS):
            e.append(f"{c}: kind solo puede ser 'partido'|'accesorio' y solo en DEPORTES")
        # Hora del evento: la landing de Deportes agrupa la jornada con ella. En un
        # partido es obligatoria (el atajo `tipo: partido` la deriva del kickoff).
        if s.kickoff_at is not None and s.category != "DEPORTES":
            e.append(f"{c}: kickoff_at solo va en DEPORTES")
        if s.kind == "partido" and s.kickoff_at is None:
            e.append(f"{c}: kind: partido requiere kickoff_at (hora del evento en UTC; el atajo `tipo: partido` lo pone solo)")
        if s.kickoff_at is not None and s.kickoff_at > s.ends_at:
            e.append(f"{c}: kickoff_at ({s.kickoff_at:%Y-%m-%dT%H:%M}Z) no puede ser posterior a ends_at")
        if s.kind == "accesorio" and (s.sujeto or {}).get("alcance") == "partido" and s.kickoff_at is None:
            avisos.append(f"{c}: accesorio de partido sin kickoff_at (la landing usará ends_at como hora del partido)")
        # Accesorio de jugador (touchdown / pases / fantasy / titular / gol en una
        # liga con fuente automática): sin sujeto con ids el job resolvería por
        # nombre y podría tomar a un homónimo (caso Josh Allen, Semana 1 de 2026).
        spec = requiere_sujeto(s.category, s.tipo, s.subcategory, s.question)
        if spec:
            if s.kind != "accesorio":
                e.append(f"{c}: accesorio de jugador ({spec['tipo']}) requiere kind: accesorio")
            if not s.sujeto:
                e.append(f"{c}: accesorio de jugador sin 'sujeto' {{jugador, equipo, rival, posicion, alcance, ids}}: "
                         f"escribe jugador/equipo/rival/alcance y llena los ids con "
                         f"`sembrar-mercados.py identificar --only {c} --apply`")
            else:
                e += [f"{c}: sujeto: {x}" for x in validar_sujeto(spec, s.sujeto, s.subcategory)]
        elif s.sujeto is not None:
            e.append(f"{c}: 'sujeto' solo va en binarios de accesorio de jugador (touchdown / pases de TD / "
                     "fantasy / titular / gol) de una liga con fuente automática")
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
