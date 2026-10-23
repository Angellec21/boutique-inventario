"""Modelos de dominio del inventario de la boutique.

Todos los montos están en bolivianos (Bs) y se manejan con ``Decimal``
para evitar errores de redondeo en precios y totales.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

TALLAS_LETRA = ("XS", "S", "M", "L", "XL", "XXL")


def normalizar_talla(valor: str) -> str:
    """Normaliza una talla: letras en mayúscula (``m`` → ``M``) o número de jean/calzado."""
    talla = valor.strip().upper()
    if not talla:
        raise ValueError("La talla no puede estar vacía")
    if talla in TALLAS_LETRA or talla == "UNICA":
        return talla
    if talla.isdigit() and 2 <= int(talla) <= 60:
        return talla
    raise ValueError(
        f"Talla inválida: {valor!r}. Use XS–XXL, UNICA o un número (p. ej. 32 para jeans)"
    )


def normalizar_color(valor: str) -> str:
    color = " ".join(valor.strip().split()).capitalize()
    if not color:
        raise ValueError("El color no puede estar vacío")
    return color


class Sucursal(BaseModel):
    id: int
    codigo: str = Field(min_length=2, max_length=6)
    nombre: str = Field(min_length=2)
    direccion: str = ""


class Producto(BaseModel):
    """Modelo de prenda (p. ej. «Blusa de lino manga corta»). Las tallas y colores van en variantes."""

    id: int
    codigo: str = Field(min_length=2, max_length=12)
    nombre: str = Field(min_length=2)
    categoria: str = Field(min_length=2)
    marca: str = ""
    precio_venta: Decimal = Field(gt=0, decimal_places=2)
    costo: Decimal = Field(ge=0, decimal_places=2)
    activo: bool = True

    @property
    def margen(self) -> Decimal:
        return self.precio_venta - self.costo


class Variante(BaseModel):
    """Combinación talla + color de un producto, identificada por su SKU."""

    id: int
    producto_id: int
    talla: str
    color: str
    sku: str
    stock_minimo: int = Field(default=2, ge=0)

    @field_validator("talla")
    @classmethod
    def _talla(cls, v: str) -> str:
        return normalizar_talla(v)

    @field_validator("color")
    @classmethod
    def _color(cls, v: str) -> str:
        return normalizar_color(v)


class Movimiento(BaseModel):
    """Registro de cada cambio de stock (kardex): quién, cuándo, cuánto y por qué."""

    id: int
    variante_id: int
    sucursal_id: int
    tipo: str  # ingreso | ajuste | transferencia_salida | transferencia_entrada
    cantidad: int  # positiva entra, negativa sale
    saldo: int
    motivo: str = ""
    referencia: Optional[str] = None


class ItemTransferencia(BaseModel):
    variante_id: int
    sku: str
    enviado: int = Field(gt=0)
    recibido: Optional[int] = None

    @property
    def faltante(self) -> int:
        return 0 if self.recibido is None else self.enviado - self.recibido


class Transferencia(BaseModel):
    """Traspaso de mercadería entre sucursales.

    Ciclo de vida: ``en_transito`` → ``recibida`` (o ``recibida_con_diferencias``
    si llegó menos de lo enviado) o ``anulada`` (el stock vuelve al origen).
    """

    id: int
    codigo: str
    origen_id: int
    destino_id: int
    estado: str = "en_transito"
    items: list[ItemTransferencia]
    nota: str = ""
    observacion_recepcion: str = ""

    @property
    def unidades_enviadas(self) -> int:
        return sum(i.enviado for i in self.items)

    @property
    def unidades_faltantes(self) -> int:
        return sum(i.faltante for i in self.items)
