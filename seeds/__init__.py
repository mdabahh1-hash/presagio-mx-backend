"""Sembrador declarativo de mercados (ver sembrar-mercados.py y mercados-pendientes.yaml).

Módulos:
- plantillas: tabla COMPETENCIAS (atajo `partido`) y subcategorías conocidas.
- schema:     carga + validación del YAML → lista de MarketSpec.
- expand:     `tipo: partido` → documento multi completo.
- runner:     inserción idempotente en la BD (importa app.*).
- prune:      quita del YAML los mercados ya terminados (a nivel texto).
"""
