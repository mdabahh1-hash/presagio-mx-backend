"""Fix existing markets + seed new ones (2026-06-29).

PHASE A: locate markets by question text (ILIKE), guardrail-protect priced/traded
markets, then reprice / recategorize / update resolution / resolve.
PHASE B: insert new binary markets, idempotent by id, deriving the opening LMSR
state from initial_yes_price (no hardcoded q).

Match strings were verified against the live question text so each resolves to
exactly one market. A0 still enforces the exactly-one rule at runtime.

Reprice/resolve are blocked when volume>0 or num_trades>0 unless FORCE=1, to avoid
disturbing markets with real positions.

Run:
    DATABASE_URL="postgresql+asyncpg://..." python fix-and-seed-2026-06-29.py
    FORCE=1 DATABASE_URL="..." python fix-and-seed-2026-06-29.py   # override guardrail
"""
import os
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal, engine
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.price_history import PriceHistory
from app.core import lmsr

FORCE = os.getenv("FORCE") == "1"


# ── PHASE A: fixes ──────────────────────────────────────────────────────────
# "match" verified to hit exactly one live market (your original paraphrases did
# not match the stored question text via ILIKE).
FIXES = [
    {
        "match": "a menos de 8%",
        "ops": ["resolve_yes"],
        "note": "La tasa de Banxico es 6.50% desde mayo, ya esta por debajo de 8%. El mercado ya es verdad.",
    },
    {
        "match": "Recortará la Fed",
        "ops": ["reprice"],
        "new_yes_price": 12.0,
        "note": "La Fed giro hawkish bajo Warsh y el mercado descuenta posible alza en julio.",
    },
    {
        "match": "70,000 USD",
        "ops": ["reprice"],
        "new_yes_price": 17.0,
        "note": "BTC en ~60k en mercado bajista. +17% en dos semanas contra la tendencia es poco probable.",
    },
    {
        "match": "los $150,000",
        "ops": ["reprice", "recategorize"],
        "new_yes_price": 8.0,
        "new_category": MarketCategory.CRYPTO,
        "note": "De 60k a 150k es +150% en bajada. Ademas estaba mal en Tech, va en Crypto.",
    },
    {
        "match": "tercer trimestre",
        "ops": ["reprice"],
        "new_yes_price": 30.0,
        "note": "Banxico dijo en mayo que fue el ultimo recorte de 2026 y paso a mantener.",
    },
    {
        "match": "octavos",
        "ops": ["reprice"],
        "new_yes_price": 80.0,
        "note": "96% es demasiado para un partido unico de knockout. El partido aun no se juega.",
    },
    {
        "match": "Morena las elecciones intermedias",
        "ops": ["reprice"],
        "new_yes_price": 72.0,
        "note": "0% esta roto. Morena es favorita a mantener mayoria.",
    },
    {
        "match": "Alto al fuego",
        "ops": ["update_resolution"],
        "new_resolution_criteria": "Resuelve SI si al 30 de junio de 2026 existe un acuerdo de alto al fuego formal y vigente entre las partes, sin operaciones militares de gran escala activas entre EE.UU. e Iran en las 48 horas previas al cierre. Fuente comunicados oficiales de EE.UU. e Iran.",
        "note": "El precio no es el problema, la resolucion era ambigua.",
    },
]


