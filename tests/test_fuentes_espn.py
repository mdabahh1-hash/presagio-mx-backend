"""fuentes.espn_scoreboard: una petición por día (ESPN dejó de aceptar el rango
`dates=D1-D2`, 2026-09-16) y sin duplicar eventos que aparecen en dos días."""
from datetime import datetime, timezone

from app.services.resolucion import fuentes
from tests.fakes import FakeHttp


def _evento(id_: str, fecha: str, local: str, visitante: str, estado: str = "STATUS_SCHEDULED",
            clock: str | None = None, period: int | None = None, hs: str = "0", as_: str = "0") -> dict:
    status: dict = {"type": {"name": estado, "completed": estado in ("STATUS_FULL_TIME", "STATUS_FINAL")}}
    if clock is not None:
        status["displayClock"] = clock
    if period is not None:
        status["period"] = period
    return {
        "id": id_, "date": fecha,
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"displayName": local, "abbreviation": local[:3].upper()}, "score": hs},
            {"homeAway": "away", "team": {"displayName": visitante, "abbreviation": visitante[:3].upper()}, "score": as_},
        ]}],
        "status": status,
    }


def test_scoreboard_pide_un_dia_a_la_vez_y_no_duplica():
    a = _evento("1", "2026-09-19T23:00Z", "Atlas", "Pumas UNAM")
    b = _evento("2", "2026-09-20T03:15Z", "América", "Guadalajara")
    http = FakeHttp({
        "scoreboard?dates=20260918": {"events": [a]},
        "scoreboard?dates=20260919": {"events": [a, b]},   # ESPN agrupa por día de la costa este
        "scoreboard?dates=20260920": {"events": [b]},
    })
    dia = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    partidos = fuentes.espn_scoreboard(http, "Liga MX", dia, dia)

    assert [p.id for p in partidos] == ["1", "2"]
    assert partidos[1].home == "América" and partidos[1].away == "Guadalajara"
    assert len(http.urls) == 3
    assert all("dates=2026091" in u or "dates=20260920" in u for u in http.urls)
    assert not any("-2026" in u.split("dates=")[1] for u in http.urls), "no debe pedir rangos D1-D2"


def test_scoreboard_conserva_marcador_en_vivo():
    e = _evento("9", "2026-09-20T01:10Z", "Monterrey", "Cruz Azul", estado="STATUS_SECOND_HALF",
                clock="58'", period=2, hs="1", as_="0")
    http = FakeHttp({"scoreboard?dates=": {"events": [e]}})
    dia = datetime(2026, 9, 20, 1, tzinfo=timezone.utc)
    [p] = fuentes.espn_scoreboard(http, "Liga MX", dia, dia)
    assert p.estado == fuentes.LIVE
    assert (p.home_score, p.away_score) == (1, 0)
