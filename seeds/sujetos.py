"""Reescribir el bloque `sujeto:` de un documento de mercados-pendientes.yaml.

Lo usa `sembrar-mercados.py identificar --apply` para guardar los ids hallados.
Trabaja a nivel texto sobre un trozo de `seeds.prune.partir_documentos`: quita
el bloque top-level `sujeto:` (si existe) y pone en su lugar el volcado YAML
del sujeto nuevo; comentarios y el resto del documento quedan intactos. Puro.
"""
from __future__ import annotations

import re

import yaml

_RE_SUJETO = re.compile(r"^sujeto\s*:")


def _en_bloque(lineas: list[str], i: int) -> bool:
    """La línea i sigue dentro de un bloque top-level: indentada, o en blanco con
    una línea indentada después (antes de la siguiente clave o del final)."""
    linea = lineas[i]
    if linea.startswith((" ", "\t")):
        return True
    if linea.strip():
        return False
    for siguiente in lineas[i + 1:]:
        if siguiente.strip():
            return siguiente.startswith((" ", "\t"))
    return False


def volcar_sujeto(sujeto: dict) -> str:
    """`sujeto:` en YAML de bloque; los ids quedan entre comillas (string)."""
    return yaml.safe_dump({"sujeto": sujeto}, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000)


def reemplazar_bloque_sujeto(trozo: str, sujeto: dict) -> str:
    """Trozo con `sujeto` reemplazado (o agregado al final del documento).
    Verifica que el resultado cargue igual salvo `sujeto`; si no, ValueError."""
    lineas = trozo.splitlines(keepends=True)
    bloque = volcar_sujeto(sujeto)
    ini = next((i for i, linea in enumerate(lineas) if _RE_SUJETO.match(linea)), None)
    if ini is not None:
        fin = ini + 1
        while fin < len(lineas) and _en_bloque(lineas, fin):
            fin += 1
        nuevas = lineas[:ini] + [bloque] + lineas[fin:]
    else:
        k = len(lineas)
        while k > 0 and not lineas[k - 1].strip():
            k -= 1
        antes = lineas[:k]
        if antes and not antes[-1].endswith("\n"):
            antes[-1] += "\n"
        nuevas = antes + [bloque] + lineas[k:]
    nuevo = "".join(nuevas)

    viejo_doc, nuevo_doc = yaml.safe_load(trozo), yaml.safe_load(nuevo)
    resto = lambda d: {k: v for k, v in (d or {}).items() if k != "sujeto"}  # noqa: E731
    if not isinstance(nuevo_doc, dict) or nuevo_doc.get("sujeto") != sujeto or resto(nuevo_doc) != resto(viejo_doc):
        raise ValueError("no pude reescribir el bloque 'sujeto' sin alterar el resto del documento")
    return nuevo
