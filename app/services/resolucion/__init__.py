"""Resolución mecánica de mercados deportivos (sin LLM).

- `fuentes`: clientes de solo lectura de ESPN (scoreboard, summary) y TheSportsDB
  (búsqueda por partido). Ambos gratuitos y sin API key.
- `cruce`: normalización de nombres, emparejado mercado ↔ partido y veredicto.
- `plan`: arma el plan de resoluciones (`resoluciones/AAAA-MM-DD.json`) que
  después valida y ejecuta `agent-resolver.py` (`check-plan`, `apply --yes`).

Regla: solo va al plan un 1X2 cuyo marcador final coincide en las DOS fuentes.
Todo lo demás (una sola fuente, aplazado, sin cruce claro, accesorios) sale como
escalado con la evidencia encontrada para que lo revise una persona.
"""
