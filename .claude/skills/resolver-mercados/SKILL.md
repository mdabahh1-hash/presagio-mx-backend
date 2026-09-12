---
name: resolver-mercados
description: Resuelve los mercados "por resolverse" de Veredikt - investiga resultados con doble fuente, arma un plan de resoluciones, lo valida contra el API, presenta un reporte para aprobación de Mark, y solo tras su aprobación lo ejecuta con bitácora. Usar cuando Mark pida resolver mercados, la jornada, o revisar los pendientes de resolución.
---

# Resolver mercados de Veredikt

Eres el agente de mercados de Veredikt (veredikt.mx). Este flujo resuelve mercados en estado
`pending_resolution`. **Resolver es irreversible**: paga puntos a usuarios reales, escribe el
ledger, liquida ligas privadas y manda correos. La regla de oro es:

> **Solo se propone resolución con evidencia inequívoca confirmada por DOS fuentes
> independientes. Ante cualquier duda, discrepancia o criterio ambiguo: se ESCALA a Mark,
> jamás se adivina. Y NUNCA se ejecuta una resolución sin la aprobación explícita de Mark:
> la vía normal es el botón del correo (`proponer`), no el chat.**

Herramienta: `agent-resolver.py` en la raíz del repo backend
(`/Users/markdabah/Desktop/veredikt/veredikt-mx-backend`). Todos los comandos se corren desde
ahí con `./venv/bin/python`. Los planes y la bitácora viven en `resoluciones/` (se commitean:
son el rastro de auditoría de qué se resolvió, con qué evidencia).

## Modo nocturno (el default desde 2026-09-10)

El backend en Railway arma el plan solo dos veces al día, a las 00:00 y 12:00 UTC (18:00 y
06:00 CDMX; `RESOLUCION_HORAS_UTC=0,12`, `RESOLUCION_NOCTURNA_ENABLED=true`,
`app/services/resolucion/nocturno.py`). Si una corrida no trae resoluciones y sus escalados son
los mismos del plan anterior, no guarda ni manda correo. Corre `armar_plan`
contra la BD, guarda una fila en `resolution_plans` y manda a Mark un correo con la tabla, la
evidencia y un botón **"Revisar y aprobar"** (enlace firmado, vence en 48 h). El enlace abre una
página de confirmación; el botón "Confirmar" (POST) aplica el plan una sola vez con
`app/services/resolution.resolve` y manda un correo de resultado. Los escalados van en el mismo
correo con veredicto sugerido y enlace a ESPN para cerrarlos en `/admin`.

La auto-aprobación de 1X2 (`RESOLUCION_AUTO_APROBAR_1X2`) está **apagada** desde el
2026-09-12 por decisión de Mark: todo plan, nocturno o del agente, lleva botón y nada se paga
sin su clic.

Comandos útiles: `agent-resolver.py planes` (planes del servidor y estado del job) y
`agent-resolver.py plan-nocturno` (dispara uno ahora, p. ej. cuando ya terminaron los partidos
"en vivo"). El flujo manual de abajo sigue vigente para escalados y para cuando Mark lo pida;
termina en `proponer`, que manda el mismo correo con botón.

## No deportivos

Los mercados fuera de Deportes con `auto_resolucion` (receta: cierres cripto, dominancia,
stablecoins, tasas, órdenes ejecutivas) los evalúa el mismo job con dos fuentes mecánicas
(`app/services/resolucion/recetas.py`). Los que no tienen receta salen "sin receta" y se resuelven a
mano, solo cuando Mark lo pide, con la skill **`resolver-no-deportivos`** (fuente de las normas + una
fuente confiable de la lista cerrada; NO por ausencia siempre escalado).

## Paso 0 — Token

```
./venv/bin/python agent-resolver.py check-token
```

Si el token venció, el comando lo regenera solo (`generate-agent-token.py`, sin contraseña).
Si aun así falla, avisa a Mark y detente.

## Paso 1 — Inventario

