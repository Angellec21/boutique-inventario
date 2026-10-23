import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    c = TestClient(create_app())
    c.post("/sucursales", json={"codigo": "CEN", "nombre": "Centro"})
    c.post("/sucursales", json={"codigo": "VEN", "nombre": "Ventura Mall"})
    c.post(
        "/productos",
        json={"codigo": "VES-020", "nombre": "Vestido midi floreado", "categoria": "Vestidos",
              "precio_venta": "320", "costo": "160"},
    )
    c.post("/productos/1/variantes/matriz", json={"tallas": ["S", "M"], "colores": ["Rojo"]})
    c.post("/stock/ingresos", json={"sucursal_id": 1, "items": [
        {"sku": "VES-020-ROJ-S", "cantidad": 3}, {"sku": "VES-020-ROJ-M", "cantidad": 5}]})
    return c


def enviar(client, items, origen=1, destino=2):
    return client.post("/transferencias", json={"origen_id": origen, "destino_id": destino, "items": items})


def test_enviar_por_sku_y_ver_en_transito(client):
    r = enviar(client, [{"sku": "ves-020-roj-m", "cantidad": 2}])
    assert r.status_code == 201
    body = r.json()
    assert (body["codigo"], body["origen"], body["destino"], body["estado"]) == (
        "TRF-00001", "CEN", "VEN", "en_transito")
    variantes = {v["sku"]: v for v in client.get("/productos/1").json()["variantes"]}
    assert variantes["VES-020-ROJ-M"]["en_transito"] == 2
    assert variantes["VES-020-ROJ-M"]["stock_total"] == 3


def test_enviar_sin_stock_devuelve_409(client):
    r = enviar(client, [{"variante_id": 1, "cantidad": 10}])
    assert r.status_code == 409
    assert "Stock insuficiente" in r.json()["detail"]


def test_item_sin_sku_ni_id_devuelve_422(client):
    assert enviar(client, [{"cantidad": 1}]).status_code == 422


def test_recepcion_completa_y_matriz_del_destino(client):
    enviar(client, [{"variante_id": 2, "cantidad": 2}])
    r = client.post("/transferencias/1/recepcion", json={})
    assert r.status_code == 200 and r.json()["estado"] == "recibida"
    matriz = client.get("/productos/1/stock", params={"sucursal_id": 2}).json()
    assert matriz["celdas"]["Rojo"]["M"] == 2
    assert client.post("/transferencias/1/recepcion", json={}).status_code == 409


def test_recepcion_con_diferencias(client):
    enviar(client, [{"variante_id": 1, "cantidad": 2}, {"variante_id": 2, "cantidad": 2}])
    sin_obs = client.post("/transferencias/1/recepcion", json={"items": [{"sku": "VES-020-ROJ-S", "cantidad": 1}]})
    assert sin_obs.status_code == 422
    r = client.post(
        "/transferencias/1/recepcion",
        json={"items": [{"sku": "VES-020-ROJ-S", "cantidad": 1}], "observacion": "Faltó 1 en la bolsa"},
    )
    assert r.json()["estado"] == "recibida_con_diferencias"
    assert r.json()["unidades_faltantes"] == 1


def test_anular_y_listar_por_estado(client):
    enviar(client, [{"variante_id": 1, "cantidad": 1}])
    enviar(client, [{"variante_id": 2, "cantidad": 1}])
    r = client.post("/transferencias/2/anulacion", json={"motivo": "No salió el envío"})
    assert r.json()["estado"] == "anulada"
    pendientes = client.get("/transferencias", params={"sucursal_id": 2, "estado": "en_transito"}).json()
    assert [t["codigo"] for t in pendientes] == ["TRF-00001"]
    assert client.get("/transferencias", params={"estado": "perdida"}).status_code == 422
    assert client.get("/transferencias", params={"sucursal_id": 9}).status_code == 404
    assert client.get("/transferencias/99").status_code == 404
    kardex = client.get("/variantes/2/kardex", params={"sucursal_id": 1}).json()
    assert [m["tipo"] for m in kardex] == ["ingreso", "transferencia_salida", "transferencia_entrada"]
