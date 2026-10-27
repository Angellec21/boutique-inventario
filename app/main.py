"""API REST del inventario de la boutique (FastAPI).

Ejecutar en desarrollo:  ``uvicorn app.main:app --reload``
Documentación interactiva: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import reportes
from .inventario import (
    Conflicto,
    ErrorInventario,
    Inventario,
    NoEncontrado,
    StockInsuficiente,
)
from .models import Movimiento, Producto, Sucursal, Transferencia, Variante, Venta
from .schemas import (
    AjusteIn,
    AnulacionIn,
    CambioClaveIn,
    LoginIn,
    RestablecerClaveIn,
    UsuarioIn,
    IngresoIn,
    MatrizIn,
    ProductoIn,
    RecepcionIn,
    SucursalIn,
    TransferenciaIn,
    VarianteIn,
    VentaIn,
)
from .usuarios import CredencialesInvalidas, RegistroUsuarios, Usuario

log = logging.getLogger("boutique")

_ESTADOS = {NoEncontrado: 404, Conflicto: 409, StockInsuficiente: 409, CredencialesInvalidas: 401}
_ESTADOS_TRANSFERENCIA = ("en_transito", "recibida", "recibida_con_diferencias", "anulada")


def _vista_transferencia(i: Inventario, t: Transferencia) -> dict:
    return {
        **t.model_dump(),
        "origen": i.sucursales[t.origen_id].codigo,
        "destino": i.sucursales[t.destino_id].codigo,
        "unidades_enviadas": t.unidades_enviadas,
        "unidades_faltantes": t.unidades_faltantes,
    }


def _vista_venta(i: Inventario, v: Venta) -> dict:
    return {
        **v.model_dump(mode="json"),
        "sucursal": i.sucursales[v.sucursal_id].codigo,
        "items": [
            {**it.model_dump(mode="json", exclude={"costo_unitario"}), "subtotal": str(it.subtotal)}
            for it in v.items
        ],
        "unidades": v.unidades,
        "descuento_total": str(v.descuento_total),
        "total": str(v.total),
        "cambio": str(v.cambio),
    }


def _rango(
    desde: Optional[date], hasta: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Fechas de la consulta (``hasta`` inclusive) a datetimes con fin exclusivo."""
    if desde and hasta and hasta < desde:
        raise HTTPException(422, "La fecha 'hasta' no puede ser anterior a 'desde'")
    inicio = datetime.combine(desde, time.min) if desde else None
    fin = datetime.combine(hasta + timedelta(days=1), time.min) if hasta else None
    return inicio, fin


def _admin_inicial(registro: RegistroUsuarios) -> None:
    """Primer arranque sin usuarios: crea el administrador.

    Usuario y contraseña salen de ``BOUTIQUE_ADMIN_USUARIO`` / ``BOUTIQUE_ADMIN_CLAVE``.
    Si no se definió la contraseña se genera una aleatoria y se muestra una sola vez.
    """
    if registro.usuarios:
        return
    usuario = os.environ.get("BOUTIQUE_ADMIN_USUARIO", "admin")
    clave = os.environ.get("BOUTIQUE_ADMIN_CLAVE")
    if not clave:
        clave = secrets.token_urlsafe(9) + "9a"
        log.warning("Administrador inicial creado: usuario=%s clave=%s (cámbiela)", usuario, clave)
    registro.crear(usuario, "Administrador", clave, rol="admin")


def _sin_costos(datos: dict) -> dict:
    """El encargado de tienda no ve costos ni márgenes."""
    return {k: v for k, v in datos.items() if k not in ("costo", "margen")}


