"""Inicio de sesión y permisos por rol en la API."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.usuarios import RegistroUsuarios
from tests.ayudas import cliente_admin, como

PUBLICAS = {"/salud", "/auth/token", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


@pytest.fixture
def admin() -> TestClient:
    c = cliente_admin()
    c.post("/sucursales", json={"codigo": "CEN", "nombre": "Centro"})
    c.post("/sucursales", json={"codigo": "EQP", "nombre": "Equipetrol"})
    c.post("/productos", json={"codigo": "VES-020", "nombre": "Vestido midi floreado",
                               "categoria": "Vestidos", "precio_venta": "320", "costo": "160"})
    c.post("/productos/1/variantes/matriz", json={"tallas": ["S", "M"], "colores": ["Rojo"]})
    for suc in (1, 2):
        c.post("/stock/ingresos", json={"sucursal_id": suc, "items": [
            {"sku": "VES-020-ROJ-S", "cantidad": 4}, {"sku": "VES-020-ROJ-M", "cantidad": 4}]})
    r = c.post("/usuarios", json={"usuario": "carla.v", "nombre": "Carla Vaca",
                                  "clave": "Equipetrol1", "sucursal_id": 2})
    assert r.status_code == 201
    return c


@pytest.fixture
def carla(admin) -> TestClient:
    """Encargada de la sucursal Equipetrol (id 2)."""
    return como(admin, "carla.v", "Equipetrol1")


def vender(c, sucursal_id, **extra):
    return c.post("/ventas", json={"sucursal_id": sucursal_id, "metodo_pago": "qr",
                                   "items": [{"sku": "VES-020-ROJ-M", "cantidad": 1}], **extra})


# --------------------------------------------------------------------- sesión
def test_login_devuelve_token_y_datos_sin_hash(admin):
    r = TestClient(admin.app).post("/auth/token", json={"usuario": "carla.v", "clave": "Equipetrol1"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["token_type"] == "bearer" and datos["expira_en_minutos"] == 480
    assert datos["usuario"]["rol"] == "encargado" and "clave_hash" not in datos["usuario"]


def test_login_incorrecto_da_401(admin):
    r = TestClient(admin.app).post("/auth/token", json={"usuario": "carla.v", "clave": "mala1234"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_todas_las_rutas_privadas_exigen_sesion(admin):
    anonimo = TestClient(admin.app)
    revisadas = 0
    for ruta in admin.app.routes:
        if ruta.path in PUBLICAS:
            continue
        url = ruta.path.replace("{sku}", "X").replace("_id}", "}")
        url = url.replace("{producto}", "1").replace("{variante}", "1").replace(
            "{sucursal}", "1").replace("{transferencia}", "1").replace("{venta}", "1").replace(
            "{usuario}", "1")
        for metodo in ruta.methods:
            r = anonimo.request(metodo, url, json={})
            assert r.status_code == 401, f"{metodo} {ruta.path} -> {r.status_code}"
            revisadas += 1
    assert revisadas >= 30


def test_token_falso_da_401(admin):
    anonimo = TestClient(admin.app, headers={"Authorization": "Bearer abc.def.ghi"})
    assert anonimo.get("/sucursales").status_code == 401


def test_yo_y_cambio_de_clave(carla, admin):
    assert carla.get("/auth/yo").json()["sucursal_id"] == 2
    r = carla.post("/auth/clave", json={"actual": "Equipetrol1", "nueva": "OtraClave22"})
    assert r.status_code == 204
    como(admin, "carla.v", "OtraClave22")


def test_admin_inicial_desde_variables_de_entorno(monkeypatch):
    monkeypatch.setenv("BOUTIQUE_SECRET", "x" * 40)
    monkeypatch.setenv("BOUTIQUE_ADMIN_USUARIO", "duena.rosa")
    monkeypatch.setenv("BOUTIQUE_ADMIN_CLAVE", "ClaveInicial1")
    c = TestClient(create_app())
    r = c.post("/auth/token", json={"usuario": "duena.rosa", "clave": "ClaveInicial1"})
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"


def test_admin_inicial_con_clave_aleatoria(monkeypatch, caplog):
    monkeypatch.delenv("BOUTIQUE_ADMIN_CLAVE", raising=False)
    monkeypatch.delenv("BOUTIQUE_ADMIN_USUARIO", raising=False)
    app = create_app()
    usuarios: RegistroUsuarios = app.state.usuarios
    assert [u.usuario for u in usuarios.usuarios.values()] == ["admin"]
    assert "Administrador inicial creado" in caplog.text


# ----------------------------------------------------------- gestión usuarios
def test_admin_gestiona_usuarios(admin):
    lista = admin.get("/usuarios").json()
    assert [u["usuario"] for u in lista] == ["rosa", "carla.v"]
    assert all("clave_hash" not in u for u in lista)
    r = admin.post("/usuarios", json={"usuario": "luis", "nombre": "Luis", "clave": "Clave2026",
                                      "sucursal_id": 9})
    assert r.status_code == 404
    assert admin.post("/usuarios/2/clave", json={"nueva": "Temporal123"}).status_code == 204
    assert admin.post("/usuarios/2/baja").json()["activo"] is False


def test_usuario_dado_de_baja_pierde_acceso_inmediato(admin, carla):
    admin.post("/usuarios/2/baja")
    assert carla.get("/sucursales").status_code == 401


def test_encargado_no_gestiona_usuarios_ni_catalogo(carla):
    assert carla.get("/usuarios").status_code == 403
    assert carla.post("/usuarios", json={"usuario": "otro", "nombre": "Otro",
                                         "clave": "Clave2026", "rol": "admin"}).status_code == 403
    assert carla.post("/sucursales", json={"codigo": "VEN", "nombre": "Ventura"}).status_code == 403
    assert carla.post("/productos", json={"codigo": "X-1", "nombre": "Polera", "categoria": "Poleras",
                                          "precio_venta": "90", "costo": "40"}).status_code == 403
    assert carla.post("/productos/1/variantes", json={"talla": "L", "color": "Rojo"}).status_code == 403


# ------------------------------------------------------------ costos y reportes
def test_encargado_no_ve_costos_ni_margen(carla, admin):
    assert "costo" in admin.get("/productos").json()[0]
    prod = carla.get("/productos").json()[0]
    assert "costo" not in prod and prod["precio_venta"] == "320.00"
    detalle = carla.get("/productos/1").json()
    assert "costo" not in detalle and "margen" not in detalle
    assert detalle["variantes"][0]["stock_total"] == 8


@pytest.mark.parametrize("ruta", ["mas-vendidos", "ventas-por-talla", "resumen-ventas",
                                  "valor-inventario"])
def test_reportes_solo_admin(carla, admin, ruta):
    assert carla.get(f"/reportes/{ruta}").status_code == 403
    assert admin.get(f"/reportes/{ruta}").status_code == 200


# ---------------------------------------------------------- límites de sucursal
def test_encargado_vende_solo_en_su_sucursal_y_queda_como_vendedor(carla):
    assert vender(carla, 1).status_code == 403
    r = vender(carla, 2)
    assert r.status_code == 201 and r.json()["vendedor"] == "Carla Vaca"
    assert vender(carla, 2, vendedor="Majo").json()["vendedor"] == "Majo"


def test_encargado_solo_ve_ventas_de_su_sucursal(carla, admin):
    vender(admin, 1)
    vender(carla, 2)
    assert [v["sucursal"] for v in carla.get("/ventas").json()] == ["EQP"]
    assert carla.get("/ventas?sucursal_id=1").status_code == 403
    assert carla.get("/ventas/1").status_code == 403
    assert len(admin.get("/ventas").json()) == 2


def test_solo_admin_anula_ventas(carla, admin):
    vender(carla, 2)
    motivo = {"motivo": "Error de caja"}
    assert carla.post("/ventas/1/anulacion", json=motivo).status_code == 403
    assert admin.post("/ventas/1/anulacion", json=motivo).json()["estado"] == "anulada"


def test_stock_ingresos_ajustes_y_alertas_por_sucursal(carla):
    ingreso = {"items": [{"sku": "VES-020-ROJ-S", "cantidad": 2}]}
    assert carla.post("/stock/ingresos", json={"sucursal_id": 1, **ingreso}).status_code == 403
    assert carla.post("/stock/ingresos", json={"sucursal_id": 2, **ingreso}).status_code == 201
    ajuste = {"variante_id": 1, "cantidad_real": 5, "motivo": "Conteo físico"}
    assert carla.post("/stock/ajustes", json={"sucursal_id": 1, **ajuste}).status_code == 403
    assert carla.post("/stock/ajustes", json={"sucursal_id": 2, **ajuste}).status_code == 201
    assert carla.get("/sucursales/1/alertas").status_code == 403
    assert carla.get("/sucursales/2/alertas").status_code == 200
    # La matriz de todas las sucursales sí la ve, para saber a quién pedir una transferencia.
    assert carla.get("/productos/1/stock").json()["total_unidades"] == 17


def test_kardex_del_encargado_se_limita_a_su_sucursal(carla, admin):
    assert len(admin.get("/variantes/1/kardex").json()) == 2
    movs = carla.get("/variantes/1/kardex").json()
    assert [m["sucursal_id"] for m in movs] == [2]
    assert carla.get("/variantes/1/kardex?sucursal_id=1").status_code == 403


def test_transferencias_segun_origen_y_destino(carla, admin):
    item = [{"sku": "VES-020-ROJ-M", "cantidad": 1}]
    # Carla no puede despachar desde el Centro, pero sí desde su tienda.
    assert carla.post("/transferencias", json={"origen_id": 1, "destino_id": 2,
                                               "items": item}).status_code == 403
    assert carla.post("/transferencias", json={"origen_id": 2, "destino_id": 1,
                                               "items": item}).status_code == 201
    # Envío del Centro a Equipetrol: lo recibe Carla; el envío de ella lo recibe el Centro.
    admin.post("/transferencias", json={"origen_id": 1, "destino_id": 2, "items": item})
    assert carla.post("/transferencias/1/recepcion", json={}).status_code == 403
    assert carla.post("/transferencias/2/recepcion", json={}).json()["estado"] == "recibida"
    # Anula solo quien despachó (o el admin).
    admin.post("/transferencias", json={"origen_id": 1, "destino_id": 2, "items": item})
    assert carla.post("/transferencias/3/anulacion", json={"motivo": "No salió"}).status_code == 403
    assert carla.post("/transferencias/1/anulacion", json={"motivo": "No salió"}).status_code == 200
    assert {t["codigo"] for t in carla.get("/transferencias").json()} == {
        "TRF-00001", "TRF-00002", "TRF-00003"}
    assert carla.get("/transferencias?sucursal_id=1").status_code == 403


def test_encargado_no_ve_transferencias_ajenas(admin, carla):
    admin.post("/sucursales", json={"codigo": "VEN", "nombre": "Ventura Mall"})
    admin.post("/transferencias", json={"origen_id": 1, "destino_id": 3,
                                        "items": [{"sku": "VES-020-ROJ-S", "cantidad": 1}]})
    assert carla.get("/transferencias/1").status_code == 403
    assert carla.get("/transferencias").json() == []
