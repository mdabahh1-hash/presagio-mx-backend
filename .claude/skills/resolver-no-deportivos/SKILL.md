---
name: resolver-no-deportivos
description: Resuelve a mano (con Claude Code, solo cuando Mark lo pide) los mercados NO deportivos que el job mecánico escaló "sin receta" - lee la fuente que citan las normas y UNA fuente confiable de la lista cerrada, arma el plan y lo propone por correo. Usar cuando Mark diga "resuelve los no deportivos", "revisa los escalados sin receta" o nombre mercados de política, economía, cripto, clima, entretenimiento o global.
---

# Resolver mercados no deportivos

Complemento de `resolver-mercados` (léela para token, `check-plan`, `proponer` y prohibiciones).
Aquí no hay fuentes mecánicas: **cada mercado se lee a mano**, con presupuesto fijo, y termina en el
mismo correo de aprobación. Esto **no corre solo**: Mark avisa cuándo (decisión 12-sep-2026, para no
gastar API ni tokens sin necesidad).

## Qué llega aquí

El job de las 06:00 y 18:00 CDMX (`app/services/resolucion/`) resuelve solo:
- deportes (ESPN + TheSportsDB / UEFA / CBS), y
- no deportivos **con receta** (`auto_resolucion`: cierres cripto, dominancia, stablecoins, tasas Fed y
  Banxico, órdenes ejecutivas; ver `app/services/resolucion/recetas.py` y `recetas-*.yaml`).

Todo no deportivo **sin receta** sale en el correo como "sin receta: resolver con la skill
resolver-no-deportivos" (el correo dice cuántos). Eso es lo que se trabaja aquí.

## Paso 1 — Inventario

```
./venv/bin/python agent-resolver.py check-token
./venv/bin/python agent-resolver.py list --sin-deportes --out <scratchpad>/nodep.json
```

Solo `status == pending_resolution` (ya cerrados). Si Mark nombra ids, limítate a esos. Los que tienen
`auto_resolucion` ya los evaluó el job: si están escalados por "una sola fuente", confírmalos con UNA
página confiable (Paso 3) en vez de investigar desde cero.

## Paso 2 — Clasificar por tipo (lo dicen `rules` y `resolution_criteria`)

- **dato publicado**: tasa, inflación, precio, escaños, participación, aprobación, conteo.
- **hecho positivo**: X ocurrió (firma, anuncio, ratificación, huracán tocó tierra, prueba nuclear,
  mención en un discurso, pelea, canción en la mañanera).
- **ausencia**: "¿pasará X antes de la fecha?" y no pasó.
- **cargo al cierre**: ¿sigue siendo PM/presidente/canciller al 31-dic?

## Paso 3 — Dos lecturas por mercado, nunca más de cinco llamadas

1. **Fuente 1 = la de las normas**: `resolution_source_url` o la página oficial nombrada en `rules`.
   Un `WebFetch` con un prompt que pida el dato exacto y la **cita textual** (fecha, cifra, nombre,
   frase). Sin `resolution_source_url`: un `WebSearch` para hallar la página oficial nombrada en las
   normas y un `WebFetch` a esa página.
2. **Fuente 2 = UNA fuente confiable de la lista cerrada** `FUENTES_CONFIABLES` en
   `app/services/resolucion/validar.py` (Reuters, AP, Bloomberg, FT, BBC, NYT, WSJ, El País; El
   Universal, Reforma, Milenio, El Financiero, El Economista, Expansión, Animal Político, Proceso,
   Aristegui; CoinMarketCap, CoinGecko, DefiLlama, TradingView, Investing, Yahoo Finance, NHC, FRED;
   dominios oficiales `.gob.mx`, `.gov`, `.gov.uk`, `.gouv.fr`, `europa.eu`, `un.org`, bancos
   centrales e institutos electorales). Un `WebFetch`; si hace falta localizarla, un `WebSearch`
   antes. `check-plan` rechaza cualquier `fuente_2` fuera de la lista y exige que una de las dos sea
   la oficial de las normas.
3. **Presupuesto**: máximo 3 `WebFetch` + 2 `WebSearch` por mercado. Si no alcanza → escalado con lo
   que se leyó. **Nunca subagentes** (10-sep-2026: ~8k tokens por mercado, agotó la sesión).
4. Nunca usar el resumen de `WebSearch` como evidencia: siempre abrir la página.

## Paso 4 — Veredicto por tipo

| tipo | ambas fuentes coinciden | qué va al plan |
|---|---|---|
| dato publicado / hecho positivo | sí, y el criterio aplica literal | `resoluciones`, `confianza: alta`, `resultado` = cita + fecha |
| ausencia (no pasó) | — | **siempre** `escalados`: `veredicto_sugerido: NO`, `razon` = qué se buscó y no apareció, `evidencia` (URLs), `citas` |
| cargo al cierre | sí y la fecha ya pasó | como hecho positivo (página oficial del cargo + un medio) |
| normas mandan cancelar (evento cancelado, dato no publicado, empate) | dos fuentes lo prueban | `veredicto: CANCELAR`; con una sola → escalado `veredicto_sugerido: CANCELAR` |
| discrepancia, criterio interpretable, ventana no cerrada | — | `escalados` con la razón |

Multi (`market_type == multi`): `veredicto` = `outcome_key` exacto del listado.

Regla de Mark: **un NO por ausencia nunca entra al botón**; él lo decide desde el correo o /admin.

## Paso 5 — Plan y propuesta

`resoluciones/AAAA-MM-DD-nodep.json` (formato de `resolver-mercados`; en `escalados` agrega
`evidencia: [urls]` y `citas: [texto]`, el correo y la página los muestran):

```
./venv/bin/python agent-resolver.py check-plan resoluciones/AAAA-MM-DD-nodep.json
./venv/bin/python agent-resolver.py proponer  resoluciones/AAAA-MM-DD-nodep.json
```

Detente: Mark aprueba desde el correo. Commit del JSON
(`Resoluciones AAAA-MM-DD: N no deportivos propuestos (plan #N)`). Reporta al final cuántas páginas
se leyeron y qué quedó escalado y por qué.

## Recetas nuevas

Si al resolver a mano descubres que un mercado era de dato publicado con API libre, propón la receta
(`auto_resolucion`) para los mercados futuros del mismo tipo en `mercados-pendientes.yaml`, o aplícala
a los ya sembrados con `agent-resolver.py recetas <archivo.yaml> --apply`. Tokens gratuitos pendientes
de registrar por Mark: `BANXICO_TOKEN` (SieAPIRest) e `INEGI_TOKEN`; sin ellos las recetas
`banxico_tasa` / `inegi_inflacion` salen escaladas con "falta token".
