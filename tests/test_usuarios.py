from datetime import datetime, timedelta, timezone

import pytest

from app.inventario import Conflicto, ErrorInventario, NoEncontrado
from app.usuarios import (
    CredencialesInvalidas,
    RegistroUsuarios,
    cifrar_clave,
    verificar_clave,
)


@pytest.fixture
def reg() -> RegistroUsuarios:
    r = RegistroUsuarios(secreto="secreto-de-pruebas-boutique-0123456789")
    r.crear("rosa", "Rosa Áñez", "Boutique2026", rol="admin")
    r.crear("carla.v", "Carla Vaca", "Equipetrol1", rol="encargado", sucursal_id=2)
    return r


def test_la_clave_se_guarda_cifrada_con_sal():
    a, b = cifrar_clave("Boutique2026"), cifrar_clave("Boutique2026")
    assert a != b and "Boutique2026" not in a
    assert a.startswith("pbkdf2_sha256$")
    assert verificar_clave("Boutique2026", a)
    assert not verificar_clave("boutique2026", a)
    assert not verificar_clave("Boutique2026", "formato-raro")


def test_crear_normaliza_usuario_y_oculta_hash(reg):
    u = reg.crear("  Luis.R ", "Luis Roca", "Ventas2026", sucursal_id=1)
    assert u.usuario == "luis.r" and u.rol == "encargado" and u.sucursal_id == 1
    assert "clave_hash" not in u.publico()


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        ({"usuario": "rosa"}, "ya existe"),
        ({"usuario": "x"}, "Usuario inválido"),
        ({"rol": "cajero"}, "Rol inválido"),
        ({"sucursal_id": None}, "sucursal asignada"),
        ({"clave": "corta1"}, "al menos 8"),
        ({"clave": "12345678"}, "letras y números"),
        ({"nombre": "  "}, "nombre"),
    ],
)
def test_validaciones_al_crear(reg, datos, mensaje):
    base = {"usuario": "nuevo", "nombre": "Nuevo", "clave": "Clave2026", "rol": "encargado",
            "sucursal_id": 1}
    with pytest.raises(ErrorInventario, match=mensaje):
        reg.crear(**{**base, **datos})


def test_admin_no_queda_atado_a_una_sucursal(reg):
    assert reg.crear("gerente", "Gerente", "Gerencia26", rol="admin", sucursal_id=3).sucursal_id is None


def test_autenticar(reg):
    assert reg.autenticar("ROSA", "Boutique2026").rol == "admin"
    with pytest.raises(CredencialesInvalidas):
        reg.autenticar("rosa", "otra-clave1")
    with pytest.raises(CredencialesInvalidas):
        reg.autenticar("nadie", "Boutique2026")


def test_usuario_desactivado_no_ingresa_ni_usa_su_token(reg):
    carla = reg.por_nombre("carla.v")
    token = reg.emitir_token(carla)
    reg.desactivar(carla.id)
    with pytest.raises(CredencialesInvalidas):
        reg.autenticar("carla.v", "Equipetrol1")
    with pytest.raises(CredencialesInvalidas, match="ya no tiene acceso"):
        reg.usuario_del_token(token)


def test_no_se_desactiva_al_unico_admin(reg):
    with pytest.raises(Conflicto, match="único administrador"):
        reg.desactivar(reg.por_nombre("rosa").id)
    with pytest.raises(NoEncontrado):
        reg.desactivar(99)


def test_token_ida_y_vuelta(reg):
    carla = reg.por_nombre("carla.v")
    assert reg.usuario_del_token(reg.emitir_token(carla)).id == carla.id


def test_token_vencido_o_de_otro_sistema(reg):
    rosa = reg.por_nombre("rosa")
    viejo = reg.emitir_token(rosa, ahora=datetime.now(timezone.utc) - timedelta(hours=9))
    with pytest.raises(CredencialesInvalidas, match="venció"):
        reg.usuario_del_token(viejo)
    ajeno = RegistroUsuarios(secreto="otro-secreto-de-otra-instalacion-987654").emitir_token(rosa)
    with pytest.raises(CredencialesInvalidas, match="inválido"):
        reg.usuario_del_token(ajeno)


def test_cambiar_y_restablecer_clave(reg):
    carla = reg.por_nombre("carla.v")
    with pytest.raises(CredencialesInvalidas):
        reg.cambiar_clave(carla.id, "incorrecta1", "NuevaClave9")
    reg.cambiar_clave(carla.id, "Equipetrol1", "NuevaClave9")
    assert reg.autenticar("carla.v", "NuevaClave9")
    reg.restablecer_clave(carla.id, "Temporal123")
    assert reg.autenticar("carla.v", "Temporal123")
    with pytest.raises(ErrorInventario):
        reg.restablecer_clave(carla.id, "123")


def test_secreto_corto_se_rechaza():
    with pytest.raises(ValueError, match="32 caracteres"):
        RegistroUsuarios(secreto="corto")
