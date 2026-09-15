"""GET /api/contenido/categorias/{categoria}: contenido curado por categoría (landing de Política)."""
from app.models.market import MarketCategory
from app.schemas.contenido import ContenidoCategoria
from contenido_categorias import CATEGORIAS, check


async def test_politica_devuelve_contenido_valido(client):
    resp = await client.get("/api/contenido/categorias/Política")
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoria"] == "POLITICA_MX"
    assert body["proyeccion"]["umbral"] == 334
    assert sum(b["escanos"] for b in body["proyeccion"]["bloques"]) <= body["proyeccion"]["total"]
    assert sum(1 for h in body["cronologia"]["hitos"] if h["clave"]) == 1
    assert body["hero"]["secundario_id"]


async def test_categoria_sin_contenido_404(client):
    resp = await client.get("/api/contenido/categorias/Clima")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CONTENIDO_NO_ENCONTRADO"


async def test_categoria_invalida_422(client):
    resp = await client.get("/api/contenido/categorias/Nada")
    assert resp.status_code == 422


def test_todas_las_entradas_validan():
    """Forma (Pydantic) + coherencia editorial (check) + ids que existen en market_content."""
    from market_content import ALL  # solo en tests: el paquete de normas carga 10 módulos

    assert CATEGORIAS, "sin categorías curadas"
    assert check() == []
    for clave, data in CATEGORIAS.items():
        assert clave in MarketCategory.__members__, f"{clave} no es un NOMBRE de MarketCategory"
        c = ContenidoCategoria.model_validate(data)
        referidos = set(c.notas)
        if c.hero.secundario_id:
            referidos.add(c.hero.secundario_id)
        if c.proyeccion and c.proyeccion.mercado_umbral_id:
            referidos.add(c.proyeccion.mercado_umbral_id)
        faltan = referidos - set(ALL)
        assert not faltan, f"{clave}: ids sin normas en market_content: {sorted(faltan)}"
