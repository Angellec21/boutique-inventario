"""API REST del inventario de la boutique (FastAPI).

Ejecutar en desarrollo:  ``uvicorn app.main:app --reload``
Documentación interactiva: http://localhost:8000/docs
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

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
    IngresoIn,
    MatrizIn,
    ProductoIn,
    RecepcionIn,
    SucursalIn,
    TransferenciaIn,
    VarianteIn,
    VentaIn,
)

_ESTADOS = {NoEncontrado: 404, Conflicto: 409, StockInsuficiente: 409}
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


def create_app(inventario: Optional[Inventario] = None) -> FastAPI:
    app = FastAPI(
        title="Boutique Inventario",
        description="Inventario para tiendas de ropa: tallas, colores y sucursales. Montos en Bs.",
        version="0.2.0",
    )
    app.state.inventario = inventario or Inventario()

    @app.exception_handler(ErrorInventario)
    async def _errores_de_negocio(_: Request, exc: ErrorInventario):
        return JSONResponse(status_code=_ESTADOS.get(type(exc), 422), content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _valores_invalidos(_: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def inv(request: Request) -> Inventario:
        return request.app.state.inventario

    @app.get("/salud", tags=["sistema"])
    def salud():
        return {"estado": "ok"}

    # ---------------------------------------------------------------- sucursales
    @app.post("/sucursales", status_code=201, response_model=Sucursal, tags=["sucursales"])
    def crear_sucursal(datos: SucursalIn, i: Inventario = Depends(inv)):
        return i.crear_sucursal(datos.codigo, datos.nombre, datos.direccion)

    @app.get("/sucursales", response_model=list[Sucursal], tags=["sucursales"])
    def listar_sucursales(i: Inventario = Depends(inv)):
        return list(i.sucursales.values())

    # ----------------------------------------------------------------- productos
    @app.post("/productos", status_code=201, response_model=Producto, tags=["productos"])
    def crear_producto(datos: ProductoIn, i: Inventario = Depends(inv)):
        return i.crear_producto(**datos.model_dump())

    @app.get("/productos", response_model=list[Producto], tags=["productos"])
    def listar_productos(
        q: str = "", categoria: Optional[str] = None, i: Inventario = Depends(inv)
    ):
        return i.buscar_productos(q, categoria)

    @app.get("/productos/{producto_id}", tags=["productos"])
    def detalle_producto(producto_id: int, i: Inventario = Depends(inv)):
        prod = i.obtener_producto(producto_id)
        return {
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

    # ----------------------------------------------------------------- variantes
    @app.post(
        "/productos/{producto_id}/variantes",
        status_code=201,
        response_model=Variante,
        tags=["variantes"],
    )
    def crear_variante(producto_id: int, datos: VarianteIn, i: Inventario = Depends(inv)):
        return i.agregar_variante(producto_id, datos.talla, datos.color, datos.stock_minimo)

    @app.post(
        "/productos/{producto_id}/variantes/matriz",
        status_code=201,
        response_model=list[Variante],
        tags=["variantes"],
        summary="Crear todas las combinaciones talla × color",
    )
    def crear_matriz(producto_id: int, datos: MatrizIn, i: Inventario = Depends(inv)):
        return i.generar_matriz(producto_id, datos.tallas, datos.colores, datos.stock_minimo)

    @app.get("/variantes/sku/{sku}", response_model=Variante, tags=["variantes"])
    def buscar_sku(sku: str, i: Inventario = Depends(inv)):
        return i.variante_por_sku(sku)

    # --------------------------------------------------------------------- stock
    def resolver_variante(variante_id: Optional[int], sku: Optional[str], i: Inventario) -> int:
        if variante_id is None and not sku:
            raise HTTPException(422, "Cada ítem necesita variante_id o sku")
        return variante_id if variante_id is not None else i.variante_por_sku(sku).id

    @app.post("/stock/ingresos", status_code=201, response_model=list[Movimiento], tags=["stock"])
    def ingreso(datos: IngresoIn, i: Inventario = Depends(inv)):
        items = [(resolver_variante(it.variante_id, it.sku, i), it.cantidad) for it in datos.items]
        return i.registrar_ingreso(datos.sucursal_id, items, datos.referencia)

    @app.post("/stock/ajustes", status_code=201, response_model=Movimiento, tags=["stock"])
    def ajuste(datos: AjusteIn, i: Inventario = Depends(inv)):
        return i.ajustar_stock(datos.variante_id, datos.sucursal_id, datos.cantidad_real, datos.motivo)

    @app.get("/productos/{producto_id}/stock", tags=["stock"], summary="Matriz talla × color")
    def matriz_stock(
        producto_id: int, sucursal_id: Optional[int] = None, i: Inventario = Depends(inv)
    ):
        return i.matriz_stock(producto_id, sucursal_id)

    @app.get("/sucursales/{sucursal_id}/alertas", tags=["stock"], summary="Variantes por reponer")
    def alertas(sucursal_id: int, i: Inventario = Depends(inv)):
        return i.bajo_minimo(sucursal_id)

    @app.get("/variantes/{variante_id}/kardex", response_model=list[Movimiento], tags=["stock"])
    def kardex(variante_id: int, sucursal_id: Optional[int] = None, i: Inventario = Depends(inv)):
        return i.kardex(variante_id, sucursal_id)

    # ------------------------------------------------------------ transferencias
    @app.post("/transferencias", status_code=201, tags=["transferencias"], summary="Enviar mercadería")
    def enviar(datos: TransferenciaIn, i: Inventario = Depends(inv)):
        items = [(resolver_variante(it.variante_id, it.sku, i), it.cantidad) for it in datos.items]
        trf = i.enviar_transferencia(datos.origen_id, datos.destino_id, items, datos.nota)
        return _vista_transferencia(i, trf)

    @app.get("/transferencias", tags=["transferencias"])
    def listar_transferencias(
        sucursal_id: Optional[int] = None,
        estado: Optional[str] = None,
        i: Inventario = Depends(inv),
    ):
        if estado is not None and estado not in _ESTADOS_TRANSFERENCIA:
            raise HTTPException(422, f"Estado inválido. Use: {', '.join(_ESTADOS_TRANSFERENCIA)}")
        if sucursal_id is not None:
            i.obtener_sucursal(sucursal_id)
        return [_vista_transferencia(i, t) for t in i.listar_transferencias(sucursal_id, estado)]

    @app.get("/transferencias/{transferencia_id}", tags=["transferencias"])
    def detalle_transferencia(transferencia_id: int, i: Inventario = Depends(inv)):
        return _vista_transferencia(i, i.obtener_transferencia(transferencia_id))

    @app.post(
        "/transferencias/{transferencia_id}/recepcion",
        tags=["transferencias"],
        summary="Confirmar llegada al destino",
    )
    def recibir(transferencia_id: int, datos: RecepcionIn, i: Inventario = Depends(inv)):
        recibidos: dict[int, int] = {}
        for it in datos.items:
            vid = resolver_variante(it.variante_id, it.sku, i)
            recibidos[vid] = recibidos.get(vid, 0) + it.cantidad
        trf = i.recibir_transferencia(transferencia_id, recibidos, datos.observacion)
        return _vista_transferencia(i, trf)

    @app.post("/transferencias/{transferencia_id}/anulacion", tags=["transferencias"])
    def anular(transferencia_id: int, datos: AnulacionIn, i: Inventario = Depends(inv)):
        return _vista_transferencia(i, i.anular_transferencia(transferencia_id, datos.motivo))

    # -------------------------------------------------------------------- ventas
    @app.post("/ventas", status_code=201, tags=["ventas"], summary="Registrar venta en caja")
    def vender(datos: VentaIn, i: Inventario = Depends(inv)):
        items = [
            (resolver_variante(it.variante_id, it.sku, i), it.cantidad, it.descuento_pct)
            for it in datos.items
        ]
        venta = i.registrar_venta(
            datos.sucursal_id, items, datos.metodo_pago, datos.monto_recibido, datos.vendedor
        )
        return _vista_venta(i, venta)

    @app.get("/ventas", tags=["ventas"])
    def listar_ventas(
        sucursal_id: Optional[int] = None,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return [_vista_venta(i, v) for v in i.listar_ventas(sucursal_id, inicio, fin)]

    @app.get("/ventas/{venta_id}", tags=["ventas"])
    def detalle_venta(venta_id: int, i: Inventario = Depends(inv)):
        return _vista_venta(i, i.obtener_venta(venta_id))

    @app.post("/ventas/{venta_id}/anulacion", tags=["ventas"], summary="Anular y devolver al stock")
    def anular_venta(venta_id: int, datos: AnulacionIn, i: Inventario = Depends(inv)):
        return _vista_venta(i, i.anular_venta(venta_id, datos.motivo))

    # ------------------------------------------------------------------ reportes
    @app.get("/reportes/mas-vendidos", tags=["reportes"])
    def mas_vendidos(
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        sucursal_id: Optional[int] = None,
        por: str = "producto",
        limite: int = 10,
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return reportes.mas_vendidos(i, inicio, fin, sucursal_id, por, limite)

    @app.get("/reportes/ventas-por-talla", tags=["reportes"])
    def ventas_por_talla(
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return reportes.ventas_por_talla(i, inicio, fin, categoria)

    @app.get("/reportes/resumen-ventas", tags=["reportes"], summary="Cierre de caja")
    def resumen_ventas(
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        sucursal_id: Optional[int] = None,
        i: Inventario = Depends(inv),
    ):
        inicio, fin = _rango(desde, hasta)
        return reportes.resumen_ventas(i, inicio, fin, sucursal_id)

    @app.get("/reportes/valor-inventario", tags=["reportes"])
    def valor_inventario(i: Inventario = Depends(inv)):
        return reportes.valor_inventario(i)

    return app


app = create_app()
