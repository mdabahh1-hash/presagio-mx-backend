"""Recetas de resolución mecánica (recetas.py): validación, evaluación y
resolución con lectores simulados (sin red)."""
from datetime import date, datetime, timezone

from app.services.resolucion import recetas
from app.services.resolucion.recetas import Lectura, RecetaError, validar_receta, resolver_receta
from app.services.resolucion.validar import es_fuente_confiable, validar_entrada

AHORA = datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc)


def _m(receta: dict, mid: str = "btc-cierre-100k-2026", ends="2026-12-31T23:59:00Z") -> dict:
    return {"id": mid, "question": "¿Bitcoin cerrará 2026 en US$100,000 o más?", "market_type": "binary",
            "category": "Crypto", "subcategory": "Bitcoin", "ends_at": ends, "volume": 0, "num_trades": 0,
            "auto_resolucion": receta}


R_CIERRE = {"fuente": "cripto_cierre", "params": {"indice": "BRR", "symbol": "BTCUSDT"}, "fecha": "2026-12-31", "op": ">=", "valor": 100000}


def test_validar_receta():
    assert validar_receta(R_CIERRE) == []
    assert "fuente desconocida" in validar_receta({"fuente": "x"})[0]
    assert any("solo aplican a mercados binarios" in e for e in validar_receta(R_CIERRE, "multi"))
    assert any("op debe ser" in e for e in validar_receta({**R_CIERRE, "op": "!="}))
    assert any("valor debe ser numérico" in e for e in validar_receta({**R_CIERRE, "valor": "cien"}))
    assert any("fecha no es AAAA-MM-DD" in e for e in validar_receta({**R_CIERRE, "fecha": "31/12/2026"}))
    assert any("necesita params.indice" in e for e in validar_receta({**R_CIERRE, "params": {}}))
    toca = {"fuente": "cripto_toca", "params": {"symbol": "BTCUSDT", "campo": "high", "agg": "max"}, "desde": "2026-08-27", "fecha": "2026-12-31", "op": ">=", "valor": 120000}
    assert validar_receta(toca) == []
    assert any("campo debe ser" in e for e in validar_receta({**toca, "params": {"symbol": "BTCUSDT", "campo": "x", "agg": "max"}}))
    fed = {"fuente": "fed_tasa", "params": {"decision": "2026-09-16", "tipo": "mantiene"}}
    assert validar_receta(fed) == []
    assert any("params.tipo" in e for e in validar_receta({"fuente": "fed_tasa", "params": {"decision": "2026-09-16", "tipo": "igual"}}))
    assert any("params.decision" in e for e in validar_receta({"fuente": "banxico_tasa", "params": {"tipo": "baja"}}))


def _lectura(valor, fuente="cfbenchmarks", url="https://www.cfbenchmarks.com/data/indices/BRR"):
    return Lectura(valor, url, "2026-12-31", f"{fuente} {valor}", fuente)


def test_resolver_receta_acuerdo_y_discrepancia(monkeypatch):
    monkeypatch.setattr(recetas, "leer_cf", lambda http, indice, dia: _lectura(103210.5))
    monkeypatch.setattr(recetas, "leer_binance", lambda http, symbol, dia: _lectura(103180.0, "binance", "https://www.binance.com/en/trade/BTCUSDT"))
    e = resolver_receta(_m(R_CIERRE), http=object(), ahora=AHORA)
    assert e["veredicto"] == "YES" and e["confianza"] == "alta"
    assert e["fuente_1"].startswith("https://www.cfbenchmarks.com") and e["fuente_2"].startswith("https://www.binance.com")
    assert ">= 100,000.00 → YES" in e["resultado"]
    # NO cuando el valor no cumple
    monkeypatch.setattr(recetas, "leer_cf", lambda http, indice, dia: _lectura(99999.0))
    monkeypatch.setattr(recetas, "leer_binance", lambda http, symbol, dia: _lectura(99980.0, "binance"))
    assert resolver_receta(_m(R_CIERRE), http=object(), ahora=AHORA)["veredicto"] == "NO"
    # discrepancia en el veredicto → escalado con sugerencia de la primaria
    monkeypatch.setattr(recetas, "leer_binance", lambda http, symbol, dia: _lectura(100500.0, "binance"))
    e = resolver_receta(_m(R_CIERRE), http=object(), ahora=AHORA)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "discrepan" in e["razon"]


