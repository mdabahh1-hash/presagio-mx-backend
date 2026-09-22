"""Sembrador declarativo (seeds/ + sembrar-mercados.py).

Cubre: carga/expansión del YAML, validación con todos los errores, siembra
idempotente (dry-run vs apply), la guarda "ya vencido" y la poda del archivo a
nivel texto.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select, text

from app.core import lmsr
from app.models.market import Market, MarketCategory
from app.models.outcome import Outcome
from app.models.price_history import PriceHistory
from market_content._common import fecha_mx
from seeds.plantillas import COMPETENCIAS
from seeds.prune import clasificar, partir_documentos, quitar_documentos
from seeds.runner import sembrar
from seeds.schema import CATEGORIAS, CATEGORIAS_PROHIBIDAS, SchemaError, cargar, cargar_texto

CONTEXTO = (
    "Contexto de prueba con hechos estables y suficiente longitud para pasar el mínimo "
    "de ciento veinte caracteres que exige el esquema del sembrador, igual que market_content."
)

YAML_OK = f"""# Cabecera de prueba: debe sobrevivir a la poda.
# Segunda línea de la cabecera.
---
tipo: binario
id: prueba-binario-ok
question: ¿Pasa la cosa binaria de prueba antes de 2030?
description: Descripción corta del binario de prueba.
category: ECONOMIA
subcategory: Banxico
resolution_criteria: Resuelve SÍ si la cosa pasa. Resuelve NO en cualquier otro caso.
rules_como: se revisa el comunicado oficial publicado en la fecha indicada y se compara con el umbral.
rules_cuerpo: |
  Cuenta únicamente el comunicado oficial; no cuentan filtraciones ni declaraciones previas.

  Si el comunicado se pospone, el mercado espera hasta el cierre indicado.
context: |
  {CONTEXTO}
ends_at: 2030-01-01T05:59:00Z
initial_yes_price: 35
---
tipo: multi
id: prueba-multi-nfl
question: ¿Quién gana el premio de prueba de la NFL?
description: Multi de prueba con tres opciones.
category: DEPORTES
subcategory: NFL
kind: accesorio
resolution_criteria: Se resuelve con el ganador anunciado oficialmente por la NFL.
resolution_source_url: https://www.nfl.com/honors/
rules: |
  El mercado se resuelve con el ganador anunciado oficialmente por la NFL en su gala anual de premios.
  Si la NFL no anuncia ganador antes del cierre, el mercado se cancela y se reembolsan las posiciones.
  Cada acción del ganador paga 1 PT y las demás valen 0. Si el ganador real no está entre las opciones nombradas, gana «Otro».
context: |
  {CONTEXTO}
ends_at: 2030-02-12T05:00:00Z
trending: true
outcomes:
  - {{key: garrett, label: "🐏 Myles Garrett", pct: 15}}
  - {{key: anderson, label: "🤠 Will Anderson Jr.", pct: 11}}
  - {{key: otro, label: "🏈 Otro jugador", pct: 74}}
---
tipo: partido
id: prueba-laliga-realmadrid-barcelona
competencia: LaLiga
local: Real Madrid
visitante: Barcelona
kickoff: 2030-10-25T20:00:00Z
# prior: SportRadar (comentario interno que debe sobrevivir a la poda)
pct: [45, 25, 30]
ventana: la Jornada 10 de LaLiga 2026-27 (23 al 26 de octubre de 2026)
trending: true
context: |
  {CONTEXTO}
---
tipo: binario
id: prueba-binario-vencido
question: ¿Pasó la cosa vencida?
description: Binario ya vencido; nunca debe sembrarse.
category: GLOBAL
resolution_criteria: Resuelve SÍ si pasó.
resolution_source_url: https://example.org/fuente
rules_cuerpo: |
  Cuenta únicamente la publicación oficial de la fuente indicada; nada más cuenta para este mercado de prueba.
context: |
  {CONTEXTO}
