"""Plan nocturno: arma el plan de resoluciones, lo persiste, lo manda por correo
al admin con un enlace de aprobación de un solo uso, y lo aplica cuando el
admin confirma.

Flujo:
  correr_plan_nocturno()  → ResolutionPlan(status=pending) + correo con URL firmada
  GET  …/aprobar?t=       → página de confirmación (no ejecuta nada)
  POST …/aprobar?t=       → aplicar_plan(): resuelve uno por uno, status applied|partial
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_db
from app.config import settings
from app.core.auth import ALGORITHM
from app.core.background import spawn
from app.models.resolution_plan import ResolutionPlan
from app.services import resolution
from app.services.email import send_resolution_plan_applied_email, send_resolution_plan_email
from app.services.resolucion.mercados import detalle_actual, pendientes_como_dicts
from app.services.resolucion.plan import armar_plan
from app.services.resolucion.validar import validar_entrada

logger = logging.getLogger(__name__)

_LAST: dict = {"ran_at": None, "last_plan_id": None, "last_error": None}


def get_nightly_status() -> dict:
    return {**_LAST, "horas_utc": horas_utc()}


# ── token de aprobación ──────────────────────────────────────────────────────

def make_plan_token(plan_id: int, nonce: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "typ": "plan_approval", "plan": plan_id, "n": nonce,
        "iat": now, "exp": now + timedelta(hours=settings.PLAN_APPROVAL_TTL_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_plan_token(token: str | None, plan_id: int) -> str | None:
    """Devuelve el nonce si el token es válido para este plan; None si no."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])  # valida exp
    except JWTError:
        return None
    nonce = payload.get("n")
    if payload.get("typ") != "plan_approval" or payload.get("plan") != plan_id or not isinstance(nonce, str):
        return None
    return nonce


def url_aprobacion(plan: ResolutionPlan) -> str:
    return f"{settings.BACKEND_URL}/api/admin/resolucion/planes/{plan.id}/aprobar?t={make_plan_token(plan.id, plan.nonce)}"


# ── armar ────────────────────────────────────────────────────────────────────

def resumen_de(plan: dict) -> dict:
    res, esc = plan.get("resoluciones", []), plan.get("escalados", [])
    con_ops = [r for r in res if (r.get("num_trades") or 0) > 0]
    return {
        "resoluciones": len(res),
        "escalados": len(esc),
        "con_operaciones": len(con_ops),
        "volumen": round(sum(float(r.get("volume") or 0) for r in res)),
        "sugeridos": len([e for e in esc if e.get("veredicto_sugerido")]),
        "sin_receta": len([e for e in esc if e.get("sin_receta")]),  # no deportivos para la skill
    }


def horas_utc() -> list[int]:
    """Horas UTC de corrida (RESOLUCION_HORAS_UTC "0,12"); si está vacía, la
    hora única de RESOLUCION_NOCTURNA_HORA_UTC."""
    raw = (settings.RESOLUCION_HORAS_UTC or "").strip()
    horas = sorted({int(h) for h in raw.split(",") if h.strip()}) if raw else []
    return horas or [settings.RESOLUCION_NOCTURNA_HORA_UTC]


def _inicio_del_turno(ahora: datetime, horas: list[int] | None = None) -> datetime:
    """Último slot programado ≤ ahora (hoy, o el último de ayer)."""
    horas = horas or horas_utc()
    candidatos = [ahora.replace(hour=h, minute=0, second=0, microsecond=0) for h in horas]
    pasados = [c for c in candidatos if c <= ahora]
    if pasados:
        return max(pasados)
    return max(candidatos) - timedelta(days=1)


async def _plan_del_turno(db: AsyncSession, ahora: datetime) -> ResolutionPlan | None:
    """Plan NOCTURNO armado desde el último slot programado (los propuestos por
    el agente no cuentan: no deben bloquear la corrida)."""
    inicio = _inicio_del_turno(ahora)
    res = await db.execute(
        select(ResolutionPlan)
        .where(
            ResolutionPlan.created_at >= inicio,
            ResolutionPlan.origen == "nocturno",
            ResolutionPlan.status.in_(("pending", "applied", "partial")),
        )
        .order_by(ResolutionPlan.id.desc())
    )
    return res.scalars().first()


