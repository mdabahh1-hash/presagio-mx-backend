"""Agente de siembra: generadores (partidos, cripto, …) → plan → correo con casillas.

Cada generador devuelve propuestas {doc, grupo, titulo, cuando, precio, nota,
revisar, url} y descartes {grupo, titulo, motivo}; `vista` los lee para el correo
y la página de aprobación.
"""


def vista(x: dict) -> dict:
    """Campos para mostrar. Tolera el formato de los primeros planes de partidos
    (liga/local/visitante/kickoff/cuotas/tabla, plan #1 del 24-sep-2026)."""
    if "titulo" in x:
        return x
    tabla = "/".join(map(str, x["tabla"])) if x.get("tabla") else "—"
    return {**x, "grupo": x.get("liga", ""), "titulo": x.get("partido") or f"{x['local']} vs {x['visitante']}",
            "cuando": x.get("kickoff"), "precio": "/".join(map(str, x["cuotas"])) if x.get("cuotas") else "",
            "nota": f"tabla {tabla}" if x.get("cuotas") else ""}