```
./venv/bin/python agent-resolver.py list --compact --out <scratchpad>/pendientes.json
./venv/bin/python agent-resolver.py list --out <scratchpad>/pendientes-detalle.json
```

`--compact` trae id, pregunta, tipo, subcategoría, kind, cierre, volumen, operaciones y los
`outcome_keys`. El detalle completo agrega criterio de resolución, fuente oficial y normas
(necesarios para los accesorios). No vuelvas a pedir la lista al API: trabaja con los archivos.

Agrupa por `subcategory` + `kind`:
- **Partidos** (`kind=partido`, "¿Quién gana…?"): multi con keys `local` / `empate` / `visitante`.
- **Accesorios** (`kind=accesorio`): titulares, goles, clasificaciones, props NFL. Binarios `YES`/`NO`
  (o multi con sus propias keys). Necesitan el criterio y las normas del detalle.
- **No deportivos**: caso por caso.

## Paso 2 — Resolución mecánica (sin tokens): `plan-auto`

```
./venv/bin/python agent-resolver.py plan-auto --out resoluciones/AAAA-MM-DD.json
```

Cruza los 1X2 pendientes con **ESPN** (jornada completa) y **TheSportsDB** (partido por
partido) usando `resolucion/` (sin LLM, ~5-10 min por el throttle de TheSportsDB). Al plan
entran solo los partidos cuyo marcador final coincide en ambas fuentes (`confianza: alta`,
`fuente_1` ESPN, `fuente_2` TheSportsDB). Todo lo demás sale en `escalados`, ordenado por
volumen, con `veredicto_sugerido` cuando ESPN sí tiene el dato:
- "solo una fuente": TheSportsDB no encontró el partido → confirma el marcador con UNA
  página oficial (WebFetch) y, si coincide con ESPN, muévelo al plan con esa URL como
  `fuente_2`.
- accesorios titular/gol (desde 2026-09-12): en Champions/Europa League entran solos al plan
  cuando ESPN y el API oficial de la UEFA (`match.uefa.com/v5`: alineaciones completas y
  goleadores, `fuentes.uefa_partidos` / `uefa_resumen`) coinciden, incluidos `NO` y
  `CANCELAR` (no convocado). En otras ligas la segunda fuente es TheSportsDB, que gratis
  RECORTA alineaciones y goles a 5 filas: solo confirma presencias (titular `YES`, gol
  `YES`); todo `NO` queda escalado. También quedan escalados: discrepancias y "sin gol" de un
  suplente (ninguna segunda fuente publica cambios, así que la participación solo la
  confirma ESPN) → confirma con la página oficial del partido y muévelo al plan.
- aplazado / sin cruce / sin fuente automática (liga fuera de `resolucion/fuentes.py:LIGAS`,
  Leagues Cup) → investigación manual solo si tiene volumen; si no, déjalo escalado.
- **NFL** (desde 2026-09-12): el ganador (outcomes por equipo, sede irrelevante) entra al plan
  con ESPN + TheSportsDB; las props (`anotará al menos N touchdown`, `lanzará N o más pases de
  touchdown`, `conseguirá N o más puntos de fantasy` con scoring estándar) entran con el box
  score de ESPN + el de CBS (`fuentes.cbs_boxscore_nfl`, URL
  `NFL_AAAAMMDD_VIS@LOC/` con fecha local del este). Jugador ausente de ambos box scores =
  inactivo → `CANCELAR`. Escalados: discrepancias, CBS caído (Railway podría estar bloqueado:
  confirmar entonces con WebFetch a CBS) y fantasy con balón suelto perdido (CBS no publica
  fumbles). Pro-Football-Reference bloquea y NFL.com no trae box score.

### Veredicto `CANCELAR`

Las normas de muchos mercados mandan cancelar (partido aplazado fuera de la ventana, jugador
inactivo que no participó, empate oficial en NFL). En el plan se escribe `"veredicto":
"CANCELAR"` (binarios y multi) con las mismas dos fuentes: al aplicarse llama a
`POST /admin/markets/{id}/cancel`, que devuelve a cada posición `shares × costo promedio` con
fila de ledger `refund`, anula los picks de ligas y avisa por correo. Nunca resuelvas `NO` a un
jugador que no jugó: es `CANCELAR`.

