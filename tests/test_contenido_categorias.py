"""GET /api/contenido/categorias/{categoria}: contenido curado por categoría (landings de Política y Deportes)."""
from pathlib import Path

from app.models.market import MarketCategory
from app.schemas.contenido import ContenidoCategoria
from contenido_categorias import CATEGORIAS, check

RAIZ = Path(__file__).resolve().parents[1]


async def test_politica_devuelve_contenido_valido(client):
    resp = await client.get("/api/contenido/categorias/Política")
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoria"] == "POLITICA_MX"
    assert body["proyeccion"]["umbral"] == 334
    assert all(b["mercado_id"] and len(b["escanos_por_opcion"]) >= 2 for b in body["proyeccion"]["bloques"])
    assert sum(1 for h in body["cronologia"]["hitos"] if h["clave"]) == 1
    assert body["cronologia"]["fuente_url"].startswith("https://")
    assert body["hero"]["secundario_id"]


async def test_categoria_sin_contenido_404(client):
    resp = await client.get("/api/contenido/categorias/Clima")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CONTENIDO_NO_ENCONTRADO"


async def test_categoria_invalida_422(client):
    resp = await client.get("/api/contenido/categorias/Nada")
    assert resp.status_code == 422


async def test_deportes_devuelve_titulos(client):
    resp = await client.get("/api/contenido/categorias/Deportes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoria"] == "DEPORTES"
    assert body["titulos"]["NFL"] == "nfl-campeon-super-bowl-lxi"
    assert body["proyeccion"] is None and body["cronologia"] is None
    assert any(f["host"] == "ligamx.net" for f in body["fuentes"])


def test_todas_las_entradas_validan():
    """Forma (Pydantic) + coherencia editorial (check) + ids que existen en market_content o en
    mercados-pendientes.yaml + ligas de `titulos` conocidas por el frontend."""
    from market_content import ALL  # solo en tests: el paquete de normas carga 10 módulos
    from seeds.plantillas import SUBCATEGORIAS_CONOCIDAS
    from seeds.schema import cargar

    specs, _ = cargar(RAIZ / "mercados-pendientes.yaml")
    conocidos = set(ALL) | {s.id for s in specs}
    assert CATEGORIAS, "sin categorías curadas"
    assert check() == []
    for clave, data in CATEGORIAS.items():
        assert clave in MarketCategory.__members__, f"{clave} no es un NOMBRE de MarketCategory"
        c = ContenidoCategoria.model_validate(data)
        referidos = set(c.notas) | set(c.titulos.values())
        if c.hero.secundario_id:
            referidos.add(c.hero.secundario_id)
        if c.proyeccion and c.proyeccion.mercado_umbral_id:
            referidos.add(c.proyeccion.mercado_umbral_id)
        faltan = referidos - conocidos
        assert not faltan, f"{clave}: ids sin normas en market_content ni documento en el YAML: {sorted(faltan)}"
        ligas_desconocidas = set(c.titulos) - SUBCATEGORIAS_CONOCIDAS
        assert not ligas_desconocidas, f"{clave}: titulos con ligas fuera de SUBCATEGORIAS_CONOCIDAS: {sorted(ligas_desconocidas)}"


def test_bloques_coinciden_con_el_yaml():
    """Las keys de `escanos_por_opcion` son exactamente las outcomes del mercado en mercados-pendientes.yaml.

    Si no coinciden, la landing no puede calcular ese partido y lo oculta. Un id que ya no está en
    el YAML (`prune` tras resolverse) se omite: para entonces la proyección habrá cambiado de mercados.
    """
    from seeds.schema import cargar  # solo en tests: el sembrador no es dependencia de la API

    specs, _ = cargar(RAIZ / "mercados-pendientes.yaml")
    por_id = {s.id: s for s in specs}
    for clave, data in CATEGORIAS.items():
        c = ContenidoCategoria.model_validate(data)
        if not c.proyeccion:
            continue
        for b in c.proyeccion.bloques:
            spec = por_id.get(b.mercado_id)
            if spec is None:
                continue
            assert spec.tipo == "multi", f"{clave}: {b.mercado_id} debe ser multi"
            assert spec.category == c.categoria, f"{clave}: {b.mercado_id} es de otra categoría"
            assert set(b.escanos_por_opcion) == {o.key for o in spec.outcomes}, (
                f"{clave}: {b.partido}: escanos_por_opcion no coincide con las outcomes de {b.mercado_id}"
            )
