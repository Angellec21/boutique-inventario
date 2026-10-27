import pytest
from fastapi.testclient import TestClient

from tests.ayudas import cliente_admin


@pytest.fixture
def client() -> TestClient:
    c = cliente_admin()
    c.post("/sucursales", json={"codigo": "CEN", "nombre": "Centro"})
    c.post("/sucursales", json={"codigo": "VEN", "nombre": "Ventura Mall"})
    c.post(
        "/productos",
        json={
            "codigo": "JEA-010",
            "nombre": "Jean skinny tiro alto",
            "categoria": "Jeans",
            "precio_venta": "260",
            "costo": "140",
        },
    )
    return c


def test_salud(client):
    assert client.get("/salud").json() == {"estado": "ok"}


def test_crear_y_listar_productos(client):
    r = client.get("/productos", params={"q": "skinny"})
    assert r.status_code == 200
    assert r.json()[0]["precio_venta"] == "260.00"


def test_producto_duplicado_devuelve_409(client):
    r = client.post(
        "/productos",
        json={"codigo": "jea-010", "nombre": "Jean recto", "categoria": "Jeans", "precio_venta": 1, "costo": 0},
    )
    assert r.status_code == 409


def test_producto_inexistente_devuelve_404(client):
    assert client.get("/productos/99").status_code == 404


def test_matriz_de_variantes_y_detalle(client):
    r = client.post(
        "/productos/1/variantes/matriz",
        json={"tallas": ["28", "30", "32"], "colores": ["Índigo", "Negro"]},
    )
    assert r.status_code == 201
    assert len(r.json()) == 6
    detalle = client.get("/productos/1").json()
    assert detalle["margen"] == "120.00"
    assert {v["sku"] for v in detalle["variantes"]} >= {"JEA-010-IND-28", "JEA-010-NEG-32"}


def test_talla_invalida_devuelve_422(client):
    r = client.post("/productos/1/variantes", json={"talla": "gigante", "color": "Negro"})
    assert r.status_code == 422


def test_ingreso_por_sku_y_matriz_de_stock(client):
    client.post("/productos/1/variantes/matriz", json={"tallas": ["30", "32"], "colores": ["Negro"]})
    r = client.post(
        "/stock/ingresos",
        json={
            "sucursal_id": 1,
            "referencia": "Pedido 0045",
            "items": [{"sku": "jea-010-neg-30", "cantidad": 6}, {"variante_id": 2, "cantidad": 4}],
        },
    )
    assert r.status_code == 201
    assert [m["saldo"] for m in r.json()] == [6, 4]
    m = client.get("/productos/1/stock").json()
    assert m["celdas"]["Negro"] == {"30": 6, "32": 4}
    assert m["valor_venta"] == "2600.00"


def test_ingreso_sin_identificador_devuelve_422(client):
    r = client.post("/stock/ingresos", json={"sucursal_id": 1, "items": [{"cantidad": 2}]})
    assert r.status_code == 422


def test_ajuste_alertas_y_kardex(client):
    client.post("/productos/1/variantes", json={"talla": "30", "color": "Negro", "stock_minimo": 3})
    client.post("/stock/ingresos", json={"sucursal_id": 1, "items": [{"variante_id": 1, "cantidad": 5}]})
    client.post("/stock/ingresos", json={"sucursal_id": 2, "items": [{"variante_id": 1, "cantidad": 4}]})
    r = client.post(
        "/stock/ajustes",
        json={"variante_id": 1, "sucursal_id": 1, "cantidad_real": 2, "motivo": "Conteo físico"},
    )
    assert r.status_code == 201 and r.json()["cantidad"] == -3
    alertas = client.get("/sucursales/1/alertas").json()
    assert alertas[0]["sku"] == "JEA-010-NEG-30"
    assert alertas[0]["en_otras_sucursales"] == 4
    kardex = client.get("/variantes/1/kardex", params={"sucursal_id": 1}).json()
    assert [k["tipo"] for k in kardex] == ["ingreso", "ajuste"]


def test_sucursal_inexistente_en_alertas(client):
    assert client.get("/sucursales/9/alertas").status_code == 404
