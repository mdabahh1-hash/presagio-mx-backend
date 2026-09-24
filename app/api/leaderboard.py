"""Aprobación del cierre mensual del leaderboard desde el enlace firmado del
correo (sin sesión). Mismo esquema que `app/api/siembra.py`:

GET  /admin/leaderboard/meses/{id}/aprobar?t=…  → página con casillas «descalificar» (no ejecuta)
POST /admin/leaderboard/meses/{id}/aprobar?t=…  → descalifica, renumera y publica, una sola vez.
"""
from __future__ import annotations

from html import escape as _esc

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.resolucion import _pagina
from app.database import get_db
from app.models.leaderboard_mes import LeaderboardMes
from app.services import leaderboard_mensual as lb
from app.services.resolucion.nocturno import verify_plan_token

router = APIRouter(prefix="/admin/leaderboard", tags=["admin"])


async def _cargar(db: AsyncSession, cierre_id: int, t: str | None) -> LeaderboardMes:
    nonce = verify_plan_token(t, cierre_id, lb.TOKEN_TYP)
    c = None if nonce is None else (await db.execute(
        select(LeaderboardMes).where(LeaderboardMes.id == cierre_id).with_for_update())).scalar_one_or_none()
    if c is None or c.nonce != nonce:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PLAN_TOKEN", "message": "Enlace inválido o vencido"})
    return c


async def _tabla(db: AsyncSession, c: LeaderboardMes, casillas: bool) -> str:
    filas = "".join(
        (f"<tr><td><input type='checkbox' name='descalificar' value='{u.id}'></td>" if casillas else "<tr>")
        + f"<td>{'—' if f.rank is None else f.rank}</td><td>@{_esc(u.username)}<br><span class='muted'>{_esc(u.email)}</span></td>"
        f"<td class='v'>{f.ganancia:+,.0f} PT</td><td class='muted'>{f.n_trades} pred. · {f.n_mercados} merc. · {f.volumen:,.0f} PT</td></tr>"
        for f, u in await lb.filas_de(db, c.mes, 10)
    )
    th = "<th>Descalificar</th>" if casillas else ""
    return f"<table><tr>{th}<th>#</th><th>Usuario</th><th>Ganancia</th><th>Actividad</th></tr>{filas}</table>"


@router.get("/meses/{cierre_id}/aprobar", response_class=HTMLResponse)
async def pagina_aprobar(cierre_id: int, t: str | None = None, db: AsyncSession = Depends(get_db)):
    c = await _cargar(db, cierre_id, t)
    if c.status != "pending":
        return _pagina("Mes ya publicado", f"<h1>Leaderboard {c.mes}: publicado</h1>{await _tabla(db, c, False)}")
    cuerpo = (
        f"<h1>Leaderboard {c.mes}</h1>"
        f"<p class='muted'>Top 10 de los elegibles ({lb.MIN_PREDICCIONES}+ predicciones en {lb.MIN_MERCADOS}+ mercados). "
        f"Marca a quien quieras descalificar; los demás suben de lugar. Al publicar, el top {lb.PREMIADOS} sale en /clasificacion.</p>"
        f"<form method='post' action='/api/admin/leaderboard/meses/{c.id}/aprobar?t={_esc(t or '')}'>"
        f"{await _tabla(db, c, True)}<button class='btn' type='submit'>Publicar ganadores</button></form>"
    )
    return _pagina(f"Leaderboard {c.mes}", cuerpo)


@router.post("/meses/{cierre_id}/aprobar", response_class=HTMLResponse)
async def aplicar(cierre_id: int, t: str | None = None, descalificar: list[int] = Form(default=[]),
                  db: AsyncSession = Depends(get_db)):
    c = await _cargar(db, cierre_id, t)
    if c.status == "pending":
        await lb.aprobar(db, c, set(descalificar))
    return _pagina(f"Leaderboard {c.mes} publicado",
                   f"<h1>Leaderboard {c.mes}: publicado</h1>{await _tabla(db, c, False)}"
                   f"<p><a href='https://veredikt.mx/#/clasificacion'>Ver clasificación →</a></p>")
