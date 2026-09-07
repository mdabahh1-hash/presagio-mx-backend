---
name: resolver-mercados
description: Resuelve los mercados "por resolverse" de Veredikt - investiga resultados con doble fuente, presenta un reporte para aprobación de Mark, y solo tras su aprobación ejecuta las resoluciones vía API. Usar cuando Mark pida resolver mercados, la jornada, o revisar los pendientes de resolución.
---

# Resolver mercados de Veredikt

Eres el agente de mercados de Veredikt (veredikt.mx). Este flujo resuelve mercados en estado
`pending_resolution`. **Resolver es irreversible**: paga puntos a usuarios reales, escribe el
ledger, liquida ligas privadas y manda correos. La regla de oro es:

> **Solo se propone resolución con evidencia inequívoca confirmada por DOS fuentes
> independientes. Ante cualquier duda, discrepancia o criterio ambiguo: se ESCALA a Mark,
> jamás se adivina. Y NUNCA se ejecuta una resolución sin la aprobación explícita de Mark
> en esta conversación.**

Herramienta: `agent-resolver.py` en la raíz del repo backend
(`/Users/markdabah/Desktop/veredikt-mx-backend`). Todos los comandos se corren desde ahí.

## Paso 0 — Verificar el token

```
./venv/bin/python agent-resolver.py check-token
```

Si falla, pide a Mark regenerarlo (`./venv/bin/python generate-agent-token.py`) y detente.

## Paso 1 — Inventario

```
./venv/bin/python agent-resolver.py list
```

Devuelve JSON con todos los pendientes: pregunta, tipo (binary/multi), criterio de
resolución, fuente oficial, normas, outcomes con sus keys, volumen y núm. de operaciones.
Guárdalo en un archivo de trabajo (scratchpad) para no volver a pedirlo.

Clasifica los mercados en grupos de investigación:
- **Partidos** (kind=partido o pregunta "¿Quién gana...?"), agrupados por liga/subcategoría.
- **Accesorios** (titulares, goles, props NFL, fantasy) — necesitan datos finos (alineaciones,
  box scores), agrupados por liga.
- **No deportivos** (política, global, etc.) — investigación caso por caso.

## Paso 2 — Investigación en paralelo (subagentes)

Lanza subagentes de investigación **en paralelo** (uno por liga o grupo, tipo general-purpose
con búsqueda web). A cada uno pásale en el prompt:

1. La lista de sus mercados: id, pregunta, criterio de resolución, fuente oficial
   (`resolution_source_url`), normas y los `outcome_key` disponibles (en multi, la resolución
   se reporta como outcome_key exacto, ej. `home`/`draw`/`away`).
2. Instrucciones estrictas:
   - Buscar el resultado en la **fuente oficial** del mercado Y en **al menos otra fuente
     independiente** (ESPN, BBC Sport, Flashscore, web de la liga, medios serios). Anotar
     las URLs de ambas.
   - Aplicar el **criterio de resolución y las normas del mercado al pie de la letra**
     (ej. "resultado a los 90 minutos" ignora penales; zona horaria CDMX; qué pasa en
     aplazamientos).
   - Verificar que el evento realmente ya ocurrió y terminó. Si fue aplazado, suspendido
     o no encuentra confirmación clara → marcar `ESCALAR` con la razón.
   - Devolver por cada mercado: `id`, veredicto (`YES`/`NO`/outcome_key exacto o `ESCALAR`),
     resultado factual (ej. "Bayern 3-0 Schalke"), fuente 1 (URL), fuente 2 (URL),
     confianza (`alta` solo si ambas fuentes coinciden y el criterio aplica sin
     interpretación; si no, `media`/`baja`).

**Regla dura**: cualquier mercado con confianza que no sea `alta`, con fuentes que no
coinciden, o donde el subagente tuvo que interpretar el criterio → va a ESCALADOS.

## Paso 3 — Reporte para aprobación

Presenta a Mark (en el chat, legible):

1. **Tabla de propuestas** — mercado (pregunta corta + id), resolución propuesta,
   resultado factual, las 2 fuentes. Ordenada por liga/categoría. Marca con ⚠️ los que
   tienen volumen > 0 (afectan posiciones reales) y di cuántos usuarios/PT involucran.
2. **Escalados** — los que NO se proponen, con la razón (aplazado, fuentes discrepan,
   criterio ambiguo, sin información).
3. **Candidatos a limpieza** — vencidos sin ninguna operación que podrían borrarse con el
   script de limpieza (solo informar; este flujo no borra nada).

Luego **DETENTE y espera la aprobación explícita de Mark**. Acepta aprobación total
("aprueba todo") o parcial ("todo menos X y Y"). Si Mark corrige un veredicto, escálalo:
re-verifica antes de aceptar el cambio.

## Paso 4 — Ejecución (solo tras aprobación)

Por cada mercado aprobado:

```
./venv/bin/python agent-resolver.py resolve <id> --resolution YES
./venv/bin/python agent-resolver.py resolve <id> --resolution NO
./venv/bin/python agent-resolver.py resolve <id> --outcome <outcome_key>
```

- Ejecuta uno por uno verificando la salida (`RESUELTO ... posiciones liquidadas: N`).
- Si uno falla, anótalo y continúa con los demás; repórtalo al final.
- No re-intentes un `MARKET_ALREADY_RESOLVED`: márcalo como ya resuelto.

## Paso 5 — Reporte final

Resumen: cuántos se resolvieron (y posiciones liquidadas totales), cuáles fallaron y por
qué, cuáles quedaron escalados y qué necesita Mark decidir. Sugiere correr la limpieza si
hay candidatos.

## Prohibiciones permanentes

- Nunca resolver sin aprobación de Mark en la conversación actual.
- Nunca resolver con una sola fuente, con fuentes en desacuerdo, o interpretando un
  criterio ambiguo por cuenta propia.
- Nunca resolver un mercado cuyo evento no haya terminado (cierre ≠ evento terminado:
  los futuros de temporada cierran meses después).
- Nunca usar `--dangerously-skip-permissions`-style atajos ni tocar la BD directamente
  para resolver: siempre el endpoint del API, que liquida todo en una transacción.
