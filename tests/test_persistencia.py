import json
from datetime import datetime
from decimal import Decimal

import pytest

from app import reportes
from app.inventario import Inventario
from app.persistencia import Almacen, ArchivoInvalido, exportar, importar
from app.usuarios import RegistroUsuarios

SECRETO = "secreto-de-pruebas-boutique-0123456789"


@pytest.fixture
def inv() -> Inventario:
    i = Inventario()
    i.crear_sucursal("CEN", "Centro", "Calle 24 de Septiembre #155")
    i.crear_sucursal("VEN", "Ventura Mall", "Av. San Martín y 4to anillo")
    i.crear_producto("BLU-001", "Blusa de lino", "Blusas", "189", "95", marca="Áñez")
    i.generar_matriz(1, ["S", "M"], ["Beige", "Verde oliva"])  # variantes 1-4
    i.registrar_ingreso(1, [(1, 5), (2, 6), (3, 2)], "Pedido 0102")
    i.ajustar_stock(3, 1, 1, "Conteo físico")
    t = i.enviar_transferencia(1, 2, [(2, 3)], "Reposición Ventura")
    i.recibir_transferencia(t.id, {2: 2}, "Llegó una prenda menos")
    i.registrar_venta(1, [(1, 2, "10"), (2, 1)], "efectivo", "600", "Carla",
                      fecha=datetime(2026, 10, 27, 11, 30))
    v = i.registrar_venta(2, [(2, 1)], "qr", fecha=datetime(2026, 10, 27, 16, 5))
    i.anular_venta(v.id, "Cliente cambió de talla")
    return i


@pytest.fixture
def reg() -> RegistroUsuarios:
    r = RegistroUsuarios(secreto=SECRETO, iteraciones=1_000)
    r.crear("rosa", "Rosa Áñez", "Boutique2026", rol="admin")
    r.crear("carla.v", "Carla Vaca", "Equipetrol1", sucursal_id=1)
    return r


def _ida_y_vuelta(inv, reg=None):
    nuevo_inv = Inventario()
    nuevo_reg = RegistroUsuarios(secreto=SECRETO, iteraciones=1_000) if reg else None
    importar(json.loads(json.dumps(exportar(inv, reg))), nuevo_inv, nuevo_reg)
    return nuevo_inv, nuevo_reg


def test_ida_y_vuelta_conserva_todo_el_estado(inv):
    copia, _ = _ida_y_vuelta(inv)
    assert copia.sucursales == inv.sucursales
    assert copia.productos == inv.productos
    assert copia.variantes == inv.variantes
    assert copia.movimientos == inv.movimientos
    assert copia.transferencias == inv.transferencias
    assert copia.ventas == inv.ventas
    for v in inv.variantes:
        for s in inv.sucursales:
            assert copia.stock(v, s) == inv.stock(v, s)


def test_montos_se_guardan_como_texto_sin_perder_precision(inv):
    datos = exportar(inv)
    assert datos["productos"][0]["precio_venta"] == "189.00"
    copia, _ = _ida_y_vuelta(inv)
    venta = copia.ventas[1]
    assert venta.total == Decimal("529.20") and venta.cambio == Decimal("70.80")
    assert isinstance(copia.productos[1].costo, Decimal)


def test_los_reportes_dan_lo_mismo_despues_de_cargar(inv):
    copia, _ = _ida_y_vuelta(inv)
    assert reportes.resumen_ventas(copia) == reportes.resumen_ventas(inv)
    assert reportes.valor_inventario(copia) == reportes.valor_inventario(inv)


def test_los_codigos_continuan_la_secuencia(inv):
    copia, _ = _ida_y_vuelta(inv)
    v = copia.registrar_venta(1, [(1, 1)], "tarjeta")
    assert v.codigo == "V-CEN-000003"
    assert copia.movimientos[-1].id == len(inv.movimientos) + 1
    nuevo = copia.crear_producto("JEA-010", "Jean skinny", "Jeans", "260", "130")
    assert nuevo.id == 2


def test_usuarios_se_restauran_y_pueden_ingresar(inv, reg):
    reg.desactivar(2)
    _, copia = _ida_y_vuelta(inv, reg)
    assert copia.autenticar("rosa", "Boutique2026").rol == "admin"
    assert copia.usuarios[2].activo is False
    assert copia.crear("luis.r", "Luis Roca", "Ventas2026", sucursal_id=2).id == 3


def test_el_archivo_no_guarda_claves_en_texto_plano_ni_el_secreto(inv, reg, tmp_path):
    almacen = Almacen(tmp_path / "boutique.json")
    almacen.guardar(inv, reg)
    texto = almacen.ruta.read_text(encoding="utf-8")
    assert "Boutique2026" not in texto and SECRETO not in texto
    assert "pbkdf2_sha256$" in texto
    assert "Rosa Áñez" in texto  # UTF-8 legible, no Á


def test_guardar_y_cargar_desde_archivo(inv, reg, tmp_path):
    almacen = Almacen(tmp_path / "datos" / "boutique.json")
    assert almacen.cargar(Inventario()) is False  # primer arranque
    almacen.guardar(inv, reg)
    nuevo_inv, nuevo_reg = Inventario(), RegistroUsuarios(secreto=SECRETO)
    assert almacen.cargar(nuevo_inv, nuevo_reg) is True
    assert nuevo_inv.stock(2, 2) == 2 and len(nuevo_reg.usuarios) == 2
    assert [p.name for p in almacen.ruta.parent.iterdir()] == ["boutique.json"]


def test_guardado_atomico_si_falla_queda_el_archivo_anterior(inv, tmp_path, monkeypatch):
    almacen = Almacen(tmp_path / "boutique.json")
    almacen.guardar(inv)
    antes = almacen.ruta.read_text(encoding="utf-8")
    inv.crear_producto("POL-020", "Polera básica", "Poleras", "79", "35")

    def falla(*_):
        raise OSError("disco lleno")

    monkeypatch.setattr("app.persistencia.os.replace", falla)
    with pytest.raises(OSError):
        almacen.guardar(inv)
    assert almacen.ruta.read_text(encoding="utf-8") == antes
    assert [p.name for p in tmp_path.iterdir()] == ["boutique.json"]  # sin temporales


@pytest.mark.parametrize(
    "contenido, mensaje",
    [
        ("{no es json", "No se pudo leer"),
        ('{"formato": 99}', "no soportado"),
        ('{"formato": 1, "sucursales": []}', "dañado"),
    ],
)
def test_archivo_invalido(tmp_path, contenido, mensaje):
    ruta = tmp_path / "boutique.json"
    ruta.write_text(contenido, encoding="utf-8")
    inv = Inventario()
    with pytest.raises(ArchivoInvalido, match=mensaje):
        Almacen(ruta).cargar(inv)


def test_un_archivo_danado_no_deja_el_estado_a_medias(inv):
    datos = exportar(inv)
    datos["ventas"][0]["fecha"] = "ayer"
    antes = dict(inv.productos)
    with pytest.raises(ArchivoInvalido):
        importar(datos, inv)
    assert inv.productos == antes and len(inv.ventas) == 2