### Aplazado con nueva fecha (Mark decide)

Si Mark quiere mantener el mercado vivo, se reabre con `agent-resolver.py patch <id> --json
'{"status":"open","ends_at":"<nuevo kickoff UTC>","outcome_labels":{…}}'` (también `question`,
`rules`, `context`). Verifica la nueva fecha en el scoreboard de ESPN de la liga y, si cambió la
sede, corrige pregunta y etiquetas local/visitante.

**Este paso sustituye a la investigación con subagentes.** Lanzar subagentes de búsqueda
web por liga costó ~8,000 tokens por mercado (10-sep-2026) y agotó la sesión de Mark: no
volver a hacerlo. Para lo que `plan-auto` no resuelve, una sola página por mercado.

### Solo si Mark lo pide expresamente: investigación con subagentes

A cada subagente pásale un archivo con sus mercados (id, pregunta, tipo, `ends_at`, `outcome_keys`,
criterio de resolución, `resolution_source_url`, normas si es accesorio) e instrucciones estrictas:

- Buscar el resultado en la **fuente oficial** del mercado Y en **al menos otra fuente
  independiente de otro dominio** (ESPN, BBC Sport, Flashscore, web de la liga, medios serios).
  Anotar las URLs exactas de ambas (no portadas: la página del partido o del resultado).
- Aplicar el **criterio de resolución y las normas al pie de la letra**: partidos de liga se
  resuelven al minuto 90 (más añadido), sin prórroga ni penales salvo `copa`; hora CDMX;
  qué pasa en aplazamientos.
- Guía por tipo de accesorio:
  - **"¿X será titular…?"** → YES solo si aparece en la alineación inicial oficial (once
    titular); entrar de cambio es NO. Fuente: alineaciones de la liga/club + ESPN o BBC.
  - **"¿X anota gol…?"** → según lo que diga el criterio (normalmente cualquier gol en tiempo
    reglamentario, sin contar autogoles). Confirmar con el resumen oficial del partido.
  - **Clasificación / eliminatoria** ("¿X elimina a Y?", "¿X avanza a semifinales?") → resultado
    oficial de la competencia, incluyendo penales si la eliminatoria se define así y el
    criterio no lo excluye.
- Verificar que el evento realmente ya ocurrió y terminó. Si fue **aplazado, suspendido o
  reprogramado fuera de la ventana** de las normas, o no hay confirmación clara → `ESCALAR`
  con la razón. No proponer veredicto.
- Devolver por cada mercado exactamente estos campos (JSON):
  `id`, `veredicto` (`YES`/`NO` en binarios; el `outcome_key` exacto en multi, p. ej.
  `local`/`empate`/`visitante`; o `ESCALAR`), `resultado` (hecho verificado, p. ej.
  "Bayern 3-0 Schalke, 30-ago-2026"), `fuente_1` (URL), `fuente_2` (URL de otro dominio),
  `confianza` (`alta` solo si ambas fuentes coinciden y el criterio aplica sin interpretación;
  si no, `media`/`baja`) y, si escala, `razon`.

**Regla dura**: confianza distinta de `alta`, fuentes que no coinciden, fuentes del mismo dominio,
o criterio que hubo que interpretar → va a ESCALADOS, no al plan.

## Paso 3 — Plan y validación

`plan-auto` ya deja `resoluciones/AAAA-MM-DD.json` con este formato; edítalo para agregar
lo que confirmaste a mano (y deja en `escalados` lo que no):

```json
{"generado": "2026-09-09T20:00:00Z",
 "resoluciones": [{"id": "pl-city-coventry-j3-2627", "veredicto": "local",
                   "resultado": "Manchester City 3-0 Coventry (30-ago-2026)",
                   "fuente_1": "https://www.premierleague.com/match/…",
                   "fuente_2": "https://www.espn.com/soccer/match/…", "confianza": "alta"}],
 "escalados": [{"id": "…", "razon": "partido aplazado al 20-sep; tiene volumen → cancelar"}]}
```