def create_app(
    inventario: Optional[Inventario] = None, usuarios: Optional[RegistroUsuarios] = None
) -> FastAPI:
    app = FastAPI(
        title="Boutique Inventario",
        description=(
            "Inventario para tiendas de ropa: tallas, colores y sucursales. Montos en Bs. "
            "Ingrese con POST /auth/token y use el botón Authorize con el token."
        ),
        version="0.3.0",
    )
    app.state.inventario = inventario or Inventario()
    if usuarios is None:
        usuarios = RegistroUsuarios()
        _admin_inicial(usuarios)
    app.state.usuarios = usuarios

    @app.exception_handler(ErrorInventario)
    async def _errores_de_negocio(_: Request, exc: ErrorInventario):
        estado = _ESTADOS.get(type(exc), 422)
        extra = {"WWW-Authenticate": "Bearer"} if estado == 401 else None
        return JSONResponse(status_code=estado, content={"detail": str(exc)}, headers=extra)

    @app.exception_handler(ValueError)
    async def _valores_invalidos(_: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def inv(request: Request) -> Inventario:
        return request.app.state.inventario

    def registro(request: Request) -> RegistroUsuarios:
        return request.app.state.usuarios

    bearer = HTTPBearer(auto_error=False, description="Token de POST /auth/token")

    def actual(
        cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
        r: RegistroUsuarios = Depends(registro),
    ) -> Usuario:
        if cred is None:
            raise CredencialesInvalidas("Debe iniciar sesión")
        return r.usuario_del_token(cred.credentials)

    def solo_admin(u: Usuario = Depends(actual)) -> Usuario:
        if u.rol != "admin":
            raise HTTPException(403, "Solo el administrador puede hacer esto")
        return u

    def de_su_sucursal(u: Usuario, *sucursales: int) -> None:
        """El encargado solo opera en su sucursal (en alguna de las indicadas)."""
        if u.rol == "encargado" and u.sucursal_id not in sucursales:
            raise HTTPException(403, "Solo puede operar en su sucursal")

    def sucursal_visible(u: Usuario, sucursal_id: Optional[int]) -> Optional[int]:
        """Para listados: el encargado siempre ve su sucursal."""
        if u.rol == "encargado":
            if sucursal_id is not None:
                de_su_sucursal(u, sucursal_id)
            return u.sucursal_id
        return sucursal_id

    @app.get("/salud", tags=["sistema"])
    def salud():
        return {"estado": "ok"}

    # ------------------------------------------------------------------ acceso
    @app.post("/auth/token", tags=["acceso"], summary="Iniciar sesión")
    def ingresar(datos: LoginIn, r: RegistroUsuarios = Depends(registro)):
        u = r.autenticar(datos.usuario, datos.clave)
        return {
            "access_token": r.emitir_token(u),
            "token_type": "bearer",
            "expira_en_minutos": r.minutos_token,
            "usuario": u.publico(),
        }

    @app.get("/auth/yo", tags=["acceso"], summary="Usuario de la sesión")
    def yo(u: Usuario = Depends(actual)):
        return u.publico()

    @app.post("/auth/clave", status_code=204, tags=["acceso"], summary="Cambiar mi contraseña")
    def cambiar_mi_clave(
        datos: CambioClaveIn, u: Usuario = Depends(actual), r: RegistroUsuarios = Depends(registro)
    ):
        r.cambiar_clave(u.id, datos.actual, datos.nueva)

    # ---------------------------------------------------------------- usuarios
    @app.post("/usuarios", status_code=201, tags=["usuarios"])
    def crear_usuario(
        datos: UsuarioIn,
        _: Usuario = Depends(solo_admin),
        r: RegistroUsuarios = Depends(registro),
        i: Inventario = Depends(inv),
    ):
        if datos.sucursal_id is not None:
            i.obtener_sucursal(datos.sucursal_id)
        return r.crear(**datos.model_dump()).publico()

    @app.get("/usuarios", tags=["usuarios"])
    def listar_usuarios(_: Usuario = Depends(solo_admin), r: RegistroUsuarios = Depends(registro)):
        return [u.publico() for u in r.usuarios.values()]

    @app.post("/usuarios/{usuario_id}/baja", tags=["usuarios"], summary="Desactivar usuario")
    def baja_usuario(
        usuario_id: int, _: Usuario = Depends(solo_admin), r: RegistroUsuarios = Depends(registro)
    ):
        return r.desactivar(usuario_id).publico()

    @app.post("/usuarios/{usuario_id}/clave", status_code=204, tags=["usuarios"])
    def restablecer_clave(
        usuario_id: int,
        datos: RestablecerClaveIn,
        _: Usuario = Depends(solo_admin),
        r: RegistroUsuarios = Depends(registro),
    ):
        r.restablecer_clave(usuario_id, datos.nueva)

    # ---------------------------------------------------------------- sucursales
    @app.post("/sucursales", status_code=201, response_model=Sucursal, tags=["sucursales"])
    def crear_sucursal(
        datos: SucursalIn, _: Usuario = Depends(solo_admin), i: Inventario = Depends(inv)
    ):
        return i.crear_sucursal(datos.codigo, datos.nombre, datos.direccion)

    @app.get("/sucursales", response_model=list[Sucursal], tags=["sucursales"])
    def listar_sucursales(_: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        return list(i.sucursales.values())

    # ----------------------------------------------------------------- productos
    @app.post("/productos", status_code=201, response_model=Producto, tags=["productos"])
    def crear_producto(
        datos: ProductoIn, _: Usuario = Depends(solo_admin), i: Inventario = Depends(inv)
    ):
        return i.crear_producto(**datos.model_dump())

    @app.get("/productos", tags=["productos"], summary="Buscar (costo solo para admin)")
    def listar_productos(
        q: str = "",
        categoria: Optional[str] = None,
        u: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        datos = [p.model_dump(mode="json") for p in i.buscar_productos(q, categoria)]
        return datos if u.rol == "admin" else [_sin_costos(d) for d in datos]

    @app.get("/productos/{producto_id}", tags=["productos"])
    def detalle_producto(
        producto_id: int, u: Usuario = Depends(actual), i: Inventario = Depends(inv)
    ):
        prod = i.obtener_producto(producto_id)
        detalle = {
            **prod.model_dump(mode="json"),
            "margen": str(prod.margen),
            "variantes": [
                {
                    **v.model_dump(),
                    "stock_total": i.stock_total(v.id),
                    "en_transito": i.en_transito(v.id),
                }
                for v in i.variantes_de(producto_id)
            ],
        }
        return detalle if u.rol == "admin" else _sin_costos(detalle)

    # ----------------------------------------------------------------- variantes
    @app.post(
        "/productos/{producto_id}/variantes",
        status_code=201,
        response_model=Variante,
        tags=["variantes"],
    )
    def crear_variante(
        producto_id: int,
        datos: VarianteIn,
        _: Usuario = Depends(solo_admin),
        i: Inventario = Depends(inv),
    ):
        return i.agregar_variante(producto_id, datos.talla, datos.color, datos.stock_minimo)

    @app.post(
        "/productos/{producto_id}/variantes/matriz",
        status_code=201,
        response_model=list[Variante],
        tags=["variantes"],
        summary="Crear todas las combinaciones talla × color",
    )
    def crear_matriz(
        producto_id: int,
        datos: MatrizIn,
        _: Usuario = Depends(solo_admin),
        i: Inventario = Depends(inv),
    ):
        return i.generar_matriz(producto_id, datos.tallas, datos.colores, datos.stock_minimo)

    @app.get("/variantes/sku/{sku}", response_model=Variante, tags=["variantes"])
    def buscar_sku(sku: str, _: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        return i.variante_por_sku(sku)

    # --------------------------------------------------------------------- stock
    def resolver_variante(variante_id: Optional[int], sku: Optional[str], i: Inventario) -> int:
        if variante_id is None and not sku:
            raise HTTPException(422, "Cada ítem necesita variante_id o sku")
        return variante_id if variante_id is not None else i.variante_por_sku(sku).id

    @app.post("/stock/ingresos", status_code=201, response_model=list[Movimiento], tags=["stock"])
    def ingreso(datos: IngresoIn, u: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        de_su_sucursal(u, datos.sucursal_id)
        items = [(resolver_variante(it.variante_id, it.sku, i), it.cantidad) for it in datos.items]
        return i.registrar_ingreso(datos.sucursal_id, items, datos.referencia)

    @app.post("/stock/ajustes", status_code=201, response_model=Movimiento, tags=["stock"])
    def ajuste(datos: AjusteIn, u: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        de_su_sucursal(u, datos.sucursal_id)
        return i.ajustar_stock(datos.variante_id, datos.sucursal_id, datos.cantidad_real, datos.motivo)

    @app.get("/productos/{producto_id}/stock", tags=["stock"], summary="Matriz talla × color")
    def matriz_stock(
        producto_id: int,
        sucursal_id: Optional[int] = None,
        _: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        return i.matriz_stock(producto_id, sucursal_id)

    @app.get("/sucursales/{sucursal_id}/alertas", tags=["stock"], summary="Variantes por reponer")
    def alertas(sucursal_id: int, u: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        de_su_sucursal(u, sucursal_id)
        return i.bajo_minimo(sucursal_id)

    @app.get("/variantes/{variante_id}/kardex", response_model=list[Movimiento], tags=["stock"])
    def kardex(
        variante_id: int,
        sucursal_id: Optional[int] = None,
        u: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        return i.kardex(variante_id, sucursal_visible(u, sucursal_id))

    # ------------------------------------------------------------ transferencias
    @app.post("/transferencias", status_code=201, tags=["transferencias"], summary="Enviar mercadería")
    def enviar(datos: TransferenciaIn, u: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        de_su_sucursal(u, datos.origen_id)
        items = [(resolver_variante(it.variante_id, it.sku, i), it.cantidad) for it in datos.items]
        trf = i.enviar_transferencia(datos.origen_id, datos.destino_id, items, datos.nota)
        return _vista_transferencia(i, trf)

    @app.get("/transferencias", tags=["transferencias"])
    def listar_transferencias(
        sucursal_id: Optional[int] = None,
        estado: Optional[str] = None,
        u: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        sucursal_id = sucursal_visible(u, sucursal_id)
        if estado is not None and estado not in _ESTADOS_TRANSFERENCIA:
            raise HTTPException(422, f"Estado inválido. Use: {', '.join(_ESTADOS_TRANSFERENCIA)}")
        if sucursal_id is not None:
            i.obtener_sucursal(sucursal_id)
        return [_vista_transferencia(i, t) for t in i.listar_transferencias(sucursal_id, estado)]

    @app.get("/transferencias/{transferencia_id}", tags=["transferencias"])
    def detalle_transferencia(
        transferencia_id: int, u: Usuario = Depends(actual), i: Inventario = Depends(inv)
    ):
        trf = i.obtener_transferencia(transferencia_id)
        de_su_sucursal(u, trf.origen_id, trf.destino_id)
        return _vista_transferencia(i, trf)

    @app.post(
        "/transferencias/{transferencia_id}/recepcion",
        tags=["transferencias"],
        summary="Confirmar llegada al destino",
    )
    def recibir(
        transferencia_id: int,
        datos: RecepcionIn,
        u: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        de_su_sucursal(u, i.obtener_transferencia(transferencia_id).destino_id)
        recibidos: dict[int, int] = {}
        for it in datos.items:
            vid = resolver_variante(it.variante_id, it.sku, i)
            recibidos[vid] = recibidos.get(vid, 0) + it.cantidad
        trf = i.recibir_transferencia(transferencia_id, recibidos, datos.observacion)
        return _vista_transferencia(i, trf)

    @app.post("/transferencias/{transferencia_id}/anulacion", tags=["transferencias"])
    def anular(
        transferencia_id: int,
        datos: AnulacionIn,
        u: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        de_su_sucursal(u, i.obtener_transferencia(transferencia_id).origen_id)
        return _vista_transferencia(i, i.anular_transferencia(transferencia_id, datos.motivo))

    # -------------------------------------------------------------------- ventas
    @app.post("/ventas", status_code=201, tags=["ventas"], summary="Registrar venta en caja")
    def vender(datos: VentaIn, u: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        de_su_sucursal(u, datos.sucursal_id)
        items = [
            (resolver_variante(it.variante_id, it.sku, i), it.cantidad, it.descuento_pct)
            for it in datos.items
        ]
        venta = i.registrar_venta(
            datos.sucursal_id,
            items,
            datos.metodo_pago,
            datos.monto_recibido,
            datos.vendedor.strip() or u.nombre,
        )
        return _vista_venta(i, venta)

    @app.get("/ventas", tags=["ventas"])
    def listar_ventas(
        sucursal_id: Optional[int] = None,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        u: Usuario = Depends(actual),
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        ventas = i.listar_ventas(sucursal_visible(u, sucursal_id), inicio, fin)
        return [_vista_venta(i, v) for v in ventas]

    @app.get("/ventas/{venta_id}", tags=["ventas"])
    def detalle_venta(venta_id: int, u: Usuario = Depends(actual), i: Inventario = Depends(inv)):
        venta = i.obtener_venta(venta_id)
        de_su_sucursal(u, venta.sucursal_id)
        return _vista_venta(i, venta)

    @app.post("/ventas/{venta_id}/anulacion", tags=["ventas"], summary="Anular y devolver al stock")
    def anular_venta(
        venta_id: int,
        datos: AnulacionIn,
        _: Usuario = Depends(solo_admin),
        i: Inventario = Depends(inv),
    ):
        return _vista_venta(i, i.anular_venta(venta_id, datos.motivo))

    # ------------------------------------------------------------------ reportes
    @app.get("/reportes/mas-vendidos", tags=["reportes"])
    def mas_vendidos(
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        sucursal_id: Optional[int] = None,
        por: str = "producto",
        limite: int = 10,
        _: Usuario = Depends(solo_admin),
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return reportes.mas_vendidos(i, inicio, fin, sucursal_id, por, limite)

    @app.get("/reportes/ventas-por-talla", tags=["reportes"])
    def ventas_por_talla(
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        _: Usuario = Depends(solo_admin),
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return reportes.ventas_por_talla(i, inicio, fin, categoria)

    @app.get("/reportes/resumen-ventas", tags=["reportes"], summary="Cierre de caja")
    def resumen_ventas(
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        sucursal_id: Optional[int] = None,
        _: Usuario = Depends(solo_admin),
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return reportes.resumen_ventas(i, inicio, fin, sucursal_id)

    @app.get("/reportes/valor-inventario", tags=["reportes"])
    def valor_inventario(_: Usuario = Depends(solo_admin), i: Inventario = Depends(inv)):
        return reportes.valor_inventario(i)

    return app


app = create_app()
