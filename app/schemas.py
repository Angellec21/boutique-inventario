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
