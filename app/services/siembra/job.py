"""Agente de siembra: arma el plan del día, lo guarda, manda el correo con
casillas y siembra lo aprobado. Mismo esquema que el job de resolución
(`app/services/resolucion/nocturno.py`), sin LLM.

  correr_siembra()  → generadores (partidos, cripto, economía) → SeedPlan(status=pending) + correo con URL firmada
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
from app.services.siembra import cripto, economia, partidos
from app.services.siembra.partidos import _yaml
from seeds.runner import sembrar
from seeds.schema import cargar_texto

logger = logging.getLogger(__name__)

TOKEN_TYP = "seed_approval"
# Foto por defecto de lo que siembran los generadores (Wikimedia Commons, licencia libre,
# aprobadas por Mark el 24-sep). Un doc que ya trae image_url (rutina creativa) la conserva;
# Deportes no la necesita (escudos y caras en el frontend).
_WM = "https://thumb.wikimedia.org/wikipedia/commons/thumb/"
FOTO_POR_SUBCATEGORIA = {
    "Bitcoin": "https://upload.wikimedia.org/wikipedia/commons/8/8d/Bitcoin-dw.png",
    "Ethereum": _WM + "0/05/Ethereum_logo_2014.svg/330px-Ethereum_logo_2014.svg.png",
    "Solana": _WM + "3/34/Solana_cryptocurrency_two.jpg/330px-Solana_cryptocurrency_two.jpg",
    "Stablecoins": _WM + "0/01/USDT_Logo.png/330px-USDT_Logo.png",
    "Fed / tasas EE.UU.": _WM + "8/89/Eccles_Building_%2826088200676%29.jpg/330px-Eccles_Building_%2826088200676%29.jpg",
    "Tasas Banxico": _WM + "4/44/Edificio_del_Banco_de_Mexico_2021.jpg/330px-Edificio_del_Banco_de_Mexico_2021.jpg",
    "Inflación (INPC)": _WM + "d/de/Dulces_t%C3%ADpicos_mexicanos.jpg/330px-Dulces_t%C3%ADpicos_mexicanos.jpg",
}
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


GENERADORES = [("partidos", partidos.armar_propuestas), ("cripto", cripto.armar_propuestas),
               ("economia", economia.armar_propuestas)]


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
            row = await crear_plan(db, propuestas, descartes, "diario")
        _LAST["last_plan_id"] = row.id
        return row
    except Exception as e:  # noqa: BLE001
        _LAST["last_error"] = str(e)
        logger.exception("siembra falló")
        raise


async def crear_plan(db: AsyncSession, propuestas: list[dict], descartes: list[dict], generador: str,
                     nota: str | None = None) -> SeedPlan:
    """Guarda el plan y manda el correo con el enlace firmado."""
    plan = {"generado": datetime.now(timezone.utc).isoformat(), "generador": generador, "nota": nota,
            "propuestas": propuestas, "descartes": descartes}
    row = SeedPlan(status="pending", nonce=secrets.token_urlsafe(16), plan=plan, resumen=resumen_de(plan))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("siembra #%d (%s): %s", row.id, generador, row.resumen)
    spawn(send_seed_plan_email(row.id, plan, url_aprobacion(row.id, row.nonce)))
    return row


async def contexto_revisor(db: AsyncSession) -> tuple[set[str], list[str], int]:
    """(ids vigentes o ya propuestos, preguntas abiertas, locos abiertos) para `filtros`."""
    vigentes = await _vigentes(db)
    abiertas = list((await db.execute(select(Market.question).where(
        Market.status.in_((MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION))))).scalars())
    desde = datetime.now(timezone.utc) - timedelta(days=800)
    locos = {x["doc"]["id"] for plan in (await db.execute(select(SeedPlan.plan).where(
        SeedPlan.status == "applied", SeedPlan.created_at >= desde))).scalars()
        for x in plan.get("propuestas", []) if x.get("loco")}
    return vigentes | await _ya_propuestos(db), abiertas, len(locos & vigentes)


async def aplicar_siembra(db: AsyncSession, plan_id: int, plan: dict, ids: list[str]) -> dict:
    """Siembra los docs marcados en una transacción (el runner salta los ids que
    ya existen y los vencidos). El plan ya debe estar en `applying`."""
    marcados = set(ids)
    docs = [p["doc"] for p in plan.get("propuestas", []) if p["doc"]["id"] in marcados]
    for d in docs:
        if not d.get("image_url") and d.get("subcategory") in FOTO_POR_SUBCATEGORIA:
            d["image_url"] = FOTO_POR_SUBCATEGORIA[d["subcategory"]]
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
