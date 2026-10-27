from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.ayudas import cliente_admin

HOY = date.today().isoformat()


@pytest.fixture
def client() -> TestClient:
    c = cliente_admin()
    c.post("/sucursales", json={"codigo": "CEN", "nombre": "Centro"})
    c.post(
        "/productos",
        json={"codigo": "BLU-001", "nombre": "Blusa de lino", "categoria": "Blusas",
              "precio_venta": "189", "costo": "95"},
    )
    c.post("/productos/1/variantes/matriz", json={"tallas": ["S", "M"], "colores": ["Beige"]})
    c.post("/stock/ingresos", json={"sucursal_id": 1, "items": [
        {"sku": "BLU-001-BEI-S", "cantidad": 2}, {"sku": "BLU-001-BEI-M", "cantidad": 4}]})
    return c


def vender(client, items, **extra):
    datos = {"sucursal_id": 1, "metodo_pago": "efectivo", "monto_recibido": "500", **extra}
    return client.post("/ventas", json={**datos, "items": items})


def test_venta_por_sku_con_descuento_y_cambio(client):
    r = vender(client, [{"sku": "blu-001-bei-m", "cantidad": 2, "descuento_pct": "10"}], vendedor="Carla")
    assert r.status_code == 201
    v = r.json()
    assert (v["codigo"], v["sucursal"], v["estado"]) == ("V-CEN-000001", "CEN", "completada")
    assert (v["total"], v["descuento_total"], v["cambio"]) == ("340.20", "37.80", "159.80")
    assert v["items"][0]["subtotal"] == "340.20"
    assert "costo_unitario" not in v["items"][0]
    matriz = client.get("/productos/1/stock?sucursal_id=1").json()
    assert matriz["celdas"]["Beige"]["M"] == 2


def test_venta_sin_stock_409_y_monto_insuficiente_422(client):
    assert vender(client, [{"variante_id": 1, "cantidad": 3}]).status_code == 409
    r = vender(client, [{"variante_id": 1, "cantidad": 1}], monto_recibido="50")
    assert r.status_code == 422 and "insuficiente" in r.json()["detail"]
    assert vender(client, [{"variante_id": 1, "cantidad": 1, "descuento_pct": "80"}]).status_code == 422


def test_anular_venta_y_listar(client):
    vid = vender(client, [{"variante_id": 1, "cantidad": 2}]).json()["id"]
    r = client.post(f"/ventas/{vid}/anulacion", json={"motivo": "Cliente se arrepintió"})
    assert r.status_code == 200 and r.json()["estado"] == "anulada"
    assert client.post(f"/ventas/{vid}/anulacion", json={"motivo": "otra vez"}).status_code == 409
    assert client.get("/productos/1/stock?sucursal_id=1").json()["celdas"]["Beige"]["S"] == 2
    assert len(client.get(f"/ventas?desde={HOY}&hasta={HOY}").json()) == 1
    assert client.get("/ventas?desde=2000-01-01&hasta=2000-01-31").json() == []
    assert client.get("/ventas/99").status_code == 404


def test_reportes_del_dueno(client):
    vender(client, [{"sku": "BLU-001-BEI-M", "cantidad": 3}], monto_recibido="600")
    vender(client, [{"sku": "BLU-001-BEI-S", "cantidad": 1}], metodo_pago="qr", monto_recibido=None)
    top = client.get("/reportes/mas-vendidos?por=variante").json()
    assert [(f["codigo"], f["unidades"]) for f in top] == [("BLU-001-BEI-M", 3), ("BLU-001-BEI-S", 1)]
    tallas = client.get("/reportes/ventas-por-talla").json()
    assert [t["talla"] for t in tallas] == ["S", "M"]
    caja = client.get(f"/reportes/resumen-ventas?desde={HOY}&hasta={HOY}&sucursal_id=1").json()
    assert caja["total"] == "756.00"
    assert caja["por_metodo_pago"] == {"efectivo": "567.00", "qr": "189.00"}
    valor = client.get("/reportes/valor-inventario").json()
    assert valor[0]["unidades"] == 2 and valor[0]["valor_venta"] == "378.00"


def test_reportes_validan_parametros(client):
    assert client.get("/reportes/mas-vendidos?por=color").status_code == 422
    assert client.get("/reportes/resumen-ventas?desde=2026-10-10&hasta=2026-10-01").status_code == 422
    assert client.get("/reportes/resumen-ventas?sucursal_id=9").status_code == 404