async def _ultimo_plan(db: AsyncSession) -> ResolutionPlan | None:
    res = await db.execute(select(ResolutionPlan).order_by(ResolutionPlan.id.desc()).limit(1))
    return res.scalars().first()


def sin_novedades(plan: dict, anterior: dict | None) -> bool:
    """True si el plan no trae resoluciones y todos sus escalados (id + veredicto
    sugerido) ya estaban en el plan anterior: no vale la pena otro correo."""
    if plan.get("resoluciones") or anterior is None:
        return False
    previos = {(e.get("id"), e.get("veredicto_sugerido")) for e in anterior.get("escalados") or []}
    previos |= {(e.get("id"), None) for e in anterior.get("resoluciones") or []}
    actuales = {(e.get("id"), e.get("veredicto_sugerido")) for e in plan.get("escalados") or []}
    return actuales <= previos


async def _expirar_viejos(db: AsyncSession) -> int:
    limite = datetime.now(timezone.utc) - timedelta(hours=settings.PLAN_APPROVAL_TTL_HOURS)
    res = await db.execute(
        select(ResolutionPlan).where(ResolutionPlan.status == "pending", ResolutionPlan.created_at < limite)
    )
    viejos = res.scalars().all()
    for p in viejos:
        p.status = "expired"
    return len(viejos)


