from decimal import Decimal

import pytest

from app.inventario import (
    Conflicto,
    ErrorInventario,
    Inventario,
    NoEncontrado,
    StockInsuficiente,
    generar_sku,
)


@pytest.fixture
def inv() -> Inventario:
    i = Inventario()
    i.crear_sucursal("CEN", "Centro", "Calle 24 de Septiembre #155")
    i.crear_sucursal("EQP", "Equipetrol", "Av. San Martín, 3er anillo")
    i.crear_producto("BLU-001", "Blusa de lino manga corta", "blusas", "189", "95", "Amalia")
    return i


def test_sku_se_genera_sin_tildes_y_abreviado():
    assert generar_sku("blu-001", "Azul marino", "M") == "BLU-001-AZM-M"
    assert generar_sku("JEA-010", "Índigo", "32") == "JEA-010-IND-32"


def test_producto_redondea_precio_y_calcula_margen(inv):
    p = inv.obtener_producto(1)
    assert p.precio_venta == Decimal("189.00")
    assert p.margen == Decimal("94.00")
    assert p.categoria == "Blusas"


def test_no_permite_codigo_de_producto_duplicado(inv):
    with pytest.raises(Conflicto):
        inv.crear_producto("blu-001", "Otra", "Blusas", 100, 50)


def test_costo_mayor_al_precio_es_error(inv):
    with pytest.raises(ErrorInventario):
        inv.crear_producto("VES-001", "Vestido", "Vestidos", 100, 150)


def test_variante_normaliza_talla_y_color(inv):
    v = inv.agregar_variante(1, " m ", "blanco  hueso")
    assert (v.talla, v.color, v.sku) == ("M", "Blanco hueso", "BLU-001-BLH-M")


def test_talla_invalida(inv):
    with pytest.raises(ValueError):
        inv.agregar_variante(1, "XXXL-grande", "Rojo")


def test_variante_duplicada(inv):
    inv.agregar_variante(1, "S", "Rojo")
    with pytest.raises(Conflicto):
        inv.agregar_variante(1, "s", "rojo")


def test_matriz_crea_solo_combinaciones_faltantes(inv):
    inv.agregar_variante(1, "M", "Negro")
    creadas = inv.generar_matriz(1, ["S", "M", "L"], ["Negro", "Beige"])
    assert len(creadas) == 5
    assert len(inv.variantes_de(1)) == 6


def test_buscar_productos_ignora_tildes_y_filtra_categoria(inv):
    inv.crear_producto("JEA-010", "Jean índigo tiro alto", "Jeans", 260, 140)
    assert [p.codigo for p in inv.buscar_productos("indigo")] == ["JEA-010"]
    assert [p.codigo for p in inv.buscar_productos(categoria="blusas")] == ["BLU-001"]


def test_ingreso_suma_stock_por_sucursal(inv):
    v = inv.agregar_variante(1, "M", "Negro")
    inv.registrar_ingreso(1, [(v.id, 10)], referencia="Pedido 0045")
    inv.registrar_ingreso(2, [(v.id, 4)])
    assert inv.stock(v.id, 1) == 10
    assert inv.stock(v.id, 2) == 4
    assert inv.stock_total(v.id) == 14


def test_ingreso_es_todo_o_nada(inv):
    v = inv.agregar_variante(1, "M", "Negro")
    with pytest.raises(NoEncontrado):
        inv.registrar_ingreso(1, [(v.id, 5), (999, 3)])
    assert inv.stock(v.id, 1) == 0
    with pytest.raises(ErrorInventario):
        inv.registrar_ingreso(1, [(v.id, 0)])


def test_ajuste_por_conteo_registra_diferencia_en_kardex(inv):
    v = inv.agregar_variante(1, "L", "Negro")
    inv.registrar_ingreso(1, [(v.id, 8)])
    mov = inv.ajustar_stock(v.id, 1, 6, "Conteo físico semanal")
    assert mov.cantidad == -2 and mov.saldo == 6
    assert [m.tipo for m in inv.kardex(v.id)] == ["ingreso", "ajuste"]


def test_ajuste_requiere_motivo(inv):
    v = inv.agregar_variante(1, "L", "Negro")
    with pytest.raises(ErrorInventario):
        inv.ajustar_stock(v.id, 1, 3, "  ")


def test_stock_no_puede_quedar_negativo(inv):
    v = inv.agregar_variante(1, "L", "Negro")
    with pytest.raises(StockInsuficiente):
        inv._mover(v.id, 1, -1, "venta")


def test_matriz_de_stock_talla_por_color(inv):
    inv.generar_matriz(1, ["L", "S", "M"], ["Negro", "Beige"])
    negro_m = next(v for v in inv.variantes_de(1) if v.color == "Negro" and v.talla == "M")
    inv.registrar_ingreso(1, [(negro_m.id, 3)])
    inv.registrar_ingreso(2, [(negro_m.id, 2)])
    m = inv.matriz_stock(1)
    assert m["tallas"] == ["S", "M", "L"]
    assert m["colores"] == ["Beige", "Negro"]
    assert m["celdas"]["Negro"]["M"] == 5
    assert m["total_unidades"] == 5
    assert m["valor_venta"] == "945.00"
    assert inv.matriz_stock(1, sucursal_id=2)["celdas"]["Negro"]["M"] == 2


def test_alerta_bajo_minimo_indica_stock_en_otras_sucursales(inv):
    a = inv.agregar_variante(1, "S", "Rojo", stock_minimo=2)
    b = inv.agregar_variante(1, "M", "Rojo", stock_minimo=2)
    inv.registrar_ingreso(1, [(a.id, 1), (b.id, 6)])
    inv.registrar_ingreso(2, [(a.id, 5)])
    alertas = inv.bajo_minimo(1)
    assert [x["sku"] for x in alertas] == [a.sku]
    assert alertas[0]["faltante"] == 2
    assert alertas[0]["en_otras_sucursales"] == 5


def test_sucursal_duplicada_y_variante_por_sku(inv):
    with pytest.raises(Conflicto):
        inv.crear_sucursal("cen", "Centro 2")
    v = inv.agregar_variante(1, "XL", "Verde")
    assert inv.variante_por_sku("blu-001-ver-xl").id == v.id
    with pytest.raises(NoEncontrado):
        inv.variante_por_sku("NO-EXISTE")