def test_resolver_receta_una_fuente_y_errores(monkeypatch):
    monkeypatch.setattr(recetas, "leer_cf", lambda http, indice, dia: _lectura(103210.5))
    monkeypatch.setattr(recetas, "leer_binance", lambda http, symbol, dia: (_ for _ in ()).throw(RecetaError("la vela aún no cierra")))
    e = resolver_receta(_m(R_CIERRE), http=object(), ahora=AHORA)
    assert e["escalar"] and e["veredicto_sugerido"] == "YES" and "una sola fuente" in e["razon"] and "aún no cierra" in e["razon"]
    # primaria falla → escalado sin sugerencia
    monkeypatch.setattr(recetas, "leer_cf", lambda http, indice, dia: (_ for _ in ()).throw(RecetaError("sin dato del 2026-12-31")))
    e = resolver_receta(_m(R_CIERRE), http=object(), ahora=AHORA)
    assert e["escalar"] and "veredicto_sugerido" not in e and "sin dato" in e["razon"]
    # todavía no es la fecha del dato
    e = resolver_receta(_m(R_CIERRE), http=object(), ahora=datetime(2026, 12, 30, tzinfo=timezone.utc))
    assert e["escalar"] and "todavía no" in e["razon"]
    # receta inválida
    e = resolver_receta(_m({"fuente": "nada"}), http=object(), ahora=AHORA)
    assert e["escalar"] and "receta inválida" in e["razon"]


def test_fed_y_dominancia(monkeypatch):
    fed = {"fuente": "fed_tasa", "params": {"decision": "2026-09-16", "tipo": "mantiene"}}
    monkeypatch.setattr(recetas, "leer_fred_movimiento", lambda http, d: Lectura(0.0, "https://fred.stlouisfed.org/series/DFEDTARU", "2026-09-16", "3.75 → 3.75", "fred"))
    monkeypatch.setattr(recetas, "leer_fed_comunicado", lambda http, d: Lectura(0.0, "https://www.federalreserve.gov/x", "2026-09-16", "maintain", "federalreserve"))
    e = resolver_receta(_m(fed, "fed-mantiene-tasa-sep26", "2026-09-16T17:55:00Z"), http=object(), ahora=AHORA)
    assert e["veredicto"] == "YES" and e["confianza"] == "alta"
    monkeypatch.setattr(recetas, "leer_fed_comunicado", lambda http, d: Lectura(-0.25, "https://www.federalreserve.gov/x", "2026-09-16", "lower", "federalreserve"))
    assert resolver_receta(_m(fed, "fed-mantiene-tasa-sep26", "2026-09-16T17:55:00Z"), http=object(), ahora=AHORA)["escalar"]
    dom = {"fuente": "cripto_dominancia", "params": {}, "fecha": "2026-12-31", "op": ">=", "valor": 60}
    monkeypatch.setattr(recetas, "leer_coingecko_global", lambda http, campo: Lectura(58.2, "https://www.coingecko.com/en/global-charts", "2027-01-02", "dominancia 58.2", "coingecko"))
    e = resolver_receta(_m(dom, "btc-dominancia-60-2026"), http=object(), ahora=AHORA)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "una sola fuente" in e["razon"]


def test_lectores_puros():
    # FRED: movimiento alrededor de la decisión
    class H:
        def get_text(self, url):
            return "observation_date,DFEDTARU\n2026-09-14,3.75\n2026-09-15,3.75\n2026-09-16,3.75\n2026-09-17,3.50\n2026-09-18,3.50\n"

        def get(self, url):
            return {"count": 57}
    l = recetas.leer_fred_movimiento(H(), date(2026, 9, 16))
    assert l.valor == -0.25 and "3.75 % → 3.50 %" in l.detalle
    assert recetas.leer_federal_register_eo(H(), "donald-trump", "2026-01-01", "2026-12-31").valor == 57

    class HFed:
        def get_text(self, url):
            return "<p>the Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent.</p>"
    l = recetas.leer_fed_comunicado(HFed(), date(2026, 7, 29))
    assert l.valor == 0.0 and "3-1/2 to 3-3/4 percent" in l.detalle


def test_fuentes_confiables_en_validar_entrada():
    assert es_fuente_confiable("https://www.reuters.com/x") and es_fuente_confiable("https://www.banxico.org.mx/x")
    assert es_fuente_confiable("https://www.gob.mx/presidencia") and es_fuente_confiable("https://clerk.house.gov/x")
    assert not es_fuente_confiable("https://blog-random.example.com/x")
    detalle = {"status": "pending_resolution", "market_type": "binary", "ends_at": "2026-09-16T17:55:00Z",
               "category": "Economía", "resolution_source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "outcomes": []}
    ahora = datetime(2026, 9, 17, tzinfo=timezone.utc)
    ok = {"veredicto": "YES", "resultado": "x", "confianza": "alta", "fuente_1": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm", "fuente_2": "https://www.reuters.com/markets/x"}
    assert validar_entrada(ok, detalle, ahora) == []
    mala = {**ok, "fuente_2": "https://cualquier-blog.com/x"}
    assert any("no es una fuente confiable" in e for e in validar_entrada(mala, detalle, ahora))
    sin_oficial = {**ok, "fuente_1": "https://www.reuters.com/a", "fuente_2": "https://apnews.com/b"}
    assert any("ninguna fuente es la oficial" in e for e in validar_entrada(sin_oficial, detalle, ahora))
    # deportes no cambia
    dep = {**detalle, "category": "Deportes", "resolution_source_url": "https://www.uefa.com/x"}
    assert validar_entrada({**ok, "fuente_1": "https://www.espn.com/a", "fuente_2": "https://www.skysports.com/b"}, dep, ahora) == []