ends_at: 2020-01-01T00:00:00Z
initial_yes_price: 50
"""

IDS_VIVOS = ["prueba-binario-ok", "prueba-multi-nfl", "prueba-laliga-realmadrid-barcelona"]
ID_VENCIDO = "prueba-binario-vencido"


def _specs():
    specs, _avisos = cargar_texto(YAML_OK)
    return specs


# ── carga y expansión ────────────────────────────────────────────────────────

def test_cargar_expande_partido():
    specs, avisos = cargar_texto(YAML_OK)
    assert [s.id for s in specs] == IDS_VIVOS + [ID_VENCIDO]
    partido = next(s for s in specs if s.id == "prueba-laliga-realmadrid-barcelona")
    assert partido.tipo == "multi" and partido.origen == "partido"
    assert partido.category == "DEPORTES" and partido.subcategory == "LaLiga" and partido.kind == "partido"
    assert partido.question == "¿Quién gana Real Madrid vs Barcelona?"
    assert [o.key for o in partido.outcomes] == ["local", "empate", "visitante"]
    assert [o.label for o in partido.outcomes] == ["🏠 Real Madrid", "🤝 Empate", "✈️ Barcelona"]
    assert [o.pct for o in partido.outcomes] == [45.0, 25.0, 30.0]
    assert "Real Madrid" in partido.rules and "Barcelona" in partido.rules and len(partido.rules) >= 200
    assert partido.resolution_source_url == COMPETENCIAS["LaLiga"].url
    assert partido.ends_at == datetime(2030, 10, 25, 20, 0, tzinfo=timezone.utc)
    assert partido.b == 3000.0
    # Banxico no está en la lista conocida → aviso, no error.
    assert any("Banxico" in a for a in avisos)


def test_rules_cuerpo_se_expande():
    binario = next(s for s in _specs() if s.id == "prueba-binario-ok")
    assert binario.rules.startswith("Cómo se resuelve:")
    assert fecha_mx("2030-01-01T05:59:00Z", con_hora=False) in binario.rules
    assert "comunicado oficial" in binario.rules


def test_cargar_desde_archivo(tmp_path):
    archivo = tmp_path / "m.yaml"
    archivo.write_text(YAML_OK, encoding="utf-8")
    specs, _ = cargar(archivo)
    assert len(specs) == 4


def test_validar_reporta_todos_los_errores():
    malo = f"""---
tipo: binario
id: Mal_ID
question: q
description: d
category: MUNDIAL_2026
resolution_criteria: r
resolution_source_url: https://x.y
rules: corta
context: |
  {CONTEXTO}
ends_at: 2030-01-01 00:00:00
initial_yes_price: 35
---
tipo: multi
id: multi-mal
question: q
description: d
category: DEPORTES
resolution_criteria: r
resolution_source_url: https://x.y
rules: |
  {CONTEXTO} {CONTEXTO}
context: |
  {CONTEXTO}
ends_at: 2030-01-01T00:00:00Z
outcomes:
  - {{key: a, label: A, pct: 45}}
  - {{key: b, label: B, pct: 45}}
---
tipo: multi
id: multi-sin-rules
question: q
description: d
category: TECH
resolution_criteria: r
resolution_source_url: https://x.y
context: |
  {CONTEXTO}
ends_at: 2030-01-01T00:00:00Z
outcomes:
  - {{key: a, label: A, pct: 50}}
  - {{key: b, label: B, pct: 50}}
---
tipo: partido
id: partido-mal
competencia: Liga Inventada
local: A
visitante: B
kickoff: 2030-01-01T00:00:00Z
pct: [40, 30, 30]
ventana: v
context: c
"""
    with pytest.raises(SchemaError) as exc:
        cargar_texto(malo)
    errores = "\n".join(exc.value.errores)
    assert len(exc.value.errores) >= 5
    for fragmento in (
        "zona horaria",                    # doc 1: ends_at sin tz (se descarta al normalizar)
        "suman 90",                        # doc 2: validación semántica
        "DEPORTES requiere subcategory",   # doc 2
        "falta 'rules'",                   # doc 3: estructural
        "Liga Inventada",                  # doc 4: expansión del partido
    ):
        assert fragmento in errores, fragmento


def test_validar_errores_de_validacion_semantica():
    malo = f"""---
