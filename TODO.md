# TODO / Deuda técnica

## Contabilidad de balances en float

Los balances de usuarios (`users.points`), costos de trades y el ledger
(`points_ledger.delta`) se almacenan y operan como `float` (float8 en
PostgreSQL). **Aceptable con puntos virtuales** — los errores de redondeo son
del orden de 1e-9 PT y no hay dinero real en juego.

**Antes de migrar a dinero real o cripto**: los balances y movimientos de
usuarios deben migrar a `Decimal`/enteros en unidad mínima (p. ej. centavos o
micro-unidades), con columnas `NUMERIC` en la BD y validación exacta en el
pipeline de dinero. La curva LMSR (`app/core/lmsr.py`) puede permanecer en
float — usa exp/ln y su salida se convierte en el borde; lo que debe ser exacto
es la contabilidad (cargos, abonos, saldos), no la cotización.

Contexto: el endpoint `GET /markets/{id}/quote` ya define un único borde de
redondeo para display y los tests (`tests/test_quote.py`) verifican los
invariantes con `Decimal` en la serialización.
