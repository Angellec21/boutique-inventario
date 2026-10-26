from datetime import datetime

import pytest

from app import reportes
from app.inventario import ErrorInventario, Inventario, NoEncontrado

DIA = datetime(2026, 10, 24)


@pytest.fixture
def inv() -> Inventario:
    i = Inventario()
    i.crear_sucursal("CEN", "Centro")
    i.crear_sucursal("VEN", "Ventura Mall")
    i.crear_producto("BLU-001", "Blusa de lino", "Blusas", "189", "95")
    i.crear_producto("JEA-010", "Jean skinny tiro alto", "Jeans", "260", "130")
    i.generar_matriz(1, ["S", "M"], ["Beige"])  # 1, 2
    i.generar_matriz(2, ["28", "30"], ["Azul"])  # 3, 4
    i.registrar_ingreso(1, [(1, 10), (2, 10), (3, 10), (4, 10)])
    i.registrar_ingreso(2, [(2, 5)])
    i.registrar_venta(1, [(2, 3), (3, 1)], "efectivo", "1000", "Carla", datetime(2026, 10, 24, 10))
    i.registrar_venta(1, [(1, 1, 10)], "qr", vendedor="Luis", fecha=datetime(2026, 10, 24, 12))
    i.registrar_venta(2, [(2, 2)], "tarjeta", vendedor="Ana", fecha=datetime(2026, 10, 24, 17))
    anulada = i.registrar_venta(1, [(4, 5)], "qr", fecha=datetime(2026, 10, 24, 18))
    i.anular_venta(anulada.id, "Error de caja")
    i.registrar_venta(1, [(4, 1)], "qr", fecha=datetime(2026, 10, 25, 9))
    return i


def test_mas_vendidos_por_producto_sin_anuladas(inv):
    top = reportes.mas_vendidos(inv, desde=DIA, hasta=datetime(2026, 10, 25))
    assert [(f["posicion"], f["codigo"], f["unidades"]) for f in top] == [
        (1, "BLU-001", 6), (2, "JEA-010", 1)]
    blusa = top[0]
    # 5 × 189 + 189 − 10 % = 945 + 170.10
    assert blusa["importe"] == "1115.10"
    assert blusa["margen"] == "545.10"
    assert blusa["margen_pct"] == "48.9"


def test_mas_vendidos_por_variante_sucursal_y_limite(inv):
    top = reportes.mas_vendidos(inv, sucursal_id=1, por="variante", limite=2)
    # empate de 1 unidad: gana el de mayor importe (jean Bs 260 > blusa con descuento)
    assert [f["codigo"] for f in top] == ["BLU-001-BEI-M", "JEA-010-AZU-28"]
    assert top[0]["talla"] == "M" and top[0]["unidades"] == 3


def test_mas_vendidos_valida_parametros(inv):
    with pytest.raises(ErrorInventario):
        reportes.mas_vendidos(inv, por="color")
    with pytest.raises(NoEncontrado):
        reportes.mas_vendidos(inv, sucursal_id=9)


def test_ventas_por_talla_ordenadas_y_con_participacion(inv):
    filas = reportes.ventas_por_talla(inv)
    assert [(f["talla"], f["unidades"]) for f in filas] == [("S", 1), ("M", 5), ("28", 1), ("30", 1)]
    assert filas[1]["participacion_pct"] == "62.5"
    jeans = reportes.ventas_por_talla(inv, categoria="jeans")
    assert [f["talla"] for f in jeans] == ["28", "30"]


def test_resumen_de_caja_del_dia(inv):
    r = reportes.resumen_ventas(inv, desde=DIA, hasta=datetime(2026, 10, 25), sucursal_id=1)
    assert r["cantidad_ventas"] == 2 and r["ventas_anuladas"] == 1
    assert r["unidades"] == 5
    assert r["total"] == "997.10"  # 567 + 260 + 170.10
    assert r["descuentos"] == "18.90"
    assert r["ticket_promedio"] == "498.55"
    assert r["por_metodo_pago"] == {"efectivo": "827.00", "qr": "170.10"}
    assert list(r["por_vendedor"]) == ["Carla", "Luis"]


def test_resumen_sin_ventas(inv):
    r = reportes.resumen_ventas(inv, desde=datetime(2027, 1, 1))
    assert (r["cantidad_ventas"], r["total"], r["ticket_promedio"], r["margen_pct"]) == (
        0, "0.00", "0.00", "0.0")


def test_valor_inventario_por_sucursal(inv):
    filas = {f["sucursal"]: f for f in reportes.valor_inventario(inv)}
    ven = filas["Ventura Mall"]
    assert ven["unidades"] == 3
    assert (ven["valor_costo"], ven["valor_venta"], ven["ganancia_potencial"]) == (
        "285.00", "567.00", "282.00")
    assert filas["Centro"]["unidades"] == 40 - 6