async def correr_plan_nocturno(forzar: bool = False) -> ResolutionPlan | None:
    """Arma y persiste el plan del turno; manda el correo. Devuelve None si no
    había pendientes, si en este turno ya se armó uno, o si no hay novedades
    respecto al plan anterior (salvo `forzar`)."""
    ahora = datetime.now(timezone.utc)
    _LAST["ran_at"] = ahora.isoformat()
    _LAST["last_error"] = None
    _LAST["horas_utc"] = horas_utc()
    try:
        async with app_db.AsyncSessionLocal() as db:
            await _expirar_viejos(db)
            await db.commit()
            if not forzar and await _plan_del_turno(db, ahora) is not None:
                logger.info("plan nocturno: ya existe un plan de este turno, no se arma otro")
                return None
            mercados = await pendientes_como_dicts(db)
            if not mercados:
                logger.info("plan nocturno: sin mercados pendientes")
                return None
            logger.info("plan nocturno: armando plan para %d pendientes", len(mercados))
            plan = await asyncio.to_thread(armar_plan, mercados)
            anterior = await _ultimo_plan(db)
            if not forzar and sin_novedades(plan, anterior.plan if anterior else None):
                logger.info("plan nocturno: sin novedades respecto al plan #%s (0 resoluciones, mismos escalados); no se guarda", anterior.id)
                return None
            row = ResolutionPlan(
                status="pending", origen="nocturno", nonce=secrets.token_urlsafe(16),
                plan=plan, resumen=resumen_de(plan),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            plan_id, nonce, resumen = row.id, row.nonce, dict(row.resumen)  # antes de cerrar la sesión
            resultado = None
            auto = [e for e in plan.get("resoluciones", []) if es_1x2_doble_fuente(e)]
            if settings.RESOLUCION_AUTO_APROBAR_1X2 and auto:
                logger.info("plan nocturno #%d: auto-aprobando %d 1X2 con doble fuente", plan_id, len(auto))
                row.status = "applying"
                await db.commit()
                resultado = await aplicar_plan(db, plan_id, {"resoluciones": auto}, notificar=False)
        _LAST["last_plan_id"] = plan_id
        logger.info("plan nocturno #%d: %s", plan_id, resumen)
        url = f"{settings.BACKEND_URL}/api/admin/resolucion/planes/{plan_id}/aprobar?t={make_plan_token(plan_id, nonce)}"
        spawn(send_resolution_plan_email(plan_id, plan, resumen, url, auto_resultado=resultado))
        return row
    except Exception as e:  # noqa: BLE001
        _LAST["last_error"] = str(e)
        logger.exception("plan nocturno falló")
        raise


# ── plan propuesto por el agente ─────────────────────────────────────────────

class PlanInvalido(ValueError):
    """El plan propuesto no pasa la validación; `errores` = {id: [motivos]}."""

    def __init__(self, message: str, errores: dict[str, list[str]]):
        super().__init__(message)
        self.errores = errores


_CAMPOS_ENTRADA = ("id", "veredicto", "resultado", "fuente_1", "fuente_2", "confianza")


async def proponer_plan(db: AsyncSession, plan: dict) -> ResolutionPlan:
    """Guarda un plan armado por el agente (`agent-resolver.py proponer`) como
    ResolutionPlan pendiente y manda el correo con el botón de aprobación. Misma
    validación que la aprobación del nocturno (`validar_entrada`): si alguna
    entrada falla, no se guarda nada y se lanza PlanInvalido."""
    entradas = list((plan or {}).get("resoluciones") or [])
    if not entradas:
        raise PlanInvalido("el plan no trae resoluciones", {})
    ahora = datetime.now(timezone.utc)
    errores: dict[str, list[str]] = {}
    enriquecidas: list[dict] = []
    vistos: set[str] = set()
    for e in entradas:
        mid = str(e.get("id") or "")
        if not mid:
            errores["?"] = ["entrada sin id"]
            continue
        if mid in vistos:
            errores[mid] = ["id repetido en el plan"]
            continue
        vistos.add(mid)
        detalle = await detalle_actual(db, mid)
        errs = validar_entrada(e, detalle, ahora)
        if errs:
            errores[mid] = errs
            continue
        enriquecidas.append({
            **{k: e.get(k) for k in _CAMPOS_ENTRADA},
            "pregunta": detalle.get("question"),
            "liga": detalle.get("subcategory"),
            "volume": detalle.get("volume"),
            "num_trades": detalle.get("num_trades"),
        })
    if errores:
        raise PlanInvalido(f"{len(errores)} mercado(s) con errores", errores)

    guardado = {
        "generado": ahora.isoformat(timespec="seconds"),
        "modo": "agente",
        "nota": plan.get("nota"),
        "resoluciones": enriquecidas,
        "escalados": list(plan.get("escalados") or []),
    }
    row = ResolutionPlan(
        status="pending", origen="agente", nonce=secrets.token_urlsafe(16),
        plan=guardado, resumen=resumen_de(guardado),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    plan_id, nonce, resumen = row.id, row.nonce, dict(row.resumen)
    logger.info("plan del agente #%d propuesto: %s", plan_id, resumen)
    url = f"{settings.BACKEND_URL}/api/admin/resolucion/planes/{plan_id}/aprobar?t={make_plan_token(plan_id, nonce)}"
    spawn(send_resolution_plan_email(plan_id, guardado, resumen, url, origen="agente"))
    return row


# ── aplicar ──────────────────────────────────────────────────────────────────

_1X2 = {"local", "empate", "visitante"}
_FUENTES_AUTO = {"espn.com", "thesportsdb.com"}


def es_1x2_doble_fuente(e: dict) -> bool:
    """Entrada apta para auto-aprobación: veredicto 1X2 y las dos fuentes
    automáticas (ESPN + TheSportsDB) con confianza alta."""
    from app.services.resolucion.validar import host

    hosts = {host(str(e.get("fuente_1") or "")), host(str(e.get("fuente_2") or ""))}
    return e.get("veredicto") in _1X2 and e.get("confianza") == "alta" and hosts == _FUENTES_AUTO


async def aplicar_plan(db: AsyncSession, plan_id: int, plan: dict, notificar: bool = True) -> dict:
    """Aplica las resoluciones del plan (una transacción por mercado). Deja
    `resultado` y `status` en la fila. Idempotente: un plan aplicado no se
    vuelve a aplicar (el llamador verifica status == pending). Recibe el plan
    por valor: los commits de resolve() expiran los objetos de la sesión."""
    ahora = datetime.now(timezone.utc)
    entradas = list((plan or {}).get("resoluciones", []))
    resueltos: list[dict] = []
    saltados: list[dict] = []
    fallidos: list[dict] = []
    posiciones = 0
    for e in entradas:
        mid = e.get("id")
        detalle = await detalle_actual(db, mid)
        if detalle is not None and detalle.get("status") != "pending_resolution":
            saltados.append({"id": mid, "razon": f"status {detalle.get('status')}"})
            continue
        errs = validar_entrada(e, detalle, ahora)
        if errs:
            fallidos.append({"id": mid, "razon": "; ".join(errs)})
            continue
        try:
            if e["veredicto"] == "CANCELAR":
                r = await resolution.cancel(db, mid)
                r["positions_settled"] = r.get("positions_refunded", 0)
            else:
                kwargs = {"outcome_key": e["veredicto"]} if detalle["market_type"] == "multi" else {"resolution": e["veredicto"]}
                r = await resolution.resolve(db, mid, **kwargs)
        except resolution.ResolutionError as ex:
            await db.rollback()
            if ex.code == "MARKET_ALREADY_RESOLVED":
                saltados.append({"id": mid, "razon": ex.code})
            else:
                fallidos.append({"id": mid, "razon": f"{ex.code}: {ex.message}"})
            continue
        except Exception as ex:  # noqa: BLE001
            await db.rollback()
            fallidos.append({"id": mid, "razon": f"error inesperado: {ex}"})
            continue
        posiciones += int(r.get("positions_settled") or 0)
        resueltos.append({"id": mid, "veredicto": e["veredicto"], "resultado": e.get("resultado"),
                          "fuente_1": e.get("fuente_1"), "fuente_2": e.get("fuente_2"),
                          "positions_settled": r.get("positions_settled")})
    resultado = {
        "aplicado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resueltos": resueltos, "saltados": saltados, "fallidos": fallidos,
        "posiciones_liquidadas": posiciones,
    }
    # Releer la fila: los commits de resolve() pudieron expirar el objeto.
    fresh = (await db.execute(select(ResolutionPlan).where(ResolutionPlan.id == plan_id))).scalar_one()
    fresh.approved_at = ahora
    fresh.applied_at = datetime.now(timezone.utc)
    fresh.resultado = resultado
    fresh.status = "partial" if fallidos else "applied"
    await db.commit()
    logger.info("plan #%d aplicado: %d resueltos, %d saltados, %d fallidos", plan_id, len(resueltos), len(saltados), len(fallidos))
    if notificar:
        spawn(send_resolution_plan_applied_email(plan_id, resultado))
    return resultado


# ── loop ─────────────────────────────────────────────────────────────────────

def segundos_hasta_proxima_corrida(ahora: datetime | None = None, hora_utc: int | None = None,
                                   horas: list[int] | None = None) -> float:
    """Segundos hasta el siguiente slot (hoy o mañana) de `horas` (default:
    horas_utc()); `hora_utc` fuerza una sola hora (compatibilidad)."""
    ahora = ahora or datetime.now(timezone.utc)
    slots = [hora_utc] if hora_utc is not None else (horas or horas_utc())
    candidatos = []
    for h in slots:
        objetivo = ahora.replace(hour=h, minute=0, second=0, microsecond=0)
        if objetivo <= ahora:
            objetivo += timedelta(days=1)
        candidatos.append(objetivo)
    return max(60.0, (min(candidatos) - ahora).total_seconds())


async def nightly_loop() -> None:
    while True:
        await asyncio.sleep(segundos_hasta_proxima_corrida())
        try:
            await correr_plan_nocturno()
        except Exception as e:  # noqa: BLE001
            print(f"[plan nocturno] error: {e}")
