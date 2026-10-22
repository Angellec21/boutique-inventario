"""Servicio de inventario: catálogo, variantes por talla/color y stock por sucursal.

Los datos viven en memoria; la capa de persistencia se agrega más adelante
sin cambiar esta interfaz.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Optional

from .models import (
    TALLAS_LETRA,
    Movimiento,
    Producto,
    Sucursal,
    Variante,
    normalizar_color,
    normalizar_talla,
)


class ErrorInventario(Exception):
    """Error de negocio genérico."""


class NoEncontrado(ErrorInventario):
    pass


class Conflicto(ErrorInventario):
    pass


class StockInsuficiente(ErrorInventario):
    pass


def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def generar_sku(codigo_producto: str, color: str, talla: str) -> str:
    """``BLU-001`` + ``Azul marino`` + ``M`` → ``BLU-001-AZM-M``."""
    palabras = _sin_tildes(color).upper().split()
    if len(palabras) == 1:
        abrev = palabras[0][:3]
    else:
        abrev = palabras[0][:2] + "".join(p[0] for p in palabras[1:])
    return f"{codigo_producto.upper()}-{abrev[:3]}-{talla}"


class Inventario:
    def __init__(self) -> None:
        self.sucursales: dict[int, Sucursal] = {}
        self.productos: dict[int, Producto] = {}
        self.variantes: dict[int, Variante] = {}
        self.movimientos: list[Movimiento] = []
        # (variante_id, sucursal_id) -> cantidad
        self._stock: dict[tuple[int, int], int] = defaultdict(int)
        self._seq: dict[str, int] = defaultdict(int)

    def _siguiente_id(self, entidad: str) -> int:
        self._seq[entidad] += 1
        return self._seq[entidad]

    # ---------------------------------------------------------------- sucursales
    def crear_sucursal(self, codigo: str, nombre: str, direccion: str = "") -> Sucursal:
        codigo = codigo.strip().upper()
        if any(s.codigo == codigo for s in self.sucursales.values()):
            raise Conflicto(f"Ya existe una sucursal con código {codigo}")
        suc = Sucursal(
            id=self._siguiente_id("sucursal"), codigo=codigo, nombre=nombre, direccion=direccion
        )
        self.sucursales[suc.id] = suc
        return suc

    def obtener_sucursal(self, sucursal_id: int) -> Sucursal:
        try:
            return self.sucursales[sucursal_id]
        except KeyError:
            raise NoEncontrado(f"Sucursal {sucursal_id} no existe") from None

    # ----------------------------------------------------------------- productos
    def crear_producto(
        self,
        codigo: str,
        nombre: str,
        categoria: str,
        precio_venta: Decimal | str | float,
        costo: Decimal | str | float,
        marca: str = "",
    ) -> Producto:
        codigo = codigo.strip().upper()
        if any(p.codigo == codigo for p in self.productos.values()):
            raise Conflicto(f"Ya existe un producto con código {codigo}")
        precio = Decimal(str(precio_venta)).quantize(Decimal("0.01"))
        costo_d = Decimal(str(costo)).quantize(Decimal("0.01"))
        if costo_d > precio:
            raise ErrorInventario("El costo no puede ser mayor al precio de venta")
        prod = Producto(
            id=self._siguiente_id("producto"),
            codigo=codigo,
            nombre=nombre.strip(),
            categoria=categoria.strip().capitalize(),
            marca=marca.strip(),
            precio_venta=precio,
            costo=costo_d,
        )
        self.productos[prod.id] = prod
        return prod

    def obtener_producto(self, producto_id: int) -> Producto:
        try:
            return self.productos[producto_id]
        except KeyError:
            raise NoEncontrado(f"Producto {producto_id} no existe") from None

    def buscar_productos(
        self, texto: str = "", categoria: Optional[str] = None
    ) -> list[Producto]:
        texto_n = _sin_tildes(texto).lower()
        res = []
        for p in self.productos.values():
            if categoria and p.categoria.lower() != categoria.lower():
                continue
            if texto_n and texto_n not in _sin_tildes(f"{p.codigo} {p.nombre} {p.marca}").lower():
                continue
            res.append(p)
        return res

    # ----------------------------------------------------------------- variantes
    def agregar_variante(
        self, producto_id: int, talla: str, color: str, stock_minimo: int = 2
    ) -> Variante:
        prod = self.obtener_producto(producto_id)
        talla_n, color_n = normalizar_talla(talla), normalizar_color(color)
        for v in self.variantes_de(producto_id):
            if v.talla == talla_n and v.color == color_n:
                raise Conflicto(f"{prod.codigo} ya tiene la variante {color_n} talla {talla_n}")
        sku = generar_sku(prod.codigo, color_n, talla_n)
        if any(v.sku == sku for v in self.variantes.values()):
            raise Conflicto(f"El SKU {sku} ya está en uso; use otro nombre de color")
        var = Variante(
            id=self._siguiente_id("variante"),
            producto_id=producto_id,
            talla=talla_n,
            color=color_n,
            sku=sku,
            stock_minimo=stock_minimo,
        )
        self.variantes[var.id] = var
        return var

    def generar_matriz(
        self,
        producto_id: int,
        tallas: Iterable[str],
        colores: Iterable[str],
        stock_minimo: int = 2,
    ) -> list[Variante]:
        """Crea todas las combinaciones talla × color que falten (las existentes se omiten)."""
        self.obtener_producto(producto_id)
        existentes = {(v.talla, v.color) for v in self.variantes_de(producto_id)}
        creadas = []
        for color in colores:
            for talla in tallas:
                if (normalizar_talla(talla), normalizar_color(color)) in existentes:
                    continue
                creadas.append(self.agregar_variante(producto_id, talla, color, stock_minimo))
        return creadas

    def obtener_variante(self, variante_id: int) -> Variante:
        try:
            return self.variantes[variante_id]
        except KeyError:
            raise NoEncontrado(f"Variante {variante_id} no existe") from None

    def variante_por_sku(self, sku: str) -> Variante:
        sku = sku.strip().upper()
        for v in self.variantes.values():
            if v.sku == sku:
                return v
        raise NoEncontrado(f"SKU {sku} no existe")

    def variantes_de(self, producto_id: int) -> list[Variante]:
        return [v for v in self.variantes.values() if v.producto_id == producto_id]

    # --------------------------------------------------------------------- stock
    def stock(self, variante_id: int, sucursal_id: int) -> int:
        return self._stock.get((variante_id, sucursal_id), 0)

    def stock_total(self, variante_id: int) -> int:
        return sum(c for (v, _), c in self._stock.items() if v == variante_id)

    def _mover(
        self,
        variante_id: int,
        sucursal_id: int,
        cantidad: int,
        tipo: str,
        motivo: str = "",
        referencia: Optional[str] = None,
    ) -> Movimiento:
        self.obtener_variante(variante_id)
        self.obtener_sucursal(sucursal_id)
        actual = self.stock(variante_id, sucursal_id)
        if actual + cantidad < 0:
            var = self.variantes[variante_id]
            raise StockInsuficiente(
                f"Stock insuficiente de {var.sku} en sucursal {sucursal_id}: "
                f"hay {actual}, se pidió {-cantidad}"
            )
        self._stock[(variante_id, sucursal_id)] = actual + cantidad
        mov = Movimiento(
            id=self._siguiente_id("movimiento"),
            variante_id=variante_id,
            sucursal_id=sucursal_id,
            tipo=tipo,
            cantidad=cantidad,
            saldo=actual + cantidad,
            motivo=motivo,
            referencia=referencia,
        )
        self.movimientos.append(mov)
        return mov

    def registrar_ingreso(
        self,
        sucursal_id: int,
        items: list[tuple[int, int]],
        referencia: Optional[str] = None,
    ) -> list[Movimiento]:
        """Ingreso de mercadería (p. ej. llegada de un pedido). Todo o nada."""
        self.obtener_sucursal(sucursal_id)
        if not items:
            raise ErrorInventario("El ingreso no tiene ítems")
        for variante_id, cantidad in items:
            self.obtener_variante(variante_id)
            if cantidad <= 0:
                raise ErrorInventario("Las cantidades de ingreso deben ser positivas")
        return [
            self._mover(v, sucursal_id, c, "ingreso", "Ingreso de mercadería", referencia)
            for v, c in items
        ]

    def ajustar_stock(
        self, variante_id: int, sucursal_id: int, cantidad_real: int, motivo: str
    ) -> Movimiento:
        """Ajuste por conteo físico: deja el stock en ``cantidad_real`` y guarda la diferencia."""
        if cantidad_real < 0:
            raise ErrorInventario("La cantidad contada no puede ser negativa")
        if not motivo.strip():
            raise ErrorInventario("Todo ajuste necesita un motivo (p. ej. «conteo físico»)")
        diferencia = cantidad_real - self.stock(variante_id, sucursal_id)
        return self._mover(variante_id, sucursal_id, diferencia, "ajuste", motivo.strip())

    def matriz_stock(self, producto_id: int, sucursal_id: Optional[int] = None) -> dict:
        """Tabla talla × color del producto (en una sucursal o sumando todas)."""
        prod = self.obtener_producto(producto_id)
        if sucursal_id is not None:
            self.obtener_sucursal(sucursal_id)
        variantes = self.variantes_de(producto_id)
        tallas = _ordenar_tallas({v.talla for v in variantes})
        colores = sorted({v.color for v in variantes})
        celdas: dict[str, dict[str, Optional[int]]] = {
            c: {t: None for t in tallas} for c in colores
        }
        total = 0
        for v in variantes:
            cant = (
                self.stock(v.id, sucursal_id) if sucursal_id is not None else self.stock_total(v.id)
            )
            celdas[v.color][v.talla] = cant
            total += cant
        return {
            "producto_id": prod.id,
            "codigo": prod.codigo,
            "sucursal_id": sucursal_id,
            "tallas": tallas,
            "colores": colores,
            "celdas": celdas,
            "total_unidades": total,
            "valor_venta": str(prod.precio_venta * total),
        }

    def bajo_minimo(self, sucursal_id: int) -> list[dict]:
        """Variantes cuyo stock en la sucursal está en o por debajo de su mínimo (para reponer)."""
        suc = self.obtener_sucursal(sucursal_id)
        alertas = []
        for v in self.variantes.values():
            prod = self.productos[v.producto_id]
            if not prod.activo:
                continue
            cant = self.stock(v.id, suc.id)
            if cant <= v.stock_minimo:
                alertas.append(
                    {
                        "sku": v.sku,
                        "producto": prod.nombre,
                        "talla": v.talla,
                        "color": v.color,
                        "stock": cant,
                        "stock_minimo": v.stock_minimo,
                        "faltante": v.stock_minimo - cant + 1,
                        "en_otras_sucursales": self.stock_total(v.id) - cant,
                    }
                )
        alertas.sort(key=lambda a: (a["stock"], a["sku"]))
        return alertas

    def kardex(self, variante_id: int, sucursal_id: Optional[int] = None) -> list[Movimiento]:
        self.obtener_variante(variante_id)
        return [
            m
            for m in self.movimientos
            if m.variante_id == variante_id and (sucursal_id is None or m.sucursal_id == sucursal_id)
        ]


TALLAS_LETRA_ORDEN = {t: i for i, t in enumerate((*TALLAS_LETRA, "UNICA"))}


def _ordenar_tallas(tallas: set[str]) -> list[str]:
    def clave(t: str):
        if t in TALLAS_LETRA_ORDEN:
            return (0, TALLAS_LETRA_ORDEN[t])
        if t.isdigit():
            return (1, int(t))
        return (2, 0)

    return sorted(tallas, key=clave)

