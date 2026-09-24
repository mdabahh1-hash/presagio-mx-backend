"""Agente revisor: checks puros y flujo de aprobación (casillas, un solo uso,
token propio, valor cambiado desde la propuesta, desmarcados que no vuelven)."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.market import Market, MarketCategory, MarketStatus
from app.models.review_plan import ReviewPlan
from app.services import email as email_mod
from app.services.resolucion import nocturno
from app.services.revision import job
from app.services.revision.checks import agrupar, revisar

AHORA = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
RULES = "Cómo se resuelve: " + "x" * 200
CONTEXT = "c" * 130


def _m(**kw):
    base = dict(id="m1", question="¿Algo pasará?", category=MarketCategory.ECONOMIA, subcategory="Tasas Banxico",
                rules=RULES, context=CONTEXT, resolution_criteria="Criterio", resolution_source_url="https://x.mx",
                image_url="https://upload.wikimedia.org/x.jpg", kind=None, kickoff_at=None, ends_at=AHORA + timedelta(days=5),
                market_type="binary", sujeto=None, auto_resolucion=None, status=MarketStatus.OPEN)
    base.update(kw)
    return SimpleNamespace(**base)


def _checks(m, n=0, pos=False):
    return {x["check"]: x for x in revisar(m, n, pos, AHORA)}


def test_mercado_completo_no_tiene_hallazgos():
    assert _checks(_m()) == {}


def test_partido_sin_fuente_ni_kickoff_se_arregla_solo():
    c = _checks(_m(category=MarketCategory.DEPORTES, subcategory="Liga MX", kind="partido",
                   resolution_source_url=None, rules="x" * 250, market_type="multi"), n=3)
    assert c["fuente"]["fix"]["campo"] == "resolution_source_url" and c["fuente"]["fix"]["despues"].startswith("https://")
    assert c["kickoff"]["fix"] == {"campo": "kickoff_at", "antes": None, "despues": (AHORA + timedelta(days=5)).isoformat()}


def test_avisos_sin_arreglo():
    c = _checks(_m(resolution_source_url=None, rules="corta", context="", resolution_criteria=" ",
                   subcategory=None, image_url=None, question="¿" + "a" * 80 + "?", market_type="multi",
                   status=MarketStatus.PENDING_RESOLUTION, ends_at=AHORA - timedelta(days=4)), n=1, pos=True)
    assert set(c) == {"fuente", "normas", "contexto", "criterios", "subcategoria", "titulo", "multi",
                      "pendiente_viejo", "sin_foto"}
    assert all(x["fix"] is None for x in c.values())
    assert "no se puede tocar" in c["titulo"]["mensaje"]


def test_imagen():
    assert _checks(_m(image_url="http://hotlink.jpg"))["imagen_invalida"]["fix"]["despues"] is None
    assert "sin_foto" in _checks(_m(image_url=None))  # fuera de Deportes, foto por mercado
    dep = dict(category=MarketCategory.DEPORTES, image_url=None)
    assert "imagen_generica" in _checks(_m(subcategory="Pádel", **dep))
    assert _checks(_m(subcategory="Liga MX", **dep)) == {}  # escudo de la liga
    avisos = [_checks(_m(id=f"b{i}", subcategory="Pádel", **dep))["imagen_generica"] for i in range(3)]
    assert agrupar(avisos)[0] == ("Solo ícono genérico de la categoría (3)", ["Pádel: 3 mercados"])


def test_escalera_sin_receta_y_kind_fuera_de_deportes():
    c = _checks(_m(category=MarketCategory.CRYPTO, subcategory="Bitcoin",
                   question="¿Bitcoin cerrará octubre en US$120,000 o más?", kind="partido"))
    assert {"receta", "categoria"} <= set(c)
    assert "receta" not in _checks(_m(question="¿Bitcoin cerrará octubre en US$120,000 o más?",
                                      auto_resolucion={"tipo": "cripto_cierre"}))


@pytest.fixture
def correos(monkeypatch):
    enviados: list[tuple[str, str]] = []

    async def fake_send(to, subject, html, **kw):
        enviados.append((subject, html))

    monkeypatch.setattr(email_mod, "_send", fake_send)
    return enviados


async def test_plan_aprobacion(client, db, correos):
    fin = datetime.now(timezone.utc) + timedelta(days=3)
    for mid in ("p1", "p2"):
        db.add(Market(id=mid, question=f"¿{mid}?", description="d", category=MarketCategory.DEPORTES,
                      subcategory="Liga MX", kind="partido", resolution_criteria="c", rules=RULES, context=CONTEXT,
                      resolution_source_url="https://x.mx", ends_at=fin, status=MarketStatus.OPEN, market_type="multi"))
    await db.commit()

    seco = await job.correr_revision(dry_run=True)
    assert len(seco["nuevos"]) == 4 and (await db.execute(select(ReviewPlan))).first() is None

    row = await job.correr_revision()
    await asyncio.sleep(0)
    assert row.resumen["arreglos"] == 2 and correos and "2 arreglos" in correos[0][0]

    t = nocturno.make_plan_token(row.id, row.nonce, job.TOKEN_TYP)
    r = await client.get(f"/api/admin/revision/planes/{row.id}/aprobar?t={t}")
    assert r.status_code == 200 and r.text.count("type='checkbox'") == 2

    otro = nocturno.make_plan_token(row.id, row.nonce, "seed_approval")
    r = await client.post(f"/api/admin/revision/planes/{row.id}/aprobar?t={otro}", data={"ids": ["p1:kickoff"]})
    assert r.status_code == 400

    # p2 cambió desde la propuesta: se salta
    p2 = await db.get(Market, "p2")
    p2.kickoff_at = fin - timedelta(hours=1)
    await db.commit()
    r = await client.post(f"/api/admin/revision/planes/{row.id}/aprobar?t={t}", data={"ids": ["p1:kickoff", "p2:kickoff"]})
    assert r.status_code == 200 and "Aplicados (1)" in r.text and "cambio_desde_propuesta" in r.text
    p1 = (await db.execute(select(Market).where(Market.id == "p1").execution_options(populate_existing=True))).scalar_one()
    assert p1.kickoff_at == fin

    r = await client.post(f"/api/admin/revision/planes/{row.id}/aprobar?t={t}", data={"ids": ["p1:kickoff"]})
    assert "ya no está pendiente" in r.text
    assert await job.correr_revision() is None  # nada nuevo en 30 días


async def test_desmarcado_no_vuelve(client, db, correos):
    db.add(Market(id="p1", question="¿p1?", description="d", category=MarketCategory.DEPORTES, subcategory="Liga MX",
                  kind="partido", resolution_criteria="c", rules=RULES, context=CONTEXT,
                  resolution_source_url="https://x.mx", ends_at=datetime.now(timezone.utc) + timedelta(days=3),
                  status=MarketStatus.OPEN, market_type="multi"))
    await db.commit()
    row = await job.correr_revision()
    t = nocturno.make_plan_token(row.id, row.nonce, job.TOKEN_TYP)
    await client.post(f"/api/admin/revision/planes/{row.id}/aprobar?t={t}", data={"ids": []})
    seco = await job.correr_revision(dry_run=True)
    assert "p1:kickoff" not in {x["id"] for x in seco["hallazgos"]}
