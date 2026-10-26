from datetime import datetime
from decimal import Decimal

import pytest

from app.inventario import Conflicto, ErrorInventario, Inventario, NoEncontrado, StockInsuficiente


@pytest.fixture
def inv() -> Inventario:
    i = Inventario()
    i.crear_sucursal("CEN", "Centro", "Calle 24 de Septiembre #155")
    i.crear_sucursal("VEN", "Ventura Mall", "Av. San Martín y 4to anillo")
    i.crear_producto("BLU-001", "Blusa de lino", "Blusas", "189", "95")
    i.crear_producto("JEA-010", "Jean skinny tiro alto", "Jeans", "260", "130")
    i.generar_matriz(1, ["S", "M"], ["Beige"])  # variantes 1, 2
    i.generar_matriz(2, ["28", "30"], ["Azul"])  # variantes 3, 4
    i.registrar_ingreso(1, [(1, 3), (2, 5), (3, 2), (4, 4)], "Pedido 0102")
    return i


def test_venta_en_efectivo_descuenta_stock_y_calcula_cambio(inv):
    v = inv.registrar_venta(1, [(2, 2), (4, 1)], "efectivo", "700", vendedor="Carla")
    assert v.codigo == "V-CEN-000001"
    assert v.total == Decimal("638.00")
    assert v.cambio == Decimal("62.00")
    assert v.unidades == 3
    assert inv.stock(2, 1) == 3 and inv.stock(4, 1) == 3
    mov = inv.kardex(2, 1)[-1]
    assert (mov.tipo, mov.cantidad, mov.referencia) == ("venta", -2, "V-CEN-000001")
    assert v.items[0].descripcion == "Blusa de lino Beige T.M"


def test_descuento_por_linea_y_redondeo(inv):
    v = inv.registrar_venta(1, [(2, 1, "15"), (3, 1)], "qr")
    assert v.items[0].descuento == Decimal("28.35")
    assert v.descuento_total == Decimal("28.35")
    assert v.total == Decimal("420.65")
    assert v.monto_recibido is None and v.cambio == Decimal("0.00")


def test_descuento_fuera_de_rango(inv):
    with pytest.raises(ErrorInventario, match="Descuento"):
        inv.registrar_venta(1, [(2, 1, 60)], "tarjeta")


def test_venta_es_todo_o_nada(inv):
    with pytest.raises(StockInsuficiente):
        inv.registrar_venta(1, [(2, 1), (3, 3)], "qr")
    assert inv.stock(2, 1) == 5
    assert inv.ventas == {}


def test_suma_items_repetidos_al_validar_stock(inv):
    with pytest.raises(StockInsuficiente):
        inv.registrar_venta(1, [(1, 2), (1, 2)], "qr")


def test_no_vende_en_sucursal_sin_stock(inv):
    with pytest.raises(StockInsuficiente, match="VEN"):
        inv.registrar_venta(2, [(1, 1)], "tarjeta")


def test_efectivo_exige_monto_suficiente(inv):
    with pytest.raises(ErrorInventario, match="monto recibido"):
        inv.registrar_venta(1, [(1, 1)], "efectivo")
    with pytest.raises(ErrorInventario, match="insuficiente"):
        inv.registrar_venta(1, [(1, 1)], "efectivo", "100")


def test_metodo_de_pago_invalido(inv):
    with pytest.raises(ErrorInventario, match="Método"):
        inv.registrar_venta(1, [(1, 1)], "cheque")


def test_no_vende_producto_dado_de_baja(inv):
    inv.productos[1].activo = False
    with pytest.raises(ErrorInventario, match="baja"):
        inv.registrar_venta(1, [(1, 1)], "qr")


def test_precio_y_costo_quedan_congelados(inv):
    v = inv.registrar_venta(1, [(1, 1)], "qr")
    inv.productos[1].precio_venta = Decimal("210.00")
    assert v.items[0].precio_unitario == Decimal("189.00")
    assert v.items[0].costo_total == Decimal("95.00")


def test_anular_venta_devuelve_stock(inv):
    v = inv.registrar_venta(1, [(2, 2), (2, 1)], "qr")
    assert inv.stock(2, 1) == 2
    inv.anular_venta(v.id, "Cliente devolvió la prenda")
    assert v.estado == "anulada"
    assert inv.stock(2, 1) == 5
    mov = inv.kardex(2, 1)[-1]
    assert (mov.tipo, mov.cantidad) == ("anulacion_venta", 3)
    with pytest.raises(Conflicto):
        inv.anular_venta(v.id, "otra vez")


def test_anular_exige_motivo_y_venta_existente(inv):
    v = inv.registrar_venta(1, [(1, 1)], "qr")
    with pytest.raises(ErrorInventario, match="motivo"):
        inv.anular_venta(v.id, "  ")
    with pytest.raises(NoEncontrado):
        inv.anular_venta(99, "no existe")


def test_listar_ventas_por_sucursal_y_fecha(inv):
    inv.registrar_ingreso(2, [(1, 2)])
    inv.registrar_venta(1, [(1, 1)], "qr", fecha=datetime(2026, 10, 20, 10))
    inv.registrar_venta(2, [(1, 1)], "qr", fecha=datetime(2026, 10, 21, 16))
    anulada = inv.registrar_venta(1, [(2, 1)], "qr", fecha=datetime(2026, 10, 21, 18))
    inv.anular_venta(anulada.id, "Error de caja")
    assert [v.codigo for v in inv.listar_ventas(sucursal_id=1)] == ["V-CEN-000001", "V-CEN-000003"]
    dia = inv.listar_ventas(desde=datetime(2026, 10, 21), hasta=datetime(2026, 10, 22))
    assert len(dia) == 2
    assert len(inv.listar_ventas(desde=datetime(2026, 10, 21), incluir_anuladas=False)) == 1
