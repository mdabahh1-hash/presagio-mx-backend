"""Validación pura del plan de resoluciones (agent-resolver.py). Sin BD ni red."""
import importlib.util
import os
from datetime import datetime, timedelta, timezone

import pytest

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent-resolver.py")
_spec = importlib.util.spec_from_file_location("agent_resolver", _PATH)
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)

AHORA = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)


def _multi(**over):
    d = {
        "id": "pl-city-coventry-j3-2627", "status": "pending_resolution", "market_type": "multi",
        "ends_at": "2026-09-05T14:00:00Z",
        "outcomes": [{"outcome_key": k} for k in ("home", "draw", "away")],
    }
    d.update(over)
    return d


def _binario(**over):
    d = {"id": "pl-titular-gakpo-j2", "status": "pending_resolution", "market_type": "binary",
         "ends_at": "2026-08-30T14:00:00Z", "outcomes": []}
    d.update(over)
    return d


def _entrada(**over):
    e = {"id": "pl-city-coventry-j3-2627", "veredicto": "home", "resultado": "Man City 3-0 Coventry",
         "fuente_1": "https://www.premierleague.com/match/1", "fuente_2": "https://www.espn.com/soccer/x",
         "confianza": "alta"}
    e.update(over)
    return e


def test_entrada_correcta_multi():
    assert ar.validar_entrada(_entrada(), _multi(), AHORA) == []


def test_entrada_correcta_binaria():
    assert ar.validar_entrada(_entrada(veredicto="NO"), _binario(), AHORA) == []


def test_outcome_key_invalido():
    errs = ar.validar_entrada(_entrada(veredicto="local"), _multi(), AHORA)
    assert any("outcome_key" in e for e in errs)


def test_binario_exige_yes_no():
    errs = ar.validar_entrada(_entrada(veredicto="home"), _binario(), AHORA)
    assert any("YES o NO" in e for e in errs)


def test_mismo_host_en_fuentes():
    errs = ar.validar_entrada(
        _entrada(fuente_2="https://premierleague.com/match/2"), _multi(), AHORA
    )
    assert any("mismo host" in e for e in errs)


def test_fuente_no_url():
    errs = ar.validar_entrada(_entrada(fuente_2="ESPN"), _multi(), AHORA)
    assert any("fuente_2" in e for e in errs)


def test_confianza_media_bloquea():
    errs = ar.validar_entrada(_entrada(confianza="media"), _multi(), AHORA)
    assert any("confianza" in e for e in errs)


def test_mercado_ya_resuelto():
    errs = ar.validar_entrada(_entrada(), _multi(status="resolved"), AHORA)
    assert any("pending_resolution" in e for e in errs)


