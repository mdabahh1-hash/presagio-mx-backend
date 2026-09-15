"""Correos a usuarios (marca v2, tema claro): estructura, enlaces, escape y
ausencia de los tokens de la marca v1. Los correos al admin siguen con `_wrap`."""
from datetime import datetime, timezone

import pytest

from app.services import email as email_mod

PREGUNTA = "¿Rayados <gana> & Tigres empata?"
PROHIBIDO = ["#07071A", "#FFD700", "#00FF88", "#FF2D55", "font-weight: 800", "font-weight:800",
             "font-weight: 900", "font-weight:900", "Courier", "¡", "✅", "⏰", "🔔", "→", "linear-gradient"]


@pytest.fixture
def enviados(monkeypatch):
    out: list[dict] = []

    async def fake_send(to, subject, html, text=None):
        out.append({"to": to, "subject": subject, "html": html, "text": text})

    monkeypatch.setattr(email_mod, "_send", fake_send)
    return out


def _comun(m: dict, con_pregunta: bool = True):
    html, text = m["html"], m["text"]
    assert html.startswith("<!DOCTYPE html>")
    assert "https://veredikt.mx/logo.png" in html
    assert ">VEREDIKT<" in html  # wordmark como texto vivo
    if con_pregunta:
        assert "&lt;gana&gt; &amp; Tigres" in html  # pregunta escapada
        assert PREGUNTA in text  # y literal en texto plano
    for t in PROHIBIDO:
        assert t not in html, t
        assert t not in m["subject"], t
    assert html.count("#E6B422") <= 1  # a lo sumo un botón dorado
    assert text and "<p" not in text and "<table" not in text and "VEREDIKT" in text


@pytest.mark.asyncio
async def test_verificacion(enviados):
    await email_mod.send_verification_email("a@b.mx", "Ana", "123456")
    m = enviados[0]
    _comun(m, con_pregunta=False)
    assert m["subject"] == "123456 es tu código de verificación VEREDIKT"
    assert "123456" in m["html"] and "123456" in m["text"]
    assert "#E6B422" not in m["html"]  # sin botón
    assert "/#/perfil" not in m["html"]  # transaccional: sin línea de baja


@pytest.mark.asyncio
async def test_resuelto_acierto(enviados):
    await email_mod.send_resolution_email("a@b.mx", "Ana", PREGUNTA, True, 250.4, market_id="mkt-1")
    m = enviados[0]
    _comun(m)
    assert m["subject"].startswith("Acertaste: ")
    assert "Acierto" in m["html"] and "+250 PT" in m["html"]
    assert "https://veredikt.mx/#/mercado/mkt-1" in m["html"]
    assert "https://veredikt.mx/#/mercado/mkt-1" in m["text"]
    assert "https://veredikt.mx/#/perfil" in m["html"]
    assert m["html"].count("#E6B422") == 1


@pytest.mark.asyncio
async def test_resuelto_fallo_sin_id(enviados):
    await email_mod.send_resolution_email("a@b.mx", "Ana", PREGUNTA, False, 0.0)
    m = enviados[0]
    _comun(m)
    assert m["subject"].startswith("Se resolvió: ")
    assert "Fallo" in m["html"] and "0 PT" in m["html"]
    assert "https://veredikt.mx/#/mercados" in m["html"]


@pytest.mark.asyncio
async def test_cancelado(enviados):
    await email_mod.send_market_cancelled_email("a@b.mx", "Ana", PREGUNTA, 120.0)
    m = enviados[0]
    _comun(m)
    assert m["subject"].startswith("Mercado cancelado: ")
    assert "+120 PT" in m["html"] and "No cuenta como acierto ni como fallo" in m["html"]


@pytest.mark.asyncio
async def test_cierra_pronto(enviados):
    await email_mod.send_closing_soon_email("a@b.mx", "Ana", PREGUNTA, datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc), "mkt-2")
    m = enviados[0]
    _comun(m)
    assert m["subject"].startswith("Cierra pronto: ")
    assert "19 sep, 19:00 (CDMX)" in m["html"]
    assert "https://veredikt.mx/#/mercado/mkt-2" in m["html"]


def test_asunto_recorta():
    s = email_mod._asunto("Acertaste", "x" * 100)
    assert len(s) <= len("Acertaste: ") + 70 and s.endswith("…")


@pytest.mark.asyncio
async def test_admin_sigue_con_wrap(enviados):
    """Guardia: los correos al admin no cambian de diseño."""
    await email_mod.send_admin_resolution_reminder([("m1", "¿Pregunta?", datetime.now(timezone.utc))])
    assert "#07071A" in enviados[0]["html"] and enviados[0]["to"] == email_mod._ADMIN_EMAIL
