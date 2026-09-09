"""Quitar de mercados-pendientes.yaml los mercados que ya terminaron.

Un mercado "terminó" si en la BD está RESOLVED / RESOLVED_YES / RESOLVED_NO /
CANCELLED, o si ya no existe Y su ends_at pasó (lo borró el cleanup de
vencidos sin actividad). Si no existe pero su ends_at es futuro, está pendiente
de sembrar y se queda.

La poda es a nivel texto: se parte el archivo por líneas `---` a solas y se
reúnen los trozos supervivientes byte a byte, así comentarios y formato quedan
intactos. Las funciones puras no importan app.*; `clasificar` sí.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import yaml

SEP = re.compile(r"^---\s*$")
ESTADOS_FINALES = {"RESOLVED", "RESOLVED_YES", "RESOLVED_NO", "CANCELLED"}


def partir_documentos(texto: str) -> list[str]:
    """Trozos crudos. Trozo 0 = cabecera antes del primer '---' (puede ser '');
    cada trozo siguiente empieza con su línea '---'.
    Invariante: ''.join(partir_documentos(t)) == t."""
    trozos: list[str] = []
    actual: list[str] = []
    for linea in texto.splitlines(keepends=True):
        if SEP.match(linea):
            trozos.append("".join(actual))
            actual = [linea]
        else:
            actual.append(linea)
    trozos.append("".join(actual))
    return trozos


def id_de_trozo(trozo: str) -> str | None:
    """id del documento del trozo, o None si es cabecera / solo comentarios."""
    doc = yaml.safe_load(trozo)
    return str(doc["id"]) if isinstance(doc, dict) and "id" in doc else None


def quitar_documentos(texto: str, ids: set[str]) -> str:
    """Texto sin los documentos cuyo id esté en `ids`; el resto va byte a byte."""
    return "".join(t for t in partir_documentos(texto) if id_de_trozo(t) not in ids)


@dataclass
class Veredicto:
    id: str
    terminado: bool
    motivo: str


async def clasificar(specs, db, now: datetime) -> list[Veredicto]:
    from sqlalchemy import select

    from app.models.market import Market

    ids = [s.id for s in specs]
    estado: dict[str, str] = {}
    if ids:
        rows = (await db.execute(select(Market.id, Market.status).where(Market.id.in_(ids)))).all()
        estado = {mid: st.name for mid, st in rows}
    out: list[Veredicto] = []
    for s in specs:
        st = estado.get(s.id)
        if st in ESTADOS_FINALES:
            out.append(Veredicto(s.id, True, st))
        elif st is None and s.ends_at < now:
            out.append(Veredicto(s.id, True, "no existe y ya venció (borrado por cleanup)"))
        elif st is None:
            out.append(Veredicto(s.id, False, "pendiente de sembrar"))
        else:
            out.append(Veredicto(s.id, False, f"activo ({st})"))
    return out
