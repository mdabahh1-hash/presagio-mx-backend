"""Escaleras de Crypto: el umbral que lee la landing sale de la pregunta.

La API no expone auto_resolucion, así que la landing de Crypto (veredikt-mx,
src/components/crypto/escalera.ts) reconoce una escalera por la redacción
«cerrará(n) <mes> en US$N [millones | mil millones] o más» y toma N de ahí. Este test garantiza que,
en todo mercado del YAML con esa redacción, N es exactamente el umbral con el que
el job lo resuelve (auto_resolucion.valor) y el mes es el de ends_at.
"""
import re
from datetime import datetime
from pathlib import Path

import yaml

YAML = Path(__file__).resolve().parents[1] / "mercados-pendientes.yaml"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
# Espejo exacto de LADDER_RE en src/components/crypto/escalera.ts
LADDER_RE = re.compile(r"cerrarán? (" + "|".join(MESES) + r") en US\$([\d,]+(?:\.\d+)?)( mil millones| millones)? o más")


def umbral(question: str) -> tuple[str, float] | None:
    m = LADDER_RE.search(question)
    if not m:
        return None
    n = float(m.group(2).replace(",", ""))
    return m.group(1), n * {" mil millones": 1e9, " millones": 1e6}.get(m.group(3) or "", 1)


def test_regex_de_ejemplo():
    assert umbral("¿Bitcoin cerrará septiembre en US$80,000 o más?") == ("septiembre", 80000)
    assert umbral("¿La capitalización de las stablecoins cerrará septiembre en US$310,500 millones o más?") == ("septiembre", 310_500e6)
    # redacción corta desde octubre-2026 (70 caracteres): miles de millones
    assert umbral("¿Las stablecoins cerrarán octubre en US$312 mil millones o más?") == ("octubre", 312e9)
    # Redacciones de los mercados de fin de año ya sembrados: no son escalera
    assert umbral("¿Bitcoin cerrará 2026 en US$100,000 o más?") is None
    assert umbral("¿Bitcoin alcanzará US$120,000 en algún momento entre el 27 de agosto y el 31 de diciembre?") is None


def test_escaleras_del_yaml_coinciden_con_la_receta():
    docs = [d for d in yaml.safe_load_all(YAML.read_text(encoding="utf-8")) if d]
    for d in docs:
        if d.get("category") != "CRYPTO" or d.get("tipo") != "binario":
            continue
        u = umbral(d["question"])
        if u is None:
            continue
        mes, n = u
        receta = d.get("auto_resolucion")
        assert receta, f"{d['id']}: redacción de escalera sin auto_resolucion"
        assert receta["op"] == ">=", f"{d['id']}: «o más» exige op >="
        assert float(receta["valor"]) == n, f"{d['id']}: pregunta dice {n:,.0f}, receta {receta['valor']}"
        ends = d["ends_at"] if isinstance(d["ends_at"], datetime) else datetime.fromisoformat(str(d["ends_at"]).replace("Z", "+00:00"))
        assert MESES[ends.month - 1] == mes, f"{d['id']}: la pregunta dice {mes}, ends_at es {ends:%Y-%m}"
