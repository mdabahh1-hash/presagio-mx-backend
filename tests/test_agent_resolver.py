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
