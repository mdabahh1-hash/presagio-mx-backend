"""Agente revisor: revisa los mercados activos contra los requisitos (`checks.py`),
guarda el plan, manda el correo con casillas y aplica lo aprobado. Mismo esquema
que el agente de siembra (`app/services/siembra/job.py`), sin LLM.

  correr_revision() → checks → ReviewPlan(status=pending) + correo con URL firmada
                      (solo si hay algún hallazgo nuevo)
  GET  /api/admin/revision/planes/{id}/aprobar?t= → página con casillas (no ejecuta)
  POST …/aprobar?t= (ids marcados)               → aplicar_revision()
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_db
from app.config import settings
from app.core.background import spawn
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.review_plan import ReviewPlan
from app.services.email import send_review_plan_email
from app.services.resolucion.nocturno import make_plan_token, segundos_hasta_proxima_corrida
from app.services.revision.checks import CAMPOS_FIX, revisar, valor

logger = logging.getLogger(__name__)

TOKEN_TYP = "review_approval"
ACTIVOS = (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION)
_EDITABLES = (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION, MarketStatus.CLOSED)  # = admin.py
VISTOS_DIAS = 30  # un aviso ya enviado no vuelve a disparar correo en este plazo


def url_aprobacion(plan_id: int, nonce: str) -> str:
    return (f"{settings.BACKEND_URL}/api/admin/revision/planes/{plan_id}/aprobar"
            f"?t={make_plan_token(plan_id, nonce, TOKEN_TYP)}")


async def hallazgos(db: AsyncSession, ahora: datetime) -> list[dict]:
    mercados = list((await db.execute(select(Market).where(Market.status.in_(ACTIVOS)).order_by(Market.id))).scalars())
    n_out = dict((await db.execute(select(Outcome.market_id, func.count()).group_by(Outcome.market_id))).all())
    return [x for m in mercados for x in revisar(m, n_out.get(m.id, 0), ahora)]


async def _historial(db: AsyncSession) -> tuple[set[str], set[str]]:
    """(ids ya enviados en los últimos 30 días, fixes desmarcados: no se vuelven a
    proponer). Un fix de un plan vencido sin respuesta sí cuenta como nuevo otra vez."""
    vistos, desmarcados = set(), set()
    for status, plan, res in (await db.execute(select(ReviewPlan.status, ReviewPlan.plan, ReviewPlan.resultado).where(
            ReviewPlan.created_at >= datetime.now(timezone.utc) - timedelta(days=VISTOS_DIAS)))).all():
        vistos |= {x["id"] for x in plan.get("hallazgos", []) if not (x["fix"] and status == "expired")}
        desmarcados |= set((res or {}).get("desmarcados", []))
    return vistos, desmarcados


def resumen_de(plan: dict) -> dict:
    hs = plan.get("hallazgos", [])
    return {"arreglos": sum(1 for x in hs if x["fix"]), "avisos": sum(1 for x in hs if not x["fix"]),
            "nuevos": plan.get("nuevos", 0)}


async def correr_revision(dry_run: bool = False) -> dict | ReviewPlan | None:
    """Revisa y, si hay algún hallazgo nuevo, guarda el plan y manda el correo.
    `dry_run` devuelve {hallazgos, nuevos} sin guardar ni mandar nada."""
    ahora = datetime.now(timezone.utc)
    async with app_db.AsyncSessionLocal() as db:
        limite = ahora - timedelta(hours=settings.PLAN_APPROVAL_TTL_HOURS)
        if not dry_run:
            for p in (await db.execute(select(ReviewPlan).where(ReviewPlan.status == "pending",
                                                                ReviewPlan.created_at < limite))).scalars():
                p.status = "expired"
            await db.commit()
        vistos, desmarcados = await _historial(db)
        hs = [x for x in await hallazgos(db, ahora) if not (x["fix"] and x["id"] in desmarcados)]
        nuevos = [x["id"] for x in hs if x["id"] not in vistos]
        if dry_run:
            return {"hallazgos": hs, "nuevos": nuevos}
        if not nuevos:
            logger.info("revisión: %d hallazgos, ninguno nuevo", len(hs))
            return None
        plan = {"generado": ahora.isoformat(), "hallazgos": hs, "nuevos": len(nuevos), "ids_nuevos": nuevos}
        row = ReviewPlan(status="pending", nonce=secrets.token_urlsafe(16), plan=plan, resumen=resumen_de(plan))
        db.add(row)
        await db.commit()
        await db.refresh(row)
    logger.info("revisión #%d: %s", row.id, row.resumen)
    spawn(send_review_plan_email(row.id, plan, url_aprobacion(row.id, row.nonce)))
    return row


async def aplicar_revision(db: AsyncSession, plan_id: int, plan: dict, ids: list[str]) -> dict:
    """Aplica los fixes marcados en una transacción. Salta el mercado que ya no es
    editable o cuyo valor cambió desde la propuesta. El plan ya debe estar en `applying`."""
    marcados = set(ids)
    fixes = [x for x in plan.get("hallazgos", []) if x["fix"]]
    aplicados, saltados = [], []
    for x in fixes:
        if x["id"] not in marcados:
            continue
        f = x["fix"]
        m = (await db.execute(select(Market).where(Market.id == x["market_id"]).with_for_update())).scalar_one_or_none()
        if f["campo"] not in CAMPOS_FIX:
            saltados.append({"id": x["id"], "motivo": "campo no permitido"})
        elif m is None or m.status not in _EDITABLES:
            saltados.append({"id": x["id"], "motivo": "el mercado ya no es editable"})
        elif valor(getattr(m, f["campo"])) != f["antes"]:
            saltados.append({"id": x["id"], "motivo": "cambio_desde_propuesta"})
        else:
            nuevo = f["despues"]
            if f["campo"] == "kickoff_at" and nuevo is not None:
                nuevo = datetime.fromisoformat(nuevo)
            setattr(m, f["campo"], nuevo)
            aplicados.append(x["id"])
    resultado = {"aplicados": aplicados, "saltados": saltados,
                 "desmarcados": [x["id"] for x in fixes if x["id"] not in marcados]}
    row = (await db.execute(select(ReviewPlan).where(ReviewPlan.id == plan_id))).scalar_one()
    row.status, row.resultado, row.applied_at = "applied", resultado, datetime.now(timezone.utc)
    await db.commit()
    logger.info("revisión #%d aplicada: %d cambios", plan_id, len(aplicados))
    return resultado


async def revision_loop() -> None:
    while True:
        await asyncio.sleep(segundos_hasta_proxima_corrida(horas=[settings.REVISION_HORA_UTC]))
        try:
            await correr_revision()
        except Exception as e:  # noqa: BLE001
            logger.exception("revisión falló")
            print(f"[revision] error: {e}")
