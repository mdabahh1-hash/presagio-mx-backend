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
> jamás se adivina. Y NUNCA se ejecuta una resolución sin la aprobación explícita de Mark
> en esta conversación.**

Herramienta: `agent-resolver.py` en la raíz del repo backend
(`/Users/markdabah/Desktop/veredikt/veredikt-mx-backend`). Todos los comandos se corren desde
ahí con `./venv/bin/python`. Los planes y la bitácora viven en `resoluciones/` (se commitean:
son el rastro de auditoría de qué se resolvió, con qué evidencia).

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

## Paso 2 — Investigación en paralelo (subagentes)

Lanza subagentes **en paralelo** (uno por liga o grupo, tipo general-purpose con búsqueda web).
A cada uno pásale un archivo con sus mercados (id, pregunta, tipo, `ends_at`, `outcome_keys`,
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

Con las respuestas arma `resoluciones/AAAA-MM-DD.json`:

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

Luego **DETENTE y espera la aprobación explícita de Mark**. Acepta aprobación total ("aprueba
todo") o parcial ("todo menos X y Y" → usa `--only` o quita los ids del plan). Si Mark corrige
un veredicto, re-verifica con dos fuentes antes de aceptar el cambio.

## Paso 4 — Ejecución (solo tras aprobación)

```
./venv/bin/python agent-resolver.py apply resoluciones/AAAA-MM-DD.json --yes
./venv/bin/python agent-resolver.py apply resoluciones/AAAA-MM-DD.json --yes --only id1 id2
```

`apply` vuelve a correr `check-plan`, resuelve uno por uno y anexa cada resultado a
`resoluciones/log.jsonl`. Si falla a la mitad, re-ejecuta el mismo comando: los ya registrados
se saltan. `MARKET_ALREADY_RESOLVED` cuenta como ya resuelto, no como fallo.

**Nunca pases `--yes` sin la aprobación de Mark en esta conversación.**

## Paso 5 — Reporte final y commit

Resumen: resueltos (y posiciones liquidadas), fallidos y por qué, escalados y qué decide Mark.
Después:
- `git add resoluciones/AAAA-MM-DD.json resoluciones/log.jsonl` y commit
  (`Resoluciones AAAA-MM-DD: N mercados`). Nunca `git add -A`.
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