def test_mercado_aun_abierto():
    futuro = (AHORA + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    errs = ar.validar_entrada(_entrada(), _multi(ends_at=futuro), AHORA)
    assert any("futuro" in e for e in errs)


def test_mercado_inexistente():
    assert ar.validar_entrada(_entrada(), {"http_error": 404}, AHORA) == ["mercado no encontrado en el API"]
    assert ar.validar_entrada(_entrada(), None, AHORA) == ["mercado no encontrado en el API"]


def test_falta_resultado():
    errs = ar.validar_entrada(_entrada(resultado=""), _multi(), AHORA)
    assert any("resultado" in e for e in errs)


# ── accesorios de jugador: identidad confirmada (caso Josh Allen, Semana 1) ──

SUJETO_ALLEN = {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "posicion": "QB",
                "alcance": "partido", "ids": {"espn": "3918298", "cbs": "2181054"}}
PREGUNTA_ALLEN = "¿Josh Allen lanzará 2 o más pases de touchdown contra los Texans en la Semana 1?"
CONFIRMADO_ALLEN = {"jugador": "Josh Allen", "equipo": "Buffalo Bills", "partido": "BUF@HOU",
                    "espn": {"id": "3918298", "nombre": "Josh Allen", "abbr": "BUF", "equipo": "Buffalo Bills"},
                    "cbs": {"id": "2181054", "nombre": "Josh Allen", "abbr": "BUF", "equipo": "Buffalo Bills"}}


def _prop(**over):
    d = _binario(id="nfl-allen-2tdpass-w1-2026", category="Deportes", subcategory="NFL", question=PREGUNTA_ALLEN,
                 sujeto=SUJETO_ALLEN)
    d.update(over)
    return d


def _entrada_prop(**over):
    e = _entrada(id="nfl-allen-2tdpass-w1-2026", veredicto="YES", resultado="BUF 36-31 HOU — 2 pases de TD",
                 fuente_1="https://www.espn.com/nfl/game/_/gameId/401872660",
                 fuente_2="https://www.cbssports.com/nfl/gametracker/boxscore/NFL_20260913_BUF@HOU/",
                 sujeto_confirmado=CONFIRMADO_ALLEN)
    e.update(over)
    return e


def test_prop_con_identidad_confirmada_pasa():
    assert ar.validar_entrada(_entrada_prop(), _prop(), AHORA) == []


def test_prop_sin_sujeto_en_el_mercado_se_rechaza():
    errs = ar.validar_entrada(_entrada_prop(), _prop(sujeto=None), AHORA)
    assert any("sin sujeto" in e for e in errs)


def test_prop_sin_sujeto_confirmado_se_rechaza():
    errs = ar.validar_entrada(_entrada_prop(sujeto_confirmado=None), _prop(), AHORA)
    assert any("sujeto_confirmado" in e for e in errs)


def test_prop_con_el_homonimo_se_rechaza():
    hines = {**CONFIRMADO_ALLEN, "espn": {"id": "3915239", "nombre": "Josh Hines-Allen", "equipo": "Jacksonville Jaguars"}}
    errs = ar.validar_entrada(_entrada_prop(sujeto_confirmado=hines), _prop(), AHORA)
    assert any("espn.id" in e for e in errs) and any("espn.equipo" in e for e in errs)


def test_prop_fuente_sin_bloque_o_host_desconocido():
    sin_cbs = {k: v for k, v in CONFIRMADO_ALLEN.items() if k != "cbs"}
    errs = ar.validar_entrada(_entrada_prop(sujeto_confirmado=sin_cbs), _prop(), AHORA)
    assert any("no trae 'cbs'" in e for e in errs)
    errs = ar.validar_entrada(_entrada_prop(fuente_2="https://www.nfl.com/games/x"), _prop(), AHORA)
    assert any("manual" in e for e in errs)
    # `manual` acompaña pero no sustituye el id obligatorio de CBS en la NFL
    manual = {**CONFIRMADO_ALLEN, "manual": {"equipo": "Buffalo Bills", "nota": "gamebook oficial"}}
    errs = ar.validar_entrada(_entrada_prop(fuente_2="https://www.nfl.com/games/x", sujeto_confirmado=manual), _prop(), AHORA)
    assert errs and all("por id en cbs" in e for e in errs)


def test_prop_sin_ningun_id_confirmado_se_rechaza():
    """TheSportsDB (por nombre) + host manual, o dos hosts manuales: ningún id
    confirmado; antes pasaban con confianza alta."""
    nota = {"equipo": "Buffalo Bills", "nota": "lo vi"}
    tsdb = {"jugador": "Josh Allen", "equipo": "Buffalo Bills", "manual": nota,
            "tsdb": {"nombre": "Josh Allen", "equipo": "Buffalo Bills"}}
    for f1, sc in (("https://www.thesportsdb.com/event/1", tsdb),
                   ("https://www.pro-football-reference.com/b", {"jugador": "Josh Allen", "equipo": "Buffalo Bills", "manual": nota})):
        errs = ar.validar_entrada(_entrada_prop(veredicto="NO", fuente_1=f1, fuente_2="https://www.nfl.com/games/x",
                                                sujeto_confirmado=sc), _prop(), AHORA)
        assert any("por id en espn" in e for e in errs) and any("por id en cbs" in e for e in errs)


def test_prop_cancelar_basta_el_equipo():
    e = _entrada_prop(veredicto="CANCELAR", sujeto_confirmado={"equipo": "Buffalo Bills"})
    assert ar.validar_entrada(e, _prop(), AHORA) == []
    errs = ar.validar_entrada({**e, "sujeto_confirmado": {"equipo": "Houston Texans"}}, _prop(), AHORA)
    assert any("equipo" in x for x in errs)


def test_accesorio_de_equipo_no_exige_sujeto():
    d = _binario(category="Deportes", subcategory="NFL", question="¿Los Bills ganarán por más de 7 puntos a los Texans?")
    assert ar.validar_entrada(_entrada(veredicto="NO"), d, AHORA) == []


def test_texto_identidad():
    assert ar.texto_identidad(CONFIRMADO_ALLEN) == "Josh Allen · Buffalo Bills · BUF@HOU · ESPN 3918298 · CBS 2181054"
    assert ar.texto_identidad(None) == ""


# ── backfill: sujetos-generar / sujetos (sin red: API y buscar_ids simulados) ──

def _mercado_api(**over):
    return _prop(status="open", ends_at="2026-09-13T17:00:00Z", **over)


def test_sujetos_dry_run_valida_y_no_escribe(tmp_path, monkeypatch, capsys):
    arch = tmp_path / "sujetos.yaml"
    arch.write_text("nfl-allen-2tdpass-w1-2026:\n  jugador: Josh Allen\n  equipo: Bills\n  rival: Texans\n"
                    "  posicion: qb\n  alcance: partido\n  ids: {espn: 3918298, cbs: 2181054}\n")
    monkeypatch.setattr(ar, "_detalles", lambda ids: {i: _mercado_api(sujeto=None) for i in ids})
    monkeypatch.setattr(ar, "_auth", lambda *a, **k: pytest.fail("dry-run no debe llamar al API admin"))
    ar.cmd_sujetos(str(arch), apply=False, only=None)
    out = capsys.readouterr().out
    assert "ESPN 3918298 · CBS 2181054 · sin sujeto" in out and "--apply" in out

    llamadas = []
    monkeypatch.setattr(ar, "_auth", lambda path, data=None, method=None: llamadas.append((path, data, method)) or {"ok": True})
    ar.cmd_sujetos(str(arch), apply=True, only=None)
    assert llamadas == [("/admin/markets/nfl-allen-2tdpass-w1-2026", {"sujeto": SUJETO_ALLEN}, "PATCH")]


def test_sujetos_con_errores_no_aplica(tmp_path, monkeypatch):
    arch = tmp_path / "sujetos.yaml"
    arch.write_text("nfl-allen-2tdpass-w1-2026:\n  jugador: Josh Hines-Allen\n  equipo: Jaguars\n  rival: Browns\n"
                    "  posicion: DE\n  alcance: partido\n  ids: {espn: '3915239', cbs: '2184628'}\n")
    monkeypatch.setattr(ar, "_detalles", lambda ids: {i: _mercado_api(sujeto=None) for i in ids})
    monkeypatch.setattr(ar, "_auth", lambda *a, **k: pytest.fail("con errores no se escribe nada"))
    with pytest.raises(SystemExit) as ex:
        ar.cmd_sujetos(str(arch), apply=True, only=None)
    assert "no se aplicó nada" in str(ex.value)


def test_sujetos_generar_arma_yaml(tmp_path, monkeypatch):
    import yaml
    from app.services.resolucion import identidad

    otro = _mercado_api(id="nfl-sin-base-w1-2026", sujeto=None,
                        question="¿Kyle Allen lanzará 2 o más pases de touchdown contra los Texans en la Semana 1?")
    monkeypatch.setattr(ar, "_fetch_markets", lambda status: [_mercado_api(), otro, _binario(status="open")] if status == "active" else [])
    monkeypatch.setattr(ar, "_detalles", lambda ids: {i: (otro if i == otro["id"] else _mercado_api(sujeto=None)) for i in ids})
    vistos = []

    def fake_buscar_ids(http, liga, base, fecha=None):
        vistos.append((liga, dict(base)))
        return {**base, "posicion": "QB", "ids": {"espn": "3918298", "cbs": "2181054"}}, [], []

    monkeypatch.setattr(identidad, "buscar_ids", fake_buscar_ids)
    out = tmp_path / "sujetos.yaml"
    with pytest.raises(SystemExit) as ex:  # el mercado sin base en market_content ni sujeto → código 1
        ar.cmd_sujetos_generar(str(out), only=None)
    assert ex.value.code == 1
    # la base sale de market_content/nfl.py:PROPS, nunca de adivinar
    assert vistos == [("NFL", {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "alcance": "partido"})]
    texto = out.read_text()
    assert yaml.safe_load(texto) == {"nfl-allen-2tdpass-w1-2026": {**SUJETO_ALLEN}}
    assert "# nfl-sin-base-w1-2026:" in texto and "sin base" in texto
