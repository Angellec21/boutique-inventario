"""Estado del sistema y descarga del respaldo completo."""

import json

from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app
from app.inventario import Inventario
from app.persistencia import importar
from app.usuarios import RegistroUsuarios
from tests.ayudas import ADMIN, SECRETO, cliente_admin, como, ingresar


def _tienda() -> TestClient:
    c = cliente_admin()
    c.post("/sucursales", json={"codigo": "CEN", "nombre": "Centro"})
    c.post("/productos", json={"codigo": "BLU-001", "nombre": "Blusa de lino",
                               "categoria": "Blusas", "precio_venta": "189", "costo": "95"})
    c.post("/productos/1/variantes/matriz", json={"tallas": ["M"], "colores": ["Negro"]})
    c.post("/stock/ingresos", json={"sucursal_id": 1, "items": [
        {"sku": "BLU-001-NEG-M", "cantidad": 5}]})
    c.post("/ventas", json={"sucursal_id": 1, "metodo_pago": "qr",
                            "items": [{"sku": "BLU-001-NEG-M", "cantidad": 2}]})
    c.post("/usuarios", json={"usuario": "carla.v", "nombre": "Carla Vaca",
                              "clave": "Centro2026", "sucursal_id": 1})
    return c


def test_salud_informa_version_y_modo_de_guardado(tmp_path, monkeypatch):
    en_memoria = TestClient(create_app())
    assert en_memoria.get("/salud").json() == {
        "estado": "ok", "version": __version__, "guardado": "memoria"}

    monkeypatch.setenv("BOUTIQUE_ADMIN_CLAVE", "ClaveDePrueba2026")
    con_archivo = TestClient(create_app(datos=tmp_path / "b.json"))
    assert con_archivo.get("/salud").json()["guardado"] == "archivo"


def test_version_de_la_api_coincide_con_el_paquete():
    c = TestClient(create_app())
    assert c.get("/openapi.json").json()["info"]["version"] == __version__


def test_admin_descarga_respaldo_como_archivo():
    r = _tienda().get("/respaldo")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    disposicion = r.headers["content-disposition"]
    assert disposicion.startswith('attachment; filename="boutique-respaldo-')
    assert disposicion.endswith('.json"')
    assert r.headers["cache-control"] == "no-store"

    datos = json.loads(r.content.decode("utf-8"))
    assert [p["codigo"] for p in datos["productos"]] == ["BLU-001"]
    assert len(datos["ventas"]) == 1
    assert {u["usuario"] for u in datos["usuarios"]["lista"]} == {"rosa", "carla.v"}


def test_respaldo_no_contiene_claves_en_texto_plano_ni_el_secreto():
    texto = _tienda().get("/respaldo").content.decode("utf-8")
    assert ADMIN[1] not in texto and "Centro2026" not in texto
    assert SECRETO not in texto


def test_respaldo_se_restaura_con_el_mismo_formato(tmp_path):
    respaldo = json.loads(_tienda().get("/respaldo").content)

    inv = Inventario()
    usuarios = RegistroUsuarios(secreto=SECRETO, iteraciones=1_000)
    importar(respaldo, inv, usuarios)
    assert inv.stock(1, 1) == 3
    assert len(inv.ventas) == 1

    archivo = tmp_path / "boutique.json"
    archivo.write_text(json.dumps(respaldo), encoding="utf-8")
    restaurado = TestClient(create_app(
        usuarios=RegistroUsuarios(secreto=SECRETO, iteraciones=1_000), datos=archivo))
    ingresar(restaurado, *ADMIN)
    assert restaurado.get("/ventas").json()[0]["sucursal_id"] == 1


def test_encargado_no_puede_descargar_respaldo():
    carla = como(_tienda(), "carla.v", "Centro2026")
    assert carla.get("/respaldo").status_code == 403


def test_respaldo_pide_sesion():
    assert TestClient(create_app()).get("/respaldo").status_code == 401