tipo: binario
id: Mal_ID
question: q
description: d
category: MUNDIAL_2026
resolution_criteria: r
rules: corta
context: |
  {CONTEXTO}
ends_at: 2030-01-01T00:00:00Z
initial_yes_price: 150
"""
    with pytest.raises(SchemaError) as exc:
        cargar_texto(malo)
    errores = "\n".join(exc.value.errores)
    for fragmento in ("id inválido", "MUNDIAL_2026", "rules < 200", "Cómo se resuelve:", "entre 1 y 99"):
        assert fragmento in errores, fragmento


def test_categorias_sincronizadas_con_enum():
    assert CATEGORIAS | CATEGORIAS_PROHIBIDAS == {c.name for c in MarketCategory}


# ── siembra ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_no_escribe(db):
    r = await sembrar(_specs(), db, apply=False, log=lambda *_: None)
    assert r.insertados == IDS_VIVOS
    assert r.vencidos == [ID_VENCIDO]
    assert (await db.execute(select(Market))).scalars().all() == []


@pytest.mark.asyncio
async def test_apply_inserta(db):
    lineas = []
    r = await sembrar(_specs(), db, apply=True, log=lineas.append)
    assert r.insertados == IDS_VIVOS and r.vencidos == [ID_VENCIDO]
    assert any("SKIP" in l and "ya vencido" in l for l in lineas)

    mercados = {m.id: m for m in (await db.execute(select(Market))).scalars().all()}
    assert set(mercados) == set(IDS_VIVOS)

    binario = mercados["prueba-binario-ok"]
    assert binario.market_type == "binary" and binario.yes_price == 35.0
    assert binario.category == MarketCategory.ECONOMIA and binario.subcategory == "Banxico"
    assert binario.rules.startswith("Cómo se resuelve:") and binario.b == 3000.0

    nfl = mercados["prueba-multi-nfl"]
    assert nfl.market_type == "multi" and nfl.kind == "accesorio" and nfl.trending is True
    partido = mercados["prueba-laliga-realmadrid-barcelona"]
    assert partido.kind == "partido" and partido.subcategory == "LaLiga"

    for mid in ("prueba-multi-nfl", "prueba-laliga-realmadrid-barcelona"):
        outcomes = (await db.execute(select(Outcome).where(Outcome.market_id == mid))).scalars().all()
        assert len(outcomes) == 3
        precios = lmsr.prices_multi({o.outcome_key: o.q for o in outcomes}, mercados[mid].b)
        for o in outcomes:
            assert abs(precios[o.outcome_key] - o.price) < 0.01

    historia = (await db.execute(select(PriceHistory))).scalars().all()
    por_mercado = {h.market_id: h for h in historia}
    assert set(por_mercado) == set(IDS_VIVOS) and len(historia) == 3
    assert por_mercado["prueba-binario-ok"].yes_price == 35.0
    assert por_mercado["prueba-multi-nfl"].yes_price == 0.0


@pytest.mark.asyncio
async def test_segunda_corrida_skip(db):
    await sembrar(_specs(), db, apply=True, log=lambda *_: None)
    r = await sembrar(_specs(), db, apply=True, log=lambda *_: None)
    assert r.insertados == [] and r.existentes == IDS_VIVOS and r.vencidos == [ID_VENCIDO]
    total = (await db.execute(text("SELECT COUNT(*) FROM markets"))).scalar_one()
    assert total == 3


# ── prune ────────────────────────────────────────────────────────────────────

def test_partir_documentos_round_trip():
    trozos = partir_documentos(YAML_OK)
    assert "".join(trozos) == YAML_OK
    assert trozos[0].startswith("# Cabecera de prueba")
    assert len(trozos) == 5  # cabecera + 4 documentos


@pytest.mark.asyncio
async def test_prune_clasifica_y_quita(db):
    specs = _specs()
    await sembrar(specs, db, apply=True, log=lambda *_: None)
    await db.execute(text("UPDATE markets SET status = 'RESOLVED_YES' WHERE id = 'prueba-binario-ok'"))
    await db.execute(delete(Outcome).where(Outcome.market_id == "prueba-multi-nfl"))
    await db.execute(delete(PriceHistory).where(PriceHistory.market_id == "prueba-multi-nfl"))
    await db.execute(delete(Market).where(Market.id == "prueba-multi-nfl"))
    await db.commit()

    veredictos = {v.id: v for v in await clasificar(specs, db, datetime.now(timezone.utc))}
    assert veredictos["prueba-binario-ok"].terminado and veredictos["prueba-binario-ok"].motivo == "RESOLVED_YES"
    assert not veredictos["prueba-multi-nfl"].terminado and veredictos["prueba-multi-nfl"].motivo == "pendiente de sembrar"
    assert veredictos[ID_VENCIDO].terminado and "cleanup" in veredictos[ID_VENCIDO].motivo
    assert veredictos["prueba-laliga-realmadrid-barcelona"].motivo == "activo (OPEN)"

    quitar = {v.id for v in veredictos.values() if v.terminado}
    nuevo = quitar_documentos(YAML_OK, quitar)
    trozos_antes = partir_documentos(YAML_OK)
    assert nuevo.startswith(trozos_antes[0])                    # cabecera intacta
    assert "# prior: SportRadar" in nuevo                         # comentario interno intacto
    assert trozos_antes[2] in nuevo and trozos_antes[3] in nuevo  # NFL y partido byte a byte
    assert "prueba-binario-ok" not in nuevo and ID_VENCIDO not in nuevo
    sobrevivientes, _ = cargar_texto(nuevo)
    assert [s.id for s in sobrevivientes] == ["prueba-multi-nfl", "prueba-laliga-realmadrid-barcelona"]


# ── accesorios de jugador: sujeto obligatorio (caso Josh Allen) ──────────────

RULES_PROP = ("El mercado se resuelve con el box score oficial del partido de la Semana 1 entre los Bills y los Texans. "
              "Cuentan solo los pases de touchdown lanzados por el jugador nombrado; no cuentan los de otro jugador "
              "con nombre parecido. Si no participa en el partido, el mercado se cancela.")
SUJETO_ALLEN = {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "posicion": "QB", "alcance": "partido",
                "ids": {"espn": 3918298, "cbs": "2181054"}}


def _prop_yaml(**cambios) -> str:
    """Documento YAML de una prop NFL; `cambios` pisa claves (None las quita)."""
    import yaml

    doc = {"tipo": "binario", "id": "nfl-allen-2tdpass-prueba",
           "question": "¿Josh Allen lanzará 2+ pases de TD en la Semana 1?",
           "description": "Prop de prueba.", "category": "DEPORTES", "subcategory": "NFL", "kind": "accesorio",
           "resolution_criteria": "Resuelve SÍ con 2 o más pases de TD del jugador.",
           "resolution_source_url": "https://www.espn.com/nfl/", "rules": RULES_PROP, "context": CONTEXTO,
           "ends_at": "2030-09-13T17:00:00Z", "initial_yes_price": 50, "sujeto": SUJETO_ALLEN}
    for k, v in cambios.items():
        if v is None:
            doc.pop(k, None)
        else:
            doc[k] = v
    return "---\n" + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def _errores(texto: str) -> str:
    with pytest.raises(SchemaError) as exc:
        cargar_texto(texto)
    return "\n".join(exc.value.errores)


def test_prop_con_sujeto_valido_carga_normalizado():
    specs, _ = cargar_texto(_prop_yaml())
    assert specs[0].sujeto == {**SUJETO_ALLEN, "ids": {"espn": "3918298", "cbs": "2181054"}}  # ids de YAML sin comillas → str


@pytest.mark.parametrize("cambios,fragmento", [
    ({"sujeto": None}, "accesorio de jugador sin 'sujeto'"),
    ({"sujeto": {**SUJETO_ALLEN, "ids": {"espn": "3918298"}}}, "sujeto: falta ids.cbs"),
    ({"sujeto": {**SUJETO_ALLEN, "jugador": "Josh Hines-Allen"}}, "debe ser idéntico"),
    ({"sujeto": {**SUJETO_ALLEN, "posicion": "DE"}}, "pases de TD exige posicion QB"),
    ({"sujeto": {k: v for k, v in SUJETO_ALLEN.items() if k != "alcance"}}, "faltan claves en sujeto: alcance"),
    ({"kind": None}, "requiere kind: accesorio"),
], ids=["sin-sujeto", "sin-ids-cbs", "homonimo", "pases-de-un-DE", "sin-alcance", "sin-kind"])
def test_prop_sin_identidad_valida_no_carga(cambios, fragmento):
    assert fragmento in _errores(_prop_yaml(**cambios))


def test_sujeto_fuera_de_un_accesorio_de_jugador_es_error():
    texto = _prop_yaml(category="GLOBAL", subcategory=None, kind=None, question="¿Pasará la cosa global antes de 2030?")
    assert "'sujeto' solo va en binarios de accesorio de jugador" in _errores(texto)


def test_accesorio_de_evento_en_singular_no_exige_sujeto():
    texto = _prop_yaml(id="ligamx-gol-antes-10-prueba", subcategory="Liga MX", sujeto=None,
                       question="¿Se anotará un gol antes del minuto 10 en América vs Chivas?")
    specs, _ = cargar_texto(texto)
    assert specs[0].sujeto is None and specs[0].kind == "accesorio"


def test_titular_de_champions_exige_ids_uefa():
    sujeto = {"jugador": "Rayan Cherki", "equipo": "Manchester City", "rival": "FC Porto", "posicion": "M",
              "alcance": "partido", "ids": {"espn": "5001"}}
    texto = _prop_yaml(id="ucl-cherki-titular-prueba", subcategory="Champions League", sujeto=sujeto,
                       question="¿Rayan Cherki será titular ante Porto?")
    assert "sujeto: falta ids.uefa" in _errores(texto)
    cargar_texto(texto.replace("espn: '5001'", "espn: '5001'\n    uefa: '250500'"))


@pytest.mark.asyncio
async def test_runner_guarda_el_sujeto(db):
    specs, _ = cargar_texto(_prop_yaml())
    r = await sembrar(specs, db, apply=True, log=lambda *_: None)
    assert r.insertados == ["nfl-allen-2tdpass-prueba"]
    m = (await db.execute(select(Market).where(Market.id == "nfl-allen-2tdpass-prueba"))).scalar_one()
    assert m.sujeto == specs[0].sujeto and m.kind == "accesorio"


def test_reemplazar_bloque_sujeto_conserva_el_resto():
    from seeds.sujetos import reemplazar_bloque_sujeto

    nuevo = {**SUJETO_ALLEN, "ids": {"espn": "3918298", "cbs": "2181054"}}
    sin = _prop_yaml(sujeto=None).replace("---\n", "---\n# comentario interno\n", 1)
    con = reemplazar_bloque_sujeto(sin, nuevo)  # sin bloque: se agrega al final
    assert "# comentario interno" in con and cargar_texto(con)[0][0].sujeto == nuevo
    viejo = sin + "sujeto:\n  jugador: Josh Allen\n  equipo: Bills\n  rival: Texans\n  alcance: partido\n# después\n"
    otra = reemplazar_bloque_sujeto(viejo, nuevo)  # con bloque: se reemplaza en su lugar
    assert otra.endswith("# después\n") and otra.count("sujeto:") == 1 and "cbs: '2181054'" in otra
    assert cargar_texto(otra)[0][0].sujeto == nuevo


def test_identificar_llena_ids_y_solo_escribe_sin_errores(tmp_path, monkeypatch, capsys):
    """`sembrar-mercados.py identificar` sin red: buscar_ids simulado."""
    import argparse
    import importlib.util
    import os

    from app.services.resolucion import identidad

    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "sembrar-mercados.py")
    spec = importlib.util.spec_from_file_location("sembrar_mercados", ruta)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    archivo = tmp_path / "m.yaml"
    escrito = _prop_yaml(sujeto={"equipo": "Bills", "rival": "Texans", "alcance": "partido"})
    archivo.write_text(YAML_OK + escrito, encoding="utf-8")
    pedidos = []

    def fake_buscar_ids(http, liga, base, fecha=None):
        pedidos.append((liga, dict(base), fecha))
        return {**base, "posicion": "QB", "ids": {"espn": "3918298", "cbs": "2181054"}}, [], []

    monkeypatch.setattr(identidad, "buscar_ids", fake_buscar_ids)
    args = argparse.Namespace(archivo=str(archivo), only=None, apply=False)
    cli.cmd_identificar(args)  # dry-run: no escribe
    assert archivo.read_text(encoding="utf-8") == YAML_OK + escrito
    # jugador sale de la pregunta; solo se consulta el accesorio de jugador
    assert pedidos == [("NFL", {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "alcance": "partido"},
                        datetime(2030, 9, 13, 17, 0, tzinfo=timezone.utc))]

    cli.cmd_identificar(argparse.Namespace(archivo=str(archivo), only=None, apply=True))
    texto = archivo.read_text(encoding="utf-8")
    assert texto.startswith(YAML_OK)  # los demás documentos, byte a byte
    specs, _ = cargar_texto(texto)
    assert next(s for s in specs if s.id == "nfl-allen-2tdpass-prueba").sujeto == \
        {**SUJETO_ALLEN, "ids": {"espn": "3918298", "cbs": "2181054"}}

    # cualquier error: código 1 y el archivo no cambia
    archivo.write_text(YAML_OK + escrito, encoding="utf-8")
    monkeypatch.setattr(identidad, "buscar_ids", lambda *a, **k: ({}, ["CBS (BUF): 2 jugadores con el nombre exacto"], []))
    with pytest.raises(SystemExit) as ex:
        cli.cmd_identificar(argparse.Namespace(archivo=str(archivo), only=None, apply=True))
    assert ex.value.code == 1 and archivo.read_text(encoding="utf-8") == YAML_OK + escrito
    assert "no se escribió nada" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_limite_de_pregunta_solo_para_mercados_nuevos(db):
    """70 caracteres (veredikt.md §7): el YAML conserva los ya sembrados hasta el
    prune, así que `validar` solo avisa y el runner rechaza al INSERTAR."""
    larga = "¿Pasa la cosa binaria de prueba con una pregunta que se pasa de setenta caracteres?"
    assert len(larga) > 70
    specs, avisos = cargar_texto(YAML_OK.replace("¿Pasa la cosa binaria de prueba antes de 2030?", larga))
    assert any("question > 70" in a for a in avisos)

    with pytest.raises(SchemaError, match="prueba-binario-ok: question > 70"):
        await sembrar(specs, db, apply=True, log=lambda *_: None)
    assert (await db.execute(select(Market.id))).scalars().all() == []  # nada escrito, ni los cortos

    corta, _ = cargar_texto(YAML_OK)
    await sembrar([s for s in corta if s.id == "prueba-binario-ok"], db, apply=True, log=lambda *_: None)
    r = await sembrar([s for s in specs if s.id == "prueba-binario-ok"], db, apply=False, log=lambda *_: None)
    assert r.existentes == ["prueba-binario-ok"]  # ya sembrado: SKIP, sin error
