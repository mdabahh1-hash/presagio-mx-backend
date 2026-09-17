"""Marcador en vivo (app/services/en_vivo.py + GET /api/markets/en-vivo): parseo del reloj
de ESPN, tick con scoreboard simulado y endpoint apagado/encendido."""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.outcome import Outcome
from app.services import en_vivo
from app.services.resolucion import fuentes
from app.services.resolucion.fuentes import LIVE, Partido

UTC = timezone.utc


def _evento(estado: str, clock: str | None = None, period: int | None = None) -> dict:
    status: dict = {"type": {"name": estado, "completed": False, "shortDetail": "2nd Half"}}
    if clock is not None:
        status["displayClock"] = clock
    if period is not None:
        status["period"] = period
    return {
        "id": "401", "date": "2026-09-20T03:15Z",
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"displayName": "América"}, "score": "1"},
            {"homeAway": "away", "team": {"displayName": "Guadalajara"}, "score": "0"},
        ]}],
        "status": status,
    }


def test_espn_partido_lee_reloj_y_periodo_solo_en_vivo():
    p = fuentes._espn_partido(_evento("STATUS_SECOND_HALF", "58'", 2), "Liga MX")
    assert (p.estado, p.reloj, p.periodo, p.detalle) == (LIVE, "58'", 2, "2nd Half")
    assert (p.home_score, p.away_score) == (1, 0)
    q = fuentes._espn_partido(_evento("STATUS_SCHEDULED", "0'", 0), "Liga MX")
    assert q.reloj is None and q.periodo is None and q.home_score is None


def _partido_mx(mid: str, kickoff: datetime, status: MarketStatus) -> tuple[Market, list[Outcome]]:
    m = Market(
        id=mid, question="¿Quién gana América vs Guadalajara?", description="1X2", category=MarketCategory.DEPORTES,
        subcategory="Liga MX", kind="partido", resolution_criteria="r", ends_at=kickoff, kickoff_at=kickoff,
        b=3000.0, q_yes=0.0, q_no=0.0, yes_price=0.0, status=status, market_type="multi",
    )
    outs = [Outcome(market_id=mid, outcome_key="local", label="🏠 América", q=0.0, price=45.0),
            Outcome(market_id=mid, outcome_key="empate", label="🤝 Empate", q=0.0, price=27.0),
            Outcome(market_id=mid, outcome_key="visitante", label="✈️ Guadalajara", q=0.0, price=28.0)]
    return m, outs


@pytest.mark.asyncio
async def test_tick_marca_el_partido_en_ventana_y_cierra_el_vencido(db, client, monkeypatch):
    ahora = datetime.now(UTC)
    m, outs = _partido_mx("vivo-clasico", ahora - timedelta(hours=1), MarketStatus.OPEN)  # el cierre aún no lo alcanzó
    lejos, outs2 = _partido_mx("vivo-lejos", ahora + timedelta(days=2), MarketStatus.OPEN)
    db.add_all([m, lejos]); await db.flush(); db.add_all(outs + outs2); await db.commit()

    def scoreboard_falso(http, liga, desde, hasta):
        assert liga == "Liga MX"
        return [Partido(fuente="espn", id="401", url="https://www.espn.com/soccer/match/_/gameId/401",
                        kickoff=ahora - timedelta(hours=1), home="América", away="Guadalajara",
                        home_score=1, away_score=0, estado=LIVE, reloj="58'", periodo=2)]
    monkeypatch.setattr(en_vivo, "espn_scoreboard", scoreboard_falso)

    assert await en_vivo.tick(ahora) == 1
    [e] = en_vivo.estados()
    assert e["market_id"] == "vivo-clasico" and e["estado"] == "LIVE"
    assert (e["marcador_local"], e["marcador_visitante"], e["reloj"], e["periodo"]) == (1, 0, "58'", 2)
    assert en_vivo.get_en_vivo_status()["en_vivo"] == 1

    # El tick cerró el partido ya iniciado (informativo: no se puede operar en juego)
    detalle = await client.get("/api/markets/vivo-clasico")
    assert detalle.json()["status"] == "pending_resolution"

    monkeypatch.setattr(settings, "EN_VIVO_ENABLED", False)
    assert (await client.get("/api/markets/en-vivo")).json() == []
    monkeypatch.setattr(settings, "EN_VIVO_ENABLED", True)
    body = (await client.get("/api/markets/en-vivo")).json()
    assert [x["market_id"] for x in body] == ["vivo-clasico"]


@pytest.mark.asyncio
async def test_tick_sin_candidatos_vacia_el_estado(db, monkeypatch):
    en_vivo._ESTADO = {"x": None}  # type: ignore[assignment]
    monkeypatch.setattr(en_vivo, "espn_scoreboard", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe pedir ESPN")))
    assert await en_vivo.tick() == 0
    assert en_vivo.estados() == []
