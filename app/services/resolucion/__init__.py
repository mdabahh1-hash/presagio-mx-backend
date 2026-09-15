"""Resolución mecánica de mercados deportivos (sin LLM).

- `fuentes`: clientes de solo lectura de ESPN (scoreboard, summary) y TheSportsDB
  (búsqueda por partido). Ambos gratuitos y sin API key.
- `cruce`: normalización de nombres, emparejado mercado ↔ partido y veredicto.
- `plan`: arma el plan de resoluciones (`resoluciones/AAAA-MM-DD.json`) que
  después valida y ejecuta `agent-resolver.py` (`check-plan`, `apply --yes`).

- `sujeto` / `identidad`: identidad del jugador de un accesorio (columna
  markets.sujeto: equipo, rival e ids por fuente) y su búsqueda con red al sembrar.

Regla: solo va al plan lo que coincide en las DOS fuentes (1X2 por marcador;
accesorios de jugador con identidad confirmada por id en ambas). Todo lo demás
(una sola fuente, aplazado, sin cruce claro, sin sujeto, homónimos, jugador
ausente) sale como escalado con la evidencia encontrada para que lo revise una
persona; si la identidad no quedó confirmada, sin veredicto sugerido.
"""
