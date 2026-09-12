"""Plan de resolución nocturno: listar/disparar planes (admin con Bearer) y
aprobar un plan desde el enlace firmado del correo (sin sesión).

GET  /admin/resolucion/planes/{id}/aprobar?t=…  → página de confirmación (NO ejecuta:
      los clientes de correo pre-cargan los enlaces).
POST /admin/resolucion/planes/{id}/aprobar?t=…  → aplica el plan una sola vez.
"""
from __future__ import annotations

from html import escape as _esc

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_admin
from app.core.background import spawn
from app.database import get_db
from app.models.resolution_plan import ResolutionPlan
from app.models.user import User
from app.services.resolucion import nocturno

router = APIRouter(prefix="/admin/resolucion", tags=["admin"])


def _plan_out(p: ResolutionPlan) -> dict:
    return {
        "id": p.id, "status": p.status, "origen": p.origen, "resumen": p.resumen,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "applied_at": p.applied_at.isoformat() if p.applied_at else None,
        "resultado": p.resultado,
    }


@router.get("/planes")
async def listar_planes(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_admin(current_user)
    res = await db.execute(select(ResolutionPlan).order_by(ResolutionPlan.id.desc()).limit(limit))
    return {"planes": [_plan_out(p) for p in res.scalars().all()], "nightly": nocturno.get_nightly_status()}


@router.get("/planes/{plan_id}")
async def ver_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_admin(current_user)
    p = (await db.execute(select(ResolutionPlan).where(ResolutionPlan.id == plan_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "PLAN_NOT_FOUND", "message": "Plan no encontrado"})
    return {**_plan_out(p), "plan": p.plan}


@router.post("/planes", status_code=202)
async def disparar_plan(
    current_user: User = Depends(get_current_user),
):
    """Arma un plan ahora (en segundo plano: tarda minutos por el throttle de
    TheSportsDB). Consultar GET /planes para ver el resultado."""
    require_admin(current_user)
    spawn(nocturno.correr_plan_nocturno(forzar=True))
    return {"started": True}


class PlanPropuesto(BaseModel):
    resoluciones: list[dict] = Field(min_length=1)
    escalados: list[dict] = []
    nota: str | None = None


@router.post("/planes/proponer", status_code=201)
async def proponer_plan(
    body: PlanPropuesto,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Plan armado por el agente (`agent-resolver.py proponer`): se valida entrada
    por entrada, se guarda como pendiente (origen=agente) y se manda el correo
    con el botón de aprobación. Nada se resuelve aquí."""
    require_admin(current_user)
    try:
        row = await nocturno.proponer_plan(db, body.model_dump())
    except nocturno.PlanInvalido as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "PLAN_INVALIDO", "message": str(e), "errores": e.errores},
        )
    return _plan_out(row)


# ── aprobación desde el correo ───────────────────────────────────────────────

_CSS = """
body{font-family:-apple-system,Inter,sans-serif;background:#0b0b14;color:#f5f0e8;margin:0;padding:32px 16px}
.wrap{max-width:760px;margin:0 auto}h1{font-size:22px;margin:0 0 6px}.muted{color:#a09c94;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid #26263a;vertical-align:top}
th{color:#a09c94;font-weight:500}.v{font-weight:600}.warn{color:#ffd700}
.btn{display:inline-block;background:#ffd700;color:#07071a;font-weight:700;padding:12px 22px;border-radius:10px;border:0;font-size:15px;cursor:pointer}
.ok{color:#00ff88}.bad{color:#ff2d55}a{color:#8ab4ff}.box{background:#12121f;border:1px solid #26263a;border-radius:12px;padding:16px;margin:16px 0}
"""


def _pagina(titulo: str, cuerpo: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(titulo)} · VEREDIKT</title><style>{_CSS}</style></head><body><div class='wrap'>"
        f"<div class='muted' style='letter-spacing:.1em;font-weight:700;color:#ffd700;margin-bottom:14px'>VEREDIKT</div>{cuerpo}</div></body></html>"
    )


def _tabla_resoluciones(plan: dict) -> str:
    filas = []
    for r in sorted(plan.get("resoluciones", []), key=lambda x: (x.get("liga") or "", x["id"])):
        ops = int(r.get("num_trades") or 0)
        warn = f" <span class='warn'>⚠️ {round(float(r.get('volume') or 0))} PT</span>" if ops else ""
        filas.append(
            f"<tr><td>{_esc(r.get('liga') or '')}</td><td>{_esc(r.get('pregunta') or r['id'])}{warn}</td>"
            f"<td class='v'>{_esc(str(r.get('veredicto')))}</td><td>{_esc(r.get('resultado') or '')} "
            f"<a href='{_esc(r.get('fuente_1') or '#')}'>F1</a> <a href='{_esc(r.get('fuente_2') or '#')}'>F2</a></td></tr>"
        )
    return "<table><tr><th>Liga</th><th>Mercado</th><th>Veredicto</th><th>Resultado y fuentes</th></tr>" + "".join(filas) + "</table>"


def _lista_escalados(plan: dict) -> str:
    esc = plan.get("escalados", [])
    if not esc:
        return ""
    items = []
    for e in esc:
        sug = f" · sugerido: <b>{_esc(str(e['veredicto_sugerido']))}</b>" if e.get("veredicto_sugerido") else ""
        ev = f" <a href='{_esc(e['fuente_1'])}'>evidencia</a>" if e.get("fuente_1") else ""
        ev += f" · <a href='{_esc(e['fuente_2'])}'>evidencia 2</a>" if e.get("fuente_2") else ""
        res = f"<br>{_esc(str(e['resultado'])[:300])}" if e.get("resultado") else ""
        citas = "".join(f"<br><i class='muted'>“{_esc(str(c)[:200])}”</i>" for c in (e.get("citas") or [])[:3])
        vol = f" <span class='warn'>⚠️ {e.get('volume')} PT</span>" if (e.get("num_trades") or 0) else ""
        items.append(f"<li><b>{_esc(e.get('pregunta') or e['id'])}</b>{vol}<br><span class='muted'>{_esc(e.get('razon') or '')}{sug}{ev}</span>{res}{citas}</li>")
    return f"<div class='box'><b>Escalados ({len(esc)})</b> — no se resuelven con este plan; ciérralos en <a href='https://veredikt.mx/#/admin'>/admin</a>.<ul>{''.join(items)}</ul></div>"


async def _cargar(db: AsyncSession, plan_id: int, t: str | None) -> ResolutionPlan:
    nonce = nocturno.verify_plan_token(t, plan_id)
    if nonce is None:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PLAN_TOKEN", "message": "Enlace inválido o vencido"})
    p = (await db.execute(select(ResolutionPlan).where(ResolutionPlan.id == plan_id).with_for_update())).scalar_one_or_none()
    if p is None or p.nonce != nonce:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PLAN_TOKEN", "message": "Enlace inválido o vencido"})
    return p


@router.get("/planes/{plan_id}/aprobar", response_class=HTMLResponse)
async def pagina_aprobar(plan_id: int, t: str | None = None, db: AsyncSession = Depends(get_db)):
    p = await _cargar(db, plan_id, t)  # el FOR UPDATE se suelta al cerrar la sesión del request
    r = p.resumen or {}
    if p.status != "pending":
        return _pagina("Plan ya procesado", f"<h1>Plan #{p.id}: {_esc(p.status)}</h1><p class='muted'>Este plan ya no está pendiente. No se hizo nada.</p>{_resultado_html(p.resultado)}")
    cuerpo = (
        f"<h1>Plan de resolución #{p.id}</h1>"
        f"<p class='muted'>{r.get('resoluciones', 0)} resoluciones con doble fuente · {r.get('con_operaciones', 0)} con operaciones · {r.get('volumen', 0)} PT · {r.get('escalados', 0)} escalados</p>"
        f"<form method='post' action='/api/admin/resolucion/planes/{p.id}/aprobar?t={_esc(t or '')}'>"
        f"<button class='btn' type='submit'>Confirmar y resolver {r.get('resoluciones', 0)} mercados</button>"
        f"<span class='muted' style='margin-left:12px'>Irreversible: paga posiciones y manda correos.</span></form>"
        f"{_tabla_resoluciones(p.plan)}{_lista_escalados(p.plan)}"
    )
    return _pagina(f"Plan #{p.id}", cuerpo)


def _resultado_html(res: dict | None) -> str:
    if not res:
        return ""
    filas = "".join(f"<li class='ok'>{_esc(x['id'])} → {_esc(str(x.get('veredicto')))} ({x.get('positions_settled', 0)} posiciones)</li>" for x in res.get("resueltos", []))
    filas += "".join(f"<li class='muted'>{_esc(x['id'])}: saltado ({_esc(x.get('razon') or '')})</li>" for x in res.get("saltados", []))
    filas += "".join(f"<li class='bad'>{_esc(x['id'])}: {_esc(x.get('razon') or '')}</li>" for x in res.get("fallidos", []))
    return (f"<div class='box'><b>Resueltos {len(res.get('resueltos', []))} · saltados {len(res.get('saltados', []))} · "
            f"fallidos {len(res.get('fallidos', []))} · posiciones liquidadas {res.get('posiciones_liquidadas', 0)}</b><ul>{filas}</ul></div>")


@router.post("/planes/{plan_id}/aprobar", response_class=HTMLResponse)
async def aplicar(plan_id: int, t: str | None = None, db: AsyncSession = Depends(get_db)):
    p = await _cargar(db, plan_id, t)
    if p.status != "pending":
        return _pagina("Plan ya procesado", f"<h1>Plan #{p.id}: {_esc(p.status)}</h1><p class='muted'>Ya se había aplicado o venció. No se hizo nada.</p>{_resultado_html(p.resultado)}")
    # Cerrar el lock antes de aplicar (cada resolución hace su propio commit);
    # leer id y plan antes: el commit puede expirar el objeto.
    pid, plan = p.id, dict(p.plan or {})
    p.status = "applying"
    await db.commit()
    try:
        res = await nocturno.aplicar_plan(db, pid, plan)
    except Exception:
        fresh = (await db.execute(select(ResolutionPlan).where(ResolutionPlan.id == plan_id))).scalar_one()
        fresh.status = "pending"
        await db.commit()
        raise
    return _pagina(f"Plan #{plan_id} aplicado", f"<h1>Plan #{plan_id} aplicado</h1>{_resultado_html(res)}<p><a href='https://veredikt.mx/#/admin'>Ir a /admin →</a></p>")