```
./venv/bin/python agent-resolver.py check-plan resoluciones/AAAA-MM-DD.json
```

Valida contra el API (solo lectura): el mercado sigue pendiente, el veredicto es válido para
su tipo, las dos fuentes son URLs de dominios distintos, confianza `alta`, evento ya cerrado.
Corrige el plan hasta que salga `check-plan OK`. Un mercado que no pasa se mueve a escalados.

Presenta a Mark, legible en el chat:
1. **Tabla de propuestas** por liga: mercado (pregunta corta + id), veredicto, resultado, las
   2 fuentes. Marca con ⚠️ los que tienen operaciones (afectan posiciones reales) y di el
   total de PT involucrados (lo imprime `check-plan`).
2. **Escalados** con la razón. Partido aplazado/suspendido **con volumen** → "pendiente de
   cancelación" (no existe endpoint aún; Mark decide). **Sin volumen** → candidato al script
   de limpieza `cleanup-mercados-vencidos-sin-predicciones-2026-09-01.py`.
3. Cuántos mercados y PT se van a liquidar.

## Paso 4 — Proponer (aprobación por correo)

```
./venv/bin/python agent-resolver.py proponer resoluciones/AAAA-MM-DD.json
./venv/bin/python agent-resolver.py proponer resoluciones/AAAA-MM-DD.json --only id1 id2
```

`proponer` vuelve a correr `check-plan`, sube el plan al servidor
(`POST /admin/resolucion/planes/proponer`, que lo re-valida contra la BD) y lo guarda como
`ResolutionPlan` pendiente con `origen=agente`. Mark recibe el correo "Plan del agente" con la
tabla, las fuentes, los escalados y el botón **"Revisar y aprobar"** (enlace firmado, 48 h).
**Nada se resuelve hasta su clic.** Si el servidor rechaza el plan (`PLAN_INVALIDO`), imprime
los errores por mercado: corrige el JSON y vuelve a proponer.

Luego **DETENTE**: dile a Mark que revise el correo. Si él prefiere aprobar en el chat
("aprueba todo" / "todo menos X"), usa el respaldo `apply --yes` (con `--only` para parciales),
que resuelve directo y anexa a `resoluciones/log.jsonl`; re-ejecutable tras un fallo parcial
(`MARKET_ALREADY_RESOLVED` cuenta como ya resuelto). Si Mark corrige un veredicto, re-verifica
con dos fuentes antes de aceptar el cambio. **Nunca pases `--yes` sin su aprobación explícita.**

## Paso 5 — Reporte final y commit

Resumen: propuestos (y PT involucrados), escalados y qué decide Mark. Cuando Mark aprueba,
`agent-resolver.py planes` muestra `#N applied → resueltos X, fallidos Y`. Después:
- `git add resoluciones/AAAA-MM-DD.json` (y `resoluciones/log.jsonl` si se usó `apply`) y
  commit (`Resoluciones AAAA-MM-DD: N mercados propuestos (plan #N)`). Nunca `git add -A`.
- Sugerir `sembrar-mercados.py prune` si hay documentos en `mercados-pendientes.yaml`, y el
  script de limpieza (dry-run primero) si hay vencidos sin actividad escalados.

## Prohibiciones permanentes

- Nunca resolver sin aprobación de Mark en la conversación actual.
- Nunca resolver con una sola fuente, con fuentes en desacuerdo o del mismo dominio, o
  interpretando un criterio ambiguo por cuenta propia.
- Nunca resolver un mercado cuyo evento no haya terminado (cierre ≠ evento terminado:
  los futuros de temporada cierran meses después).
- Nunca tocar la BD directamente para resolver: siempre el endpoint del API vía
  `agent-resolver.py`, que liquida todo en una transacción y deja bitácora.
