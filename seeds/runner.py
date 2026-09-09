"""Inserción idempotente de MarketSpec en la BD.

Mismas cuatro escrituras que hacían los seed-markets-*.py: fila en markets,
(multi) filas en market_outcomes, una fila en price_history. Con apply=False
hace las mismas lecturas y los mismos prints pero termina en rollback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import lmsr
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.outcome import Outcome
from app.models.price_history import PriceHistory
from seeds.schema import MarketSpec


@dataclass
class Resumen:
    insertados: list[str] = field(default_factory=list)
    existentes: list[str] = field(default_factory=list)
    vencidos: list[str] = field(default_factory=list)


async def sembrar(specs: list[MarketSpec], db: AsyncSession, apply: bool,
                  now: datetime | None = None, log=print) -> Resumen:
    now = now or datetime.now(timezone.utc)
    r = Resumen()
    for s in specs:
        existe = (await db.execute(select(Market.id).where(Market.id == s.id))).scalar_one_or_none()
        if existe is not None:
            log(f"  SKIP   {s.id} (ya existe)")
            r.existentes.append(s.id)
            continue
        # Guarda load-bearing: cleanup-mercados-vencidos-sin-predicciones-* borra los
        # vencidos sin actividad y no deben resucitar en la siguiente siembra.
        if s.ends_at < now:
            log(f"  SKIP   {s.id} (ya vencido: ends_at={s.ends_at:%Y-%m-%dT%H:%M}Z; no se siembran mercados cerrados)")
            r.vencidos.append(s.id)
            continue

        comunes = dict(
            id=s.id, question=s.question, description=s.description,
            category=MarketCategory[s.category], subcategory=s.subcategory, kind=s.kind,
            image_url=s.image_url, resolution_criteria=s.resolution_criteria,
            resolution_source_url=s.resolution_source_url, rules=s.rules, context=s.context,
            ends_at=s.ends_at, b=s.b, volume=0.0, num_trades=0,
            status=MarketStatus.OPEN, trending=s.trending,
        )
        sub = s.subcategory or "-"
        cuando = f"{s.ends_at:%Y-%m-%d %H:%M}Z"
        if s.tipo == "binario":
            q_yes, q_no = lmsr.init_q_for_price(s.initial_yes_price / 100.0, s.b)
            yp = lmsr.yes_price_pct(q_yes, q_no, s.b)
            log(f"  INSERT {s.id}  binario  {s.category}/{sub}  yes_price={yp}%  b={s.b:g}  ends_at={cuando}")
            if apply:
                db.add(Market(**comunes, market_type="binary", q_yes=q_yes, q_no=q_no, yes_price=yp))
                db.add(PriceHistory(market_id=s.id, yes_price=yp, volume_snapshot=0.0))
        else:
            q = lmsr.init_qs_for_targets({o.key: o.pct for o in s.outcomes}, s.b)
            check = lmsr.prices_multi(q, s.b)
            etiqueta = "multi (partido)" if s.origen == "partido" else "multi"
            log(f"  INSERT {s.id}  {etiqueta}  {s.category}/{sub}  b={s.b:g}  trending={s.trending}  ends_at={cuando}")
            for o in s.outcomes:
                log(f"           + {o.key:<12} {o.label:<34} {o.pct:5.1f}%  q={q[o.key]:9.2f}  lmsr_check={check[o.key]:.2f}%")
            if apply:
                db.add(Market(**comunes, market_type="multi"))
                await db.flush()  # fija el padre antes de los outcomes
                for o in s.outcomes:
                    db.add(Outcome(market_id=s.id, outcome_key=o.key, label=o.label, q=q[o.key], price=float(o.pct)))
                db.add(PriceHistory(market_id=s.id, yes_price=0.0, volume_snapshot=0.0))
        r.insertados.append(s.id)

    if apply:
        await db.commit()
    else:
        await db.rollback()
    return r
