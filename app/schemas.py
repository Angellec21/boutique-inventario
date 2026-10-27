"""Esquemas de entrada de la API (lo que envía el cliente)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class SucursalIn(BaseModel):
    codigo: str = Field(min_length=2, max_length=6, examples=["CEN"])
    nombre: str = Field(min_length=2, examples=["Centro"])
    direccion: str = Field(default="", examples=["Calle 24 de Septiembre #155"])


class ProductoIn(BaseModel):
    codigo: str = Field(min_length=2, max_length=12, examples=["BLU-001"])
    nombre: str = Field(min_length=2, examples=["Blusa de lino manga corta"])
    categoria: str = Field(min_length=2, examples=["Blusas"])
    marca: str = ""
    precio_venta: Decimal = Field(gt=0, examples=["189.00"])
    costo: Decimal = Field(ge=0, examples=["95.00"])


class VarianteIn(BaseModel):
    talla: str = Field(examples=["M"])
    color: str = Field(examples=["Azul marino"])
    stock_minimo: int = Field(default=2, ge=0)


class MatrizIn(BaseModel):
    tallas: list[str] = Field(min_length=1, examples=[["S", "M", "L"]])
    colores: list[str] = Field(min_length=1, examples=[["Negro", "Beige"]])
    stock_minimo: int = Field(default=2, ge=0)


class ItemIngreso(BaseModel):
    variante_id: Optional[int] = None
    sku: Optional[str] = None
    cantidad: int = Field(gt=0)


class IngresoIn(BaseModel):
    sucursal_id: int
    referencia: Optional[str] = Field(default=None, examples=["Pedido proveedor 0045"])
    items: list[ItemIngreso] = Field(min_length=1)


class AjusteIn(BaseModel):
    variante_id: int
    sucursal_id: int
    cantidad_real: int = Field(ge=0)
    motivo: str = Field(min_length=3, examples=["Conteo físico semanal"])


class ItemTransferenciaIn(BaseModel):
    variante_id: Optional[int] = None
    sku: Optional[str] = Field(default=None, examples=["VES-020-ROJ-M"])
    cantidad: int = Field(gt=0)


class TransferenciaIn(BaseModel):
    origen_id: int
    destino_id: int
    nota: str = Field(default="", examples=["Reposición de vitrina para el fin de semana"])
    items: list[ItemTransferenciaIn] = Field(min_length=1)


class ItemRecibidoIn(BaseModel):
    variante_id: Optional[int] = None
    sku: Optional[str] = None
    cantidad: int = Field(ge=0)


class RecepcionIn(BaseModel):
    """Si ``items`` está vacío se asume que llegó todo lo enviado."""

    items: list[ItemRecibidoIn] = Field(default_factory=list)
    observacion: str = Field(default="", examples=["Faltó una prenda en la bolsa"])


class AnulacionIn(BaseModel):
    motivo: str = Field(min_length=3, examples=["El envío no salió de la tienda"])


class ItemVentaIn(BaseModel):
    variante_id: Optional[int] = None
    sku: Optional[str] = Field(default=None, examples=["BLU-001-BEI-M"])
    cantidad: int = Field(gt=0, examples=[1])
    descuento_pct: Decimal = Field(default=Decimal("0"), ge=0, le=50, examples=["10"])


class VentaIn(BaseModel):
    sucursal_id: int
    metodo_pago: str = Field(default="efectivo", examples=["efectivo"])
    monto_recibido: Optional[Decimal] = Field(default=None, ge=0, examples=["200.00"])
    vendedor: str = Field(default="", examples=["Carla"])
    items: list[ItemVentaIn] = Field(min_length=1)


class LoginIn(BaseModel):
    usuario: str = Field(min_length=1, examples=["admin"])
    clave: str = Field(min_length=1, examples=["Boutique2026"])


class UsuarioIn(BaseModel):
    usuario: str = Field(examples=["carla.v"])
    nombre: str = Field(min_length=2, examples=["Carla Vaca"])
    clave: str = Field(min_length=8, examples=["Equipetrol2026"])
    rol: str = Field(default="encargado", examples=["encargado"])
    sucursal_id: Optional[int] = Field(default=None, examples=[2])


class CambioClaveIn(BaseModel):
    actual: str
    nueva: str = Field(min_length=8)


class RestablecerClaveIn(BaseModel):
    nueva: str = Field(min_length=8)
