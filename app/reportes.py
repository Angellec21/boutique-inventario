"""Reportes para el dueño de la boutique.

Funciones puras sobre ``Inventario``: solo leen datos, nunca modifican stock.
Las ventas anuladas no cuentan en ningún reporte.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .inventario import ErrorInventario, Inventario, _ordenar_tallas

CERO = Decimal("0.00")


def _margen_pct(importe: Decimal, costo: Decimal) -> str:
    if importe == 0:
        return "0.0"
    return str(((importe - costo) / importe * 100).quantize(Decimal("0.1")))


def mas_vendidos(
    inv: Inventario,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    sucursal_id: Optional[int] = None,
    por: str = "producto",
    limite: int = 10,
) -> list[dict]:
    """Ranking por unidades vendidas (desempate por importe), por producto o por variante (SKU)."""
    if por not in ("producto", "variante"):
        raise ErrorInventario("Agrupe por 'producto' o 'variante'")
    if sucursal_id is not None:
        inv.obtener_sucursal(sucursal_id)
    acum: dict[int, dict] = {}
    for venta in inv.listar_ventas(sucursal_id, desde, hasta, incluir_anuladas=False):
        for item in venta.items:
            var = inv.variantes[item.variante_id]
            prod = inv.productos[var.producto_id]
            clave = prod.id if por == "producto" else var.id
            fila = acum.setdefault(
                clave,
                {
                    "codigo": prod.codigo if por == "producto" else var.sku,
                    "producto": prod.nombre,
                    "categoria": prod.categoria,
                    **({"talla": var.talla, "color": var.color} if por == "variante" else {}),
                    "unidades": 0,
                    "importe": CERO,
                    "costo": CERO,
                },
            )
            fila["unidades"] += item.cantidad
            fila["importe"] += item.subtotal
            fila["costo"] += item.costo_total
    filas = sorted(acum.values(), key=lambda f: (-f["unidades"], -f["importe"], f["codigo"]))
    resultado = []
    for pos, f in enumerate(filas[: max(limite, 0)], start=1):
        importe, costo = f.pop("importe"), f.pop("costo")
        resultado.append(
            {
                "posicion": pos,
                **f,
                "importe": str(importe),
                "margen": str(importe - costo),
                "margen_pct": _margen_pct(importe, costo),
            }
        )
    return resultado


def ventas_por_talla(
    inv: Inventario,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    categoria: Optional[str] = None,
) -> list[dict]:
    """Unidades vendidas por talla y su participación: ayuda a decidir la curva de tallas al comprar."""
    unidades: dict[str, int] = defaultdict(int)
    for venta in inv.listar_ventas(None, desde, hasta, incluir_anuladas=False):
        for item in venta.items:
            var = inv.variantes[item.variante_id]
            if categoria and inv.productos[var.producto_id].categoria.lower() != categoria.lower():
                continue
            unidades[var.talla] += item.cantidad
    total = sum(unidades.values())
    return [
        {
            "talla": t,
            "unidades": unidades[t],
            "participacion_pct": str((Decimal(unidades[t]) / total * 100).quantize(Decimal("0.1"))),
        }
        for t in _ordenar_tallas(set(unidades))
    ]


def resumen_ventas(
    inv: Inventario,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    sucursal_id: Optional[int] = None,
) -> dict:
    """Cierre de caja: totales, ticket promedio, margen y desglose por método de pago y vendedor."""
    if sucursal_id is not None:
        inv.obtener_sucursal(sucursal_id)
    todas = inv.listar_ventas(sucursal_id, desde, hasta)
    validas = [v for v in todas if v.estado == "completada"]
    total = sum((v.total for v in validas), CERO)
    costo = sum((i.costo_total for v in validas for i in v.items), CERO)
    por_metodo: dict[str, Decimal] = defaultdict(lambda: CERO)
    por_vendedor: dict[str, Decimal] = defaultdict(lambda: CERO)
    for v in validas:
        por_metodo[v.metodo_pago] += v.total
        por_vendedor[v.vendedor or "Sin asignar"] += v.total
    return {
        "sucursal_id": sucursal_id,
        "cantidad_ventas": len(validas),
        "ventas_anuladas": len(todas) - len(validas),
        "unidades": sum(v.unidades for v in validas),
        "total": str(total),
        "descuentos": str(sum((v.descuento_total for v in validas), CERO)),
        "ticket_promedio": str((total / len(validas)).quantize(Decimal("0.01")) if validas else CERO),
        "margen": str(total - costo),
        "margen_pct": _margen_pct(total, costo),
        "por_metodo_pago": {m: str(t) for m, t in sorted(por_metodo.items())},
        "por_vendedor": {n: str(t) for n, t in sorted(por_vendedor.items(), key=lambda x: -x[1])},
    }


def valor_inventario(inv: Inventario) -> list[dict]:
    """Mercadería en cada sucursal valorizada a costo y a precio de venta (sin lo que está en tránsito)."""
    filas = []
    for suc in inv.sucursales.values():
        unidades, a_costo, a_venta = 0, CERO, CERO
        for var in inv.variantes.values():
            cant = inv.stock(var.id, suc.id)
            if cant:
                prod = inv.productos[var.producto_id]
                unidades += cant
                a_costo += prod.costo * cant
                a_venta += prod.precio_venta * cant
        filas.append(
            {
                "sucursal_id": suc.id,
                "sucursal": suc.nombre,
                "unidades": unidades,
                "valor_costo": str(a_costo),
                "valor_venta": str(a_venta),
                "ganancia_potencial": str(a_venta - a_costo),
            }
        )
    return filas
