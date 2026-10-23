import pytest

from app.inventario import Conflicto, ErrorInventario, Inventario, NoEncontrado, StockInsuficiente


@pytest.fixture
def inv() -> Inventario:
    i = Inventario()
    i.crear_sucursal("CEN", "Centro", "Calle 24 de Septiembre #155")
    i.crear_sucursal("VEN", "Ventura Mall", "Av. San Martín y 4to anillo")
    i.crear_producto("VES-020", "Vestido midi floreado", "Vestidos", "320", "160")
    i.generar_matriz(1, ["S", "M", "L"], ["Rojo"])  # variantes 1, 2, 3
    i.registrar_ingreso(1, [(1, 4), (2, 6), (3, 2)], "Pedido 0101")
    return i


def test_envio_descuenta_origen_y_queda_en_transito(inv):
    trf = inv.enviar_transferencia(1, 2, [(2, 3), (3, 1)], "Para la vitrina del mall")
    assert trf.codigo == "TRF-00001"
    assert trf.estado == "en_transito"
    assert trf.unidades_enviadas == 4
    assert inv.stock(2, 1) == 3 and inv.stock(2, 2) == 0
    assert inv.en_transito() == 4
    assert inv.en_transito(2) == 3
    salida = inv.kardex(2, 1)[-1]
    assert (salida.tipo, salida.cantidad, salida.referencia) == ("transferencia_salida", -3, "TRF-00001")


def test_envio_agrupa_variantes_repetidas(inv):
    trf = inv.enviar_transferencia(1, 2, [(1, 1), (1, 2)])
    assert len(trf.items) == 1 and trf.items[0].enviado == 3


def test_envio_es_todo_o_nada(inv):
    with pytest.raises(StockInsuficiente):
        inv.enviar_transferencia(1, 2, [(2, 1), (3, 5)])
    assert inv.stock(2, 1) == 6
    assert inv.transferencias == {}


def test_envio_no_permite_misma_sucursal_ni_vacio(inv):
    with pytest.raises(ErrorInventario):
        inv.enviar_transferencia(1, 1, [(1, 1)])
    with pytest.raises(ErrorInventario):
        inv.enviar_transferencia(1, 2, [])
    with pytest.raises(NoEncontrado):
        inv.enviar_transferencia(1, 9, [(1, 1)])


def test_recepcion_completa_suma_al_destino(inv):
    trf = inv.enviar_transferencia(1, 2, [(2, 3)])
    inv.recibir_transferencia(trf.id)
    assert trf.estado == "recibida"
    assert inv.stock(2, 2) == 3
    assert inv.en_transito() == 0
    assert inv.stock_total(2) == 6  # la mercadería solo cambió de tienda
    entrada = inv.kardex(2, 2)[-1]
    assert entrada.tipo == "transferencia_entrada" and entrada.motivo == "Recepción desde CEN"


def test_recepcion_con_faltante_exige_observacion(inv):
    trf = inv.enviar_transferencia(1, 2, [(1, 2), (2, 3)])
    with pytest.raises(ErrorInventario):
        inv.recibir_transferencia(trf.id, {2: 2})
    assert trf.estado == "en_transito"  # no se registró nada
    inv.recibir_transferencia(trf.id, {2: 2}, "Faltó una prenda en la bolsa")
    assert trf.estado == "recibida_con_diferencias"
    assert trf.unidades_faltantes == 1
    assert inv.stock(1, 2) == 2 and inv.stock(2, 2) == 2


def test_recepcion_no_acepta_mas_de_lo_enviado_ni_variantes_ajenas(inv):
    trf = inv.enviar_transferencia(1, 2, [(2, 3)])
    with pytest.raises(ErrorInventario):
        inv.recibir_transferencia(trf.id, {2: 4})
    with pytest.raises(ErrorInventario):
        inv.recibir_transferencia(trf.id, {1: 1})


def test_no_se_recibe_dos_veces(inv):
    trf = inv.enviar_transferencia(1, 2, [(2, 1)])
    inv.recibir_transferencia(trf.id)
    with pytest.raises(Conflicto):
        inv.recibir_transferencia(trf.id)


def test_anular_devuelve_stock_al_origen(inv):
    trf = inv.enviar_transferencia(1, 2, [(2, 3)])
    with pytest.raises(ErrorInventario):
        inv.anular_transferencia(trf.id, "  ")
    inv.anular_transferencia(trf.id, "El mensajero no pudo salir")
    assert trf.estado == "anulada"
    assert inv.stock(2, 1) == 6 and inv.en_transito() == 0
    with pytest.raises(Conflicto):
        inv.recibir_transferencia(trf.id)


def test_listar_por_sucursal_y_estado(inv):
    a = inv.enviar_transferencia(1, 2, [(1, 1)])
    inv.enviar_transferencia(1, 2, [(2, 1)])
    inv.recibir_transferencia(a.id)
    assert len(inv.listar_transferencias(2)) == 2
    assert [t.codigo for t in inv.listar_transferencias(2, "en_transito")] == ["TRF-00002"]
    inv.crear_sucursal("EQP", "Equipetrol")
    assert inv.listar_transferencias(3) == []
