# Seeds históricos (congelados)

Scripts `seed-markets-*.py` que ya se ejecutaron en prod (junio–septiembre 2026). Se conservan solo como registro de qué se sembró y con qué textos; **no volver a correrlos** ni usarlos de plantilla.

Desde 2026-09-09 los mercados nuevos van como documentos YAML en `mercados-pendientes.yaml` (raíz del backend) y se siembran con `sembrar-mercados.py`. Ver `veredikt.md` §5.

Nota: estos scripts hacen `sys.path.insert(0, dirname(__file__))`, así que desde esta carpeta ya no encuentran el paquete `app` — a propósito.
