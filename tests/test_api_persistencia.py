"""La API guarda en disco cada cambio y lo recupera al reiniciar."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.usuarios import RegistroUsuarios
from tests.ayudas import ADMIN, SECRETO, ingresar


def _servidor(ruta) -> TestClient:
    """Simula arrancar el servidor (o reiniciarlo) con el archivo de datos ``ruta``."""
    usuarios = RegistroUsuarios(secreto=SECRETO, iteraciones=1_000)
    return TestClient(create_app(usuarios=usuarios, datos=ruta))


@pytest.fixture
def ruta(tmp_path, monkeypatch):
    monkeypatch.setenv("BOUTIQUE_ADMIN_USUARIO", ADMIN[0])
    monkeypatch.setenv("BOUTIQUE_ADMIN_CLAVE", ADMIN[1])
    return tmp_path / "boutique.json"


def _cargar_tienda(c: TestClient) -> None:
    assert c.post("/sucursales", json={"codigo": "CEN", "nombre": "Centro"}).status_code == 201
    r = c.post("/productos", json={"codigo": "BLU-001", "nombre": "Blusa de lino",
                                   "categoria": "Blusas", "precio_venta": "189", "costo": "95"})
    assert r.status_code == 201, r.text
    r = c.post("/productos/1/variantes/matriz", json={"tallas": ["S", "M"], "colores": ["Beige"]})
    assert r.status_code == 201, r.text
    r = c.post("/stock/ingresos", json={"sucursal_id": 1, "referencia": "Pedido 0102",
                                        "items": [{"variante_id": 1, "cantidad": 4}]})
    assert r.status_code == 201, r.text
    r = c.post("/ventas", json={"sucursal_id": 1, "metodo_pago": "qr",
                                "items": [{"variante_id": 1, "cantidad": 1}]})
    assert r.status_code == 201, r.text


def test_primer_arranque_crea_el_archivo_con_el_admin(ruta):
    _servidor(ruta)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert [u["usuario"] for u in datos["usuarios"]["lista"]] == [ADMIN[0]]


def test_los_cambios_sobreviven_a_un_reinicio(ruta):
    c = ingresar(_servidor(ruta), *ADMIN)
    _cargar_tienda(c)

    c2 = ingresar(_servidor(ruta), *ADMIN)  # «reinicio»: nueva app, mismo archivo
    kardex = c2.get("/variantes/1/kardex").json()
    assert [(m["tipo"], m["saldo"]) for m in kardex] == [("ingreso", 4), ("venta", 3)]
    ventas = c2.get("/ventas").json()
    assert [v["codigo"] for v in ventas] == ["V-CEN-000001"]
    r = c2.post("/ventas", json={"sucursal_id": 1, "metodo_pago": "tarjeta",
                                 "items": [{"variante_id": 1, "cantidad": 1}]})
    assert r.json()["codigo"] == "V-CEN-000002"


def test_usuarios_creados_y_claves_cambiadas_persisten(ruta):
    c = ingresar(_servidor(ruta), *ADMIN)
    _cargar_tienda(c)
    r = c.post("/usuarios", json={"usuario": "carla.v", "nombre": "Carla Vaca",
                                  "clave": "Equipetrol1", "rol": "encargado", "sucursal_id": 1})
    assert r.status_code == 201, r.text
    assert c.post("/auth/clave", json={"actual": ADMIN[1], "nueva": "NuevaClave9"}).status_code == 204

    nuevo = _servidor(ruta)
    assert nuevo.post("/auth/token", json={"usuario": ADMIN[0], "clave": ADMIN[1]}).status_code == 401
    ingresar(nuevo, ADMIN[0], "NuevaClave9")
    assert ingresar(_servidor(ruta), "carla.v", "Equipetrol1").get("/auth/yo").json()["rol"] == "encargado"


def test_operaciones_rechazadas_no_tocan_el_archivo(ruta):
    c = ingresar(_servidor(ruta), *ADMIN)
    _cargar_tienda(c)
    antes = ruta.stat().st_mtime_ns, ruta.read_text(encoding="utf-8")
    r = c.post("/ventas", json={"sucursal_id": 1, "metodo_pago": "qr",
                                "items": [{"variante_id": 1, "cantidad": 99}]})
    assert r.status_code == 409
    assert c.post("/auth/token", json={"usuario": ADMIN[0], "clave": ADMIN[1]}).status_code == 200
    assert c.get("/ventas").status_code == 200
    assert (ruta.stat().st_mtime_ns, ruta.read_text(encoding="utf-8")) == antes


def test_sin_archivo_de_datos_todo_queda_en_memoria(tmp_path):
    usuarios = RegistroUsuarios(secreto=SECRETO, iteraciones=1_000)
    usuarios.crear(*ADMIN[:1], "Rosa Áñez", ADMIN[1], rol="admin")
    c = ingresar(TestClient(create_app(usuarios=usuarios)), *ADMIN)
    _cargar_tienda(c)
    assert c.app.state.almacen is None
    assert list(tmp_path.iterdir()) == []
