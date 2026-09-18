# Scripts históricos (congelados)

Scripts de un solo uso que ya se ejecutaron en prod (junio–septiembre 2026): seeds (`seed-markets-*.py`, `seed-categorias-*.py`), backfills (`backfill-*.py`), fixes (`fix-and-seed-*.py`) y limpiezas (`cleanup-*.py`). Se conservan solo como registro de qué se corrió y con qué textos/datos; **no volver a correrlos** ni usarlos de plantilla.

Desde 2026-09-09 los mercados nuevos van como documentos YAML en `mercados-pendientes.yaml` (raíz del backend) y se siembran con `scripts/sembrar-mercados.py`. Ver `veredikt.md` §5.

Nota: estos scripts hacen `sys.path.insert(0, dirname(__file__))`, así que desde esta carpeta ya no encuentran el paquete `app` — a propósito.
