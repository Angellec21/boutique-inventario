from datetime import datetime
from decimal import Decimal

import pytest

from app import reportes
from app.datos_ejemplo import USUARIOS_DEMO, cargar_ejemplo, main
from app.inventario import Inventario
from app.persistencia import Almacen
from app.usuarios import RegistroUsuarios

HOY = datetime(2026, 10, 28, 20, 0)


@pytest.fixture(scope="module")
def tienda():
    inv = Inventario()
    usuarios = RegistroUsuarios(secreto="secreto-de-pruebas-boutique-0123456789", iteraciones=1_000)
    resumen = cargar_ejemplo(inv, usuarios, hoy=HOY)
    return inv, usuarios, resumen


def test_genera_una_boutique_completa(tienda):
    inv, usuarios, resumen = tienda
    assert resumen["sucursales"] == 3 and resumen["productos"] == 8
    assert resumen["variantes"] == len(inv.variantes) > 40
    assert resumen["ventas"] > 100 and resumen["usuarios"] == 3
    assert {s.nombre for s in inv.sucursales.values()} == {"Centro", "Equipetrol", "Ventura Mall"}


def test_es_reproducible():
    a, b = Inventario(), Inventario()
    cargar_ejemplo(a, hoy=HOY)
    cargar_ejemplo(b, hoy=HOY)
    assert reportes.resumen_ventas(a) == reportes.resumen_ventas(b)


def test_ventas_dentro_del_periodo_y_coherentes(tienda):
    inv, _, _ = tienda
    fechas = [v.fecha for v in inv.ventas.values()]
    assert min(fechas) >= datetime(2026, 10, 14, 9, 0) and max(fechas) < HOY
    for v in inv.ventas.values():
        if v.metodo_pago == "efectivo":
            assert v.monto_recibido >= v.total and v.monto_recibido % 10 == 0
    assert {v.metodo_pago for v in inv.ventas.values()} == {"efectivo", "qr", "tarjeta"}
    assert sum(v.estado == "anulada" for v in inv.ventas.values()) == 1


def test_stock_nunca_negativo_y_kardex_cuadra(tienda):
    inv, _, _ = tienda
    assert all(c >= 0 for c in inv._stock.values())
    for (variante_id, sucursal_id), cantidad in inv._stock.items():
        kardex = inv.kardex(variante_id, sucursal_id)
        assert sum(m.cantidad for m in kardex) == cantidad


def test_reportes_del_dueno_tienen_contenido(tienda):
    inv, _, _ = tienda
    resumen = reportes.resumen_ventas(inv)
    assert Decimal(resumen["total"]) > Decimal("10000")
    assert len(reportes.mas_vendidos(inv, limite=5)) == 5
    assert len(reportes.valor_inventario(inv)) == 3
    trf = next(iter(inv.transferencias.values()))
    assert trf.estado == "recibida_con_diferencias" and trf.unidades_faltantes == 1


def test_usuarios_de_demostracion_pueden_ingresar(tienda):
    _, usuarios, _ = tienda
    for usuario, _, clave, rol, _ in USUARIOS_DEMO:
        assert usuarios.autenticar(usuario, clave).rol == rol
    assert usuarios.por_nombre("carla.v").sucursal_id == 2


def test_no_mezcla_con_un_inventario_con_datos():
    inv = Inventario()
    inv.crear_sucursal("CEN", "Centro")
    with pytest.raises(ValueError, match="ya tiene datos"):
        cargar_ejemplo(inv)


def test_linea_de_comandos_escribe_y_no_pisa_sin_forzar(tmp_path, capsys):
    ruta = tmp_path / "boutique.json"
    assert main(["--archivo", str(ruta), "--dias", "3"]) == 0
    assert "Boutique de ejemplo guardada" in capsys.readouterr().out
    inv = Inventario()
    assert Almacen(ruta).cargar(inv) and len(inv.sucursales) == 3

    assert main(["--archivo", str(ruta)]) == 1
    assert "--forzar" in capsys.readouterr().err
    assert main(["--archivo", str(ruta), "--forzar", "--dias", "1"]) == 0


def test_la_api_arranca_con_los_datos_de_ejemplo(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.ayudas import SECRETO, ingresar

    ruta = tmp_path / "boutique.json"
    assert main(["--archivo", str(ruta), "--dias", "2"]) == 0
    app = create_app(usuarios=RegistroUsuarios(secreto=SECRETO), datos=ruta)
    c = ingresar(TestClient(app), "rosa", "Boutique2026")
    assert len(c.get("/sucursales").json()) == 3
    assert c.get("/reportes/resumen-ventas").json()["cantidad_ventas"] > 0
    encargada = ingresar(TestClient(c.app), "carla.v", "Equipetrol26")
    assert {v["sucursal"] for v in encargada.get("/ventas").json()} == {"EQP"}
