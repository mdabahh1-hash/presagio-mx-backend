"""Agente revisor: listar/disparar planes (admin con Bearer) y aprobar un plan desde
el enlace firmado del correo (sin sesión), arreglo por arreglo.

GET  /admin/revision/planes/{id}/aprobar?t=…  → página con casillas (NO ejecuta:
      los clientes de correo pre-cargan los enlaces).
POST /admin/revision/planes/{id}/aprobar?t=…  → aplica los marcados, una sola vez.
"""
from __future__ import annotations

from html import escape as _esc

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.resolucion import _pagina
from app.core.auth import get_current_user, require_admin
from app.database import get_db
from app.models.review_plan import ReviewPlan
from app.models.user import User
from app.services.resolucion.nocturno import verify_plan_token
from app.services.revision import job
from app.services.revision.checks import agrupar

router = APIRouter(prefix="/admin/revision", tags=["admin"])


@router.get("/planes")
async def listar_planes(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_admin(current_user)
    filas = (await db.execute(select(ReviewPlan).order_by(ReviewPlan.id.desc()).limit(20))).scalars()
    return [{"id": p.id, "status": p.status, "resumen": p.resumen, "resultado": p.resultado,
             "created_at": p.created_at, "applied_at": p.applied_at} for p in filas]


@router.post("/planes")
async def disparar_plan(dry_run: bool = False, current_user: User = Depends(get_current_user)):
    """Revisa ahora. `dry_run` devuelve los hallazgos sin guardar ni mandar correo."""
    require_admin(current_user)
    r = await job.correr_revision(dry_run=dry_run)
    if dry_run:
        return r
    return {"plan_id": r.id if r else None, "resumen": r.resumen if r else None}


async def _cargar(db: AsyncSession, plan_id: int, t: str | None) -> ReviewPlan:
    nonce = verify_plan_token(t, plan_id, job.TOKEN_TYP)
    p = None if nonce is None else (await db.execute(
        select(ReviewPlan).where(ReviewPlan.id == plan_id).with_for_update())).scalar_one_or_none()
    if p is None or p.nonce != nonce:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PLAN_TOKEN", "message": "Enlace inválido o vencido"})
    return p


def _resultado_html(res: dict | None) -> str:
    if not res:
        return ""
    saltados = [f"{s['id']} ({s['motivo']})" for s in res.get("saltados", [])]
    lineas = [("ok", "Aplicados", res.get("aplicados")), ("warn", "Saltados", saltados),
              ("muted", "Desmarcados (no se vuelven a proponer)", res.get("desmarcados"))]
    return "".join(f"<div class='box'><b class='{c}'>{t} ({len(ids)})</b><br><span class='muted'>{_esc(', '.join(ids))}</span></div>"
                   for c, t, ids in lineas if ids)


def _ya_procesado(p: ReviewPlan) -> HTMLResponse:
    return _pagina("Plan ya procesado", f"<h1>Revisión #{p.id}: {_esc(p.status)}</h1>"
                                        f"<p class='muted'>Este plan ya no está pendiente. No se hizo nada.</p>{_resultado_html(p.resultado)}")


def _mercado(x: dict) -> str:
    return f"<a href='https://veredikt.mx/#/mercado/{_esc(x['market_id'])}'>{_esc(x['pregunta'])}</a>"


@router.get("/planes/{plan_id}/aprobar", response_class=HTMLResponse)
async def pagina_aprobar(plan_id: int, t: str | None = None, db: AsyncSession = Depends(get_db)):
    p = await _cargar(db, plan_id, t)
    if p.status != "pending":
        return _ya_procesado(p)
    hs = p.plan.get("hallazgos", [])
    fixes, avisos = [x for x in hs if x["fix"]], [x for x in hs if not x["fix"]]
    filas = "".join(
        f"<tr><td><input type='checkbox' name='ids' value='{_esc(x['id'])}' checked></td>"
        f"<td>{_mercado(x)}<br><span class='muted'>{_esc(x['mensaje'])}</span></td>"
        f"<td><code>{_esc(x['fix']['campo'])}</code><br>{_esc(str(x['fix']['antes']))} → "
        f"<span class='v'>{_esc(str(x['fix']['despues']))}</span></td></tr>"
        for x in fixes)
    lista = "".join(f"<p><b>{_esc(titulo)}</b></p><ul>" + "".join(f"<li class='muted'>{_esc(f)}</li>" for f in filas) + "</ul>"
                    for titulo, filas in agrupar(avisos))
    form = (f"<form method='post' action='/api/admin/revision/planes/{p.id}/aprobar?t={_esc(t or '')}'>"
            f"<table><tr><th></th><th>Mercado</th><th>Cambio</th></tr>{filas}</table>"
            f"<button class='btn' type='submit'>Aplicar los marcados</button></form>") if fixes else \
        "<p class='muted'>No hay arreglos automáticos en este plan.</p>"
    cuerpo = (f"<h1>Revisión de mercados #{p.id}</h1>"
              f"<p class='muted'>{len(fixes)} arreglos y {len(avisos)} avisos. Desmarca los arreglos que no quieras: "
              f"no se vuelven a proponer. El agente nunca toca la pregunta ni los criterios.</p>{form}"
              + (f"<div class='box'><b>Revisar a mano ({len(avisos)})</b>{lista}</div>" if avisos else ""))
    return _pagina(f"Revisión #{p.id}", cuerpo)


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
        res = await job.aplicar_revision(db, pid, plan, ids)
    except Exception:
        await db.rollback()
        fresh = (await db.execute(select(ReviewPlan).where(ReviewPlan.id == plan_id))).scalar_one()
        fresh.status = "pending"
        await db.commit()
        raise
    return _pagina(f"Revisión #{plan_id} aplicada",
                   f"<h1>Revisión #{plan_id} aplicada</h1>{_resultado_html(res)}"
                   f"<p><a href='https://veredikt.mx/#/mercados'>Ver mercados →</a></p>")
