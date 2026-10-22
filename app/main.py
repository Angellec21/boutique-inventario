"""API REST del inventario de la boutique (FastAPI).

Ejecutar en desarrollo:  ``uvicorn app.main:app --reload``
Documentación interactiva: http://localhost:8000/docs
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .inventario import (
    Conflicto,
    ErrorInventario,
    Inventario,
    NoEncontrado,
    StockInsuficiente,
)
from .models import Movimiento, Producto, Sucursal, Variante
from .schemas import AjusteIn, IngresoIn, MatrizIn, ProductoIn, SucursalIn, VarianteIn

_ESTADOS = {NoEncontrado: 404, Conflicto: 409, StockInsuficiente: 409}


def create_app(inventario: Optional[Inventario] = None) -> FastAPI:
    app = FastAPI(
        title="Boutique Inventario",
        description="Inventario para tiendas de ropa: tallas, colores y sucursales. Montos en Bs.",
        version="0.1.0",
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
                {**v.model_dump(), "stock_total": i.stock_total(v.id)}
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
    @app.post("/stock/ingresos", status_code=201, response_model=list[Movimiento], tags=["stock"])
    def ingreso(datos: IngresoIn, i: Inventario = Depends(inv)):
        items = []
        for it in datos.items:
            if it.variante_id is None and not it.sku:
                raise HTTPException(422, "Cada ítem necesita variante_id o sku")
            vid = it.variante_id if it.variante_id is not None else i.variante_por_sku(it.sku).id
            items.append((vid, it.cantidad))
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

    return app


app = create_app()
