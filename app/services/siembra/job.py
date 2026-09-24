"""Agente de siembra: arma el plan del día, lo guarda, manda el correo con
casillas y siembra lo aprobado. Mismo esquema que el job de resolución
(`app/services/resolucion/nocturno.py`), sin LLM.

  correr_siembra()  → generadores (partidos, cripto) → SeedPlan(status=pending) + correo con URL firmada
  GET  /api/admin/siembra/planes/{id}/aprobar?t= → página con casillas (no ejecuta)
  POST …/aprobar?t= (ids marcados)              → aplicar_siembra(): sembrador YAML
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_db
from app.config import settings
from app.core.background import spawn
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.seed_plan import SeedPlan
from app.services.email import send_seed_plan_email
from app.services.resolucion.fuentes import Http
from app.services.resolucion.nocturno import make_plan_token, segundos_hasta_proxima_corrida
from app.services.siembra import cripto, partidos
from app.services.siembra.partidos import _yaml
from seeds.runner import sembrar
from seeds.schema import cargar_texto

logger = logging.getLogger(__name__)

TOKEN_TYP = "seed_approval"
_LAST: dict = {"ran_at": None, "last_plan_id": None, "last_error": None}


def url_aprobacion(plan_id: int, nonce: str) -> str:
    return (f"{settings.BACKEND_URL}/api/admin/siembra/planes/{plan_id}/aprobar"
            f"?t={make_plan_token(plan_id, nonce, TOKEN_TYP)}")


async def _expirar_viejos(db: AsyncSession) -> None:
    limite = datetime.now(timezone.utc) - timedelta(hours=settings.PLAN_APPROVAL_TTL_HOURS)
    for p in (await db.execute(select(SeedPlan).where(SeedPlan.status == "pending",
                                                      SeedPlan.created_at < limite))).scalars():
        p.status = "expired"


async def _ya_propuestos(db: AsyncSession) -> set[str]:
    """Ids en planes vivos o aprobados (un partido desmarcado no vuelve a salir).
    Los de planes vencidos sí se vuelven a proponer."""
    desde = datetime.now(timezone.utc) - timedelta(days=30)
    filas = (await db.execute(select(SeedPlan.plan).where(
        SeedPlan.status.in_(("pending", "applying", "applied")), SeedPlan.created_at >= desde))).scalars()
    return {x["doc"]["id"] for plan in filas for x in plan.get("propuestas", [])}


async def _vigentes(db: AsyncSession) -> set[str]:
    """Ids de los mercados que aún no cierran (una escalera del mes ya sembrada no se repite)."""
    return set((await db.execute(select(Market.id).where(Market.ends_at >= datetime.now(timezone.utc)))).scalars())


async def _partidos_abiertos(db: AsyncSession) -> list[dict]:
    """[{subcategory, kickoff_at, labels}] de los partidos abiertos (duplicados con otro id)."""
    mercados = (await db.execute(select(Market.id, Market.subcategory, Market.kickoff_at).where(
        Market.kind == "partido", Market.kickoff_at.is_not(None),
        Market.status.in_((MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION))))).all()
    labels: dict[str, list[str]] = {}
    if mercados:
        for mid, label in (await db.execute(select(Outcome.market_id, Outcome.label).where(
                Outcome.market_id.in_([m.id for m in mercados])))).all():
            labels.setdefault(mid, []).append(label)
    return [{"subcategory": m.subcategory, "kickoff_at": m.kickoff_at, "labels": labels.get(m.id, [])} for m in mercados]


def resumen_de(plan: dict) -> dict:
    props = plan.get("propuestas", [])
    return {"propuestas": len(props), "revisar": sum(1 for p in props if p["revisar"]),
            "descartes": len(plan.get("descartes", []))}


GENERADORES = [("partidos", partidos.armar_propuestas), ("cripto", cripto.armar_propuestas)]


def _correr_generadores(ahora: datetime, excluir: set[str], existentes: list[dict]) -> tuple[list[dict], list[dict]]:
    """Síncrono (urllib). Un generador que truena sale en descartes y no tumba a los demás."""
    props, desc = [], []
    for nombre, gen in GENERADORES:
        try:
            p, d = gen(Http(), ahora, excluir, existentes)
        except Exception as e:  # noqa: BLE001
            logger.exception("siembra: el generador %s falló", nombre)
            p, d = [], [{"grupo": nombre, "titulo": "(generador completo)", "motivo": f"falló: {e}"[:300]}]
        props += p
        desc += d
    return props, desc


async def correr_siembra() -> SeedPlan | None:
    """Arma, guarda y manda el plan. None si no hay nada nuevo que proponer."""
    ahora = datetime.now(timezone.utc)
    _LAST.update(ran_at=ahora.isoformat(), last_error=None)
    try:
        async with app_db.AsyncSessionLocal() as db:
            await _expirar_viejos(db)
            await db.commit()
            existentes = await _partidos_abiertos(db)
            excluir = await _vigentes(db) | await _ya_propuestos(db)
            propuestas, descartes = await asyncio.to_thread(_correr_generadores, ahora, excluir, existentes)
            if not propuestas:
                logger.info("siembra: sin mercados nuevos (%d descartes)", len(descartes))
                return None
            plan = {"generado": ahora.isoformat(),
                    "propuestas": propuestas, "descartes": descartes}
            row = SeedPlan(status="pending", nonce=secrets.token_urlsafe(16), plan=plan, resumen=resumen_de(plan))
            db.add(row)
            await db.commit()
            await db.refresh(row)
            plan_id, nonce = row.id, row.nonce
        _LAST["last_plan_id"] = plan_id
        logger.info("siembra #%d: %s", plan_id, row.resumen)
        spawn(send_seed_plan_email(plan_id, plan, url_aprobacion(plan_id, nonce)))
        return row
    except Exception as e:  # noqa: BLE001
        _LAST["last_error"] = str(e)
        logger.exception("siembra falló")
        raise


async def aplicar_siembra(db: AsyncSession, plan_id: int, plan: dict, ids: list[str]) -> dict:
    """Siembra los docs marcados en una transacción (el runner salta los ids que
    ya existen y los vencidos). El plan ya debe estar en `applying`."""
    marcados = set(ids)
    docs = [p["doc"] for p in plan.get("propuestas", []) if p["doc"]["id"] in marcados]
    r = None
    if docs:
        specs, _ = cargar_texto(_yaml(docs))
        r = await sembrar(specs, db, apply=True, log=logger.info)
    resultado = {
        "insertados": r.insertados if r else [], "existentes": r.existentes if r else [],
        "vencidos": r.vencidos if r else [],
        "desmarcados": [p["doc"]["id"] for p in plan.get("propuestas", []) if p["doc"]["id"] not in marcados],
    }
    row = (await db.execute(select(SeedPlan).where(SeedPlan.id == plan_id))).scalar_one()
    row.status, row.resultado, row.applied_at = "applied", resultado, datetime.now(timezone.utc)
    await db.commit()
    logger.info("siembra #%d aplicada: %d insertados", plan_id, len(resultado["insertados"]))
    return resultado


async def siembra_loop() -> None:
    while True:
        await asyncio.sleep(segundos_hasta_proxima_corrida(horas=[settings.SIEMBRA_HORA_UTC]))
        try:
            await correr_siembra()
        except Exception as e:  # noqa: BLE001
            print(f"[siembra] error: {e}")