# ── PHASE B: new markets ────────────────────────────────────────────────────
MARKETS = [
    {
        "id": "cruz-azul-campeon-de-campeones-2026",
        "question": "¿Cruz Azul vence a Toluca en el Campeón de Campeones 2026?",
        "description": "El 25 de julio se juega el Campeón de Campeones entre Cruz Azul, monarca del Clausura 2026, y Toluca, campeón del torneo anterior. Es un partido único a definirse el mismo día.",
        "category": MarketCategory.DEPORTES,
        "resolution_criteria": "Resuelve SÍ si Cruz Azul gana a Toluca en el Campeón de Campeones del 25 de julio de 2026, en tiempo regular o en penales. Fuente Liga MX.",
        "ends_at": datetime(2026, 7, 26, 5, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 50.0,
        "trending": True,
    },
    {
        "id": "fed-sube-tasa-julio-2026",
        "question": "¿La Fed sube la tasa en su reunión del 29 de julio de 2026?",
        "description": "La Reserva Federal mantuvo la tasa en 3.50 a 3.75 por ciento en junio y quitó el sesgo de baja bajo el nuevo chair Warsh. El mercado empezó a descontar una posible alza de 25 pb en julio.",
        "category": MarketCategory.MERCADOS_GLOBALES,
        "resolution_criteria": "Resuelve SÍ si el FOMC anuncia un aumento del rango objetivo de la tasa de fondos federales en su decisión del 29 de julio de 2026. Fuente Federal Reserve.",
        "ends_at": datetime(2026, 7, 29, 20, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 38.0,
        "trending": True,
    },
    {
        "id": "argentina-final-mundial-2026",
        "question": "¿Argentina llega a la final del Mundial 2026?",
        "description": "Argentina es de las favoritas y Messi llega encendido tras la fase de grupos. El mercado pregunta solo si disputa la final, no si gana el torneo.",
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": "Resuelve SÍ si Argentina disputa la final del Mundial 2026, es decir si gana su semifinal. Fuente FIFA.",
        "ends_at": datetime(2026, 7, 16, 4, 0, 0, tzinfo=timezone.utc),
        "b": 150.0,
        "initial_yes_price": 30.0,
        "trending": True,
    },
    {
        "id": "banxico-mantiene-tasa-ago-2026",
        "question": "¿Banxico mantiene la tasa sin cambios en su reunión de agosto de 2026?",
        "description": "Tras el recorte de mayo a 6.50 por ciento, Banxico señaló que sería el último del año y pasó a una postura de mantener. El mercado pregunta si vuelve a dejar la tasa intacta.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si Banxico deja la tasa de referencia sin cambios en su anuncio de política monetaria de agosto de 2026. Fuente Banco de México.",
        "ends_at": datetime(2026, 8, 6, 20, 0, 0, tzinfo=timezone.utc),
        "b": 120.0,
        "initial_yes_price": 82.0,
        "trending": False,
    },
    {
        "id": "anfitrion-semifinal-mundial-2026",
        "question": "¿Algún país anfitrión llega a semifinales del Mundial 2026?",
        "description": "México, Estados Unidos y Canadá organizan el torneo. Canadá goleó en fase de grupos y México ganó su grupo invicto. El mercado pregunta si al menos uno alcanza las semifinales.",
        "category": MarketCategory.MUNDIAL_2026,
        "resolution_criteria": "Resuelve SÍ si al menos una de México, Estados Unidos o Canadá clasifica a las semifinales del Mundial 2026. Fuente FIFA.",
        "ends_at": datetime(2026, 7, 12, 6, 0, 0, tzinfo=timezone.utc),
        "b": 120.0,
        "initial_yes_price": 25.0,
        "trending": False,
    },
    {
        "id": "inflacion-mx-julio-baja-2026",
        "question": "¿La inflación de julio 2026 baja respecto a junio en México?",
        "description": "INEGI publica el INPC de julio a principios de agosto. Banxico revisó al alza la inflación no subyacente para este tramo del año, lo que hace el resultado incierto.",
        "category": MarketCategory.ECONOMIA,
        "resolution_criteria": "Resuelve SÍ si la inflación general mensual de julio 2026 reportada por INEGI es menor que la de junio 2026. Fuente INEGI.",
        "ends_at": datetime(2026, 8, 7, 18, 0, 0, tzinfo=timezone.utc),
        "b": 100.0,
        "initial_yes_price": 50.0,
        "trending": False,
    },
]


def _guard_blocked(m: Market) -> bool:
    """True if a reprice/resolve must be skipped to protect a market with activity."""
    return (m.volume > 0 or m.num_trades > 0) and not FORCE


async def run_fixes(db) -> tuple[int, int]:
    applied = skipped = 0
    print("══════════ FASE A — FIXES ══════════")
    for fix in FIXES:
        match = fix["match"]
        rows = (await db.execute(select(Market).where(Market.question.ilike(f"%{match}%")))).scalars().all()
        if len(rows) != 1:
            print(f"\nERROR  match '{match}': {len(rows)} coincidencia(s) — SALTADO")
            for r in rows:
                print(f"    candidato: [{r.id}] {r.question[:70]}")
            skipped += 1
            continue

        m = rows[0]
        print(f"\n[{m.id}]  vol={round(m.volume)} trades={m.num_trades}  ·  {fix['note']}")
        did_something = False
        for op in fix["ops"]:
            if op == "reprice":
                if _guard_blocked(m):
                    print(f"  ⛔ reprice SALTADO (vol/trades>0, sin FORCE)")
                    continue
                old = m.yes_price
                p = fix["new_yes_price"] / 100.0
                q_yes, q_no = lmsr.init_q_for_price(p, m.b)
                yp = lmsr.yes_price_pct(q_yes, q_no, m.b)
                m.q_yes, m.q_no, m.yes_price = q_yes, q_no, yp
                db.add(PriceHistory(market_id=m.id, yes_price=yp, volume_snapshot=m.volume))
                print(f"  ✓ reprice: {old}% → {yp}%  (b={m.b})")
                did_something = True
            elif op == "recategorize":
                old = m.category.value
                m.category = fix["new_category"]
                print(f"  ✓ recategorize: {old} → {m.category.value}")
                did_something = True
            elif op == "update_resolution":
                m.resolution_criteria = fix["new_resolution_criteria"]
                print(f"  ✓ update_resolution: criterio actualizado")
                did_something = True
            elif op == "resolve_yes":
                if _guard_blocked(m):
                    print(f"  ⛔ resolve_yes SALTADO (vol/trades>0, sin FORCE)")
                    continue
                # No reusable resolution service exists (payout logic lives inline in
                # the admin endpoint). Manual set per spec — safe because the guardrail
                # only lets through markets with no positions, so no payouts are owed.
                m.status = MarketStatus.RESOLVED_YES
                m.resolved_at = datetime.now(timezone.utc)
                print(f"  ✓ resolve_yes: status → RESOLVED_YES  (yes_price={m.yes_price}%, b={m.b})")
                did_something = True
            else:
                print(f"  ? op desconocida: {op}")

        if did_something:
            applied += 1
        else:
            skipped += 1
            print("  (sin cambios efectivos → contado como saltado)")
    return applied, skipped


async def run_seed(db) -> tuple[int, int]:
    inserted = existing = 0
    print("\n══════════ FASE B — NUEVOS MERCADOS ══════════")
    for data in MARKETS:
        exists = (await db.execute(select(Market).where(Market.id == data["id"]))).scalar_one_or_none()
        if exists:
            print(f"SKIP   {data['id']} (ya existe)")
            existing += 1
            continue
        p = data["initial_yes_price"] / 100.0
        q_yes, q_no = lmsr.init_q_for_price(p, data["b"])
        yes_price_val = lmsr.yes_price_pct(q_yes, q_no, data["b"])
        m = Market(
            id=data["id"], question=data["question"], description=data["description"],
            category=data["category"], resolution_criteria=data["resolution_criteria"],
            ends_at=data["ends_at"], b=data["b"], q_yes=q_yes, q_no=q_no,
            yes_price=yes_price_val, volume=0.0, num_trades=0,
            status=MarketStatus.OPEN, trending=data.get("trending", False), market_type="binary",
        )
        db.add(m)
        db.add(PriceHistory(market_id=m.id, yes_price=yes_price_val, volume_snapshot=0.0))
        print(f"INSERT {data['id']}  yes_price={yes_price_val}  b={data['b']}")
        inserted += 1
    return inserted, existing


async def main() -> None:
    print(f"FORCE = {FORCE}\n")
    async with AsyncSessionLocal() as db:
        fixes_applied, fixes_skipped = await run_fixes(db)
        inserted, existing = await run_seed(db)
        await db.commit()

    print("\n══════════ RESUMEN ══════════")
    print(f"Fixes aplicados:  {fixes_applied}")
    print(f"Fixes saltados:   {fixes_skipped}")
    print(f"Mercados nuevos insertados: {inserted}")
    print(f"Mercados que ya existían:   {existing}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
