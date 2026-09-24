"""Agente de siembra: listar/disparar planes (admin con Bearer) y aprobar un plan
desde el enlace firmado del correo (sin sesión), eligiendo mercado por mercado.

GET  /admin/siembra/planes/{id}/aprobar?t=…  → página con casillas (NO ejecuta:
      los clientes de correo pre-cargan los enlaces).
POST /admin/siembra/planes/{id}/aprobar?t=…  → siembra los marcados, una sola vez.
"""
from __future__ import annotations

from datetime import datetime
from html import escape as _esc

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.resolucion import _pagina
from app.core.auth import get_current_user, require_admin
from app.core.background import spawn
from app.database import get_db
from app.models.seed_plan import SeedPlan
from app.models.user import User
from app.services.email import _fmt_mx
from app.services.resolucion.nocturno import verify_plan_token
from app.services.siembra import job, vista

router = APIRouter(prefix="/admin/siembra", tags=["admin"])


@router.get("/planes")
async def listar_planes(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_admin(current_user)
    filas = (await db.execute(select(SeedPlan).order_by(SeedPlan.id.desc()).limit(20))).scalars()
    return [{"id": p.id, "status": p.status, "resumen": p.resumen, "resultado": p.resultado,
             "created_at": p.created_at, "applied_at": p.applied_at} for p in filas]


@router.post("/planes", status_code=202)
async def disparar_plan(current_user: User = Depends(get_current_user)):
    """Arma un plan ahora, en segundo plano (≈100 consultas a ESPN, Binance y DefiLlama)."""
    require_admin(current_user)
    spawn(job.correr_siembra())
    return {"started": True}


async def _cargar(db: AsyncSession, plan_id: int, t: str | None) -> SeedPlan:
    nonce = verify_plan_token(t, plan_id, job.TOKEN_TYP)
    p = None if nonce is None else (await db.execute(
        select(SeedPlan).where(SeedPlan.id == plan_id).with_for_update())).scalar_one_or_none()
    if p is None or p.nonce != nonce:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PLAN_TOKEN", "message": "Enlace inválido o vencido"})
    return p


def _resultado_html(res: dict | None) -> str:
    if not res:
        return ""
    lineas = [("ok", "Sembrados", res.get("insertados")), ("muted", "Ya existían", res.get("existentes")),
              ("muted", "Ya habían empezado", res.get("vencidos")), ("muted", "Desmarcados", res.get("desmarcados"))]
    return "".join(f"<div class='box'><b class='{c}'>{t} ({len(ids)})</b><br><span class='muted'>{_esc(', '.join(ids))}</span></div>"
                   for c, t, ids in lineas if ids)


def _ya_procesado(p: SeedPlan) -> HTMLResponse:
    return _pagina("Plan ya procesado", f"<h1>Plan de siembra #{p.id}: {_esc(p.status)}</h1>"
                                        f"<p class='muted'>Este plan ya no está pendiente. No se hizo nada.</p>{_resultado_html(p.resultado)}")


@router.get("/planes/{plan_id}/aprobar", response_class=HTMLResponse)
async def pagina_aprobar(plan_id: int, t: str | None = None, db: AsyncSession = Depends(get_db)):
    p = await _cargar(db, plan_id, t)
    if p.status != "pending":
        return _ya_procesado(p)
    props = [vista(x) for x in p.plan.get("propuestas", [])]
    filas = "".join(
        f"<tr><td><input type='checkbox' name='ids' value='{_esc(x['doc']['id'])}' checked></td>"
        f"<td>{_esc(x['grupo'])}</td><td><a href='{_esc(x['url'])}'>{_esc(x['titulo'])}</a>"
        + (f"<br><span class='warn'>⚠️ revisar: {_esc('; '.join(x['revisar']))}</span>" if x["revisar"] else "")
        + f"</td><td>{_fmt_mx(datetime.fromisoformat(x['cuando'].replace('Z', '+00:00')))}</td>"
        f"<td class='v'>{_esc(x['precio'])}<br><span class='muted'>{_esc(x['nota'])}</span></td></tr>"
        for x in props
    )
    desc = "".join(f"<li class='muted'>{_esc(d['grupo'])} · {_esc(d['titulo'])}: {_esc(d['motivo'])}</li>"
                   for d in map(vista, p.plan.get("descartes", [])))
    cuerpo = (
        f"<h1>Plan de siembra #{p.id}</h1>"
        f"<p class='muted'>{len(props)} mercados. Partidos: % local/empate/visitante con las cuotas de DraftKings y, "
        f"debajo, lo que da la tabla de ESPN. Crypto: precio de apertura y el spot del día. "
        f"Desmarca los que no quieras: no se vuelven a proponer.</p>"
        f"<form method='post' action='/api/admin/siembra/planes/{p.id}/aprobar?t={_esc(t or '')}'>"
        f"<table><tr><th></th><th>Grupo</th><th>Mercado</th><th>Cierre</th><th>Apertura</th></tr>{filas}</table>"
        f"<button class='btn' type='submit'>Sembrar los marcados</button></form>"
        + (f"<div class='box'><b>Descartados</b><ul>{desc}</ul></div>" if desc else "")
    )
    return _pagina(f"Siembra #{p.id}", cuerpo)


@router.post("/planes/{plan_id}/aprobar", response_class=HTMLResponse)
async def aplicar(plan_id: int, t: str | None = None, ids: list[str] = Form(default=[]),
                  db: AsyncSession = Depends(get_db)):
    p = await _cargar(db, plan_id, t)
    if p.status != "pending":
        return _ya_procesado(p)
    pid, plan = p.id, dict(p.plan or {})
    p.status = "applying"
    await db.commit()
    try:
        res = await job.aplicar_siembra(db, pid, plan, ids)
    except Exception:
        await db.rollback()
        fresh = (await db.execute(select(SeedPlan).where(SeedPlan.id == plan_id))).scalar_one()
        fresh.status = "pending"
        await db.commit()
        raise
    return _pagina(f"Siembra #{plan_id} aplicada",
                   f"<h1>Plan de siembra #{plan_id} aplicado</h1>{_resultado_html(res)}"
                   f"<p><a href='https://veredikt.mx/#/mercados'>Ver mercados →</a></p>")
