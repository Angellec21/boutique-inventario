"""Datos de ejemplo: una boutique de Santa Cruz de la Sierra con tres tiendas.

Sirve para probar el sistema o mostrarlo a un cliente sin cargar todo a mano::

    python -m app.datos_ejemplo                 # escribe data/boutique.json
    python -m app.datos_ejemplo --forzar        # reemplaza un archivo existente
    python -m app.datos_ejemplo --archivo otro.json --dias 30

Genera catálogo, stock inicial, una transferencia, dos semanas de ventas (con
descuentos, pagos en efectivo/QR/tarjeta y una anulación) y tres usuarios de
demostración. Las ventas usan una semilla fija: siempre salen los mismos datos.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Optional

from .inventario import Inventario, StockInsuficiente
from .persistencia import Almacen
from .usuarios import RegistroUsuarios

SUCURSALES = [
    ("CEN", "Centro", "Calle 21 de Mayo #248, casi Junín"),
    ("EQP", "Equipetrol", "Av. San Martín #1150, 3er anillo"),
    ("VEN", "Ventura Mall", "Av. San Martín y 4to anillo, local 214"),
]

# código, nombre, categoría, marca, precio Bs, costo Bs, tallas, colores
CATALOGO = [
    ("BLU-001", "Blusa de lino manga corta", "Blusas", "Flor de Patujú", 189, 95,
     ["S", "M", "L"], ["Beige", "Blanco", "Verde oliva"]),
    ("BLU-002", "Blusa de gasa estampada", "Blusas", "Flor de Patujú", 165, 80,
     ["S", "M", "L"], ["Coral", "Negro"]),
    ("JEA-010", "Jean skinny tiro alto", "Jeans", "Urbana", 260, 130,
     ["26", "28", "30", "32"], ["Azul", "Negro"]),
    ("JEA-011", "Jean mom fit", "Jeans", "Urbana", 280, 140,
     ["26", "28", "30", "32"], ["Celeste"]),
    ("VES-020", "Vestido de tirantes", "Vestidos", "Tropical", 320, 150,
     ["S", "M", "L"], ["Rojo", "Verde agua"]),
    ("POL-030", "Polera básica algodón", "Poleras", "Básicos SC", 79, 35,
     ["S", "M", "L", "XL"], ["Blanco", "Negro", "Gris"]),
    ("SHO-040", "Short de jean", "Shorts", "Urbana", 149, 70,
     ["26", "28", "30"], ["Azul"]),
    ("CHA-050", "Chamarra de cuero sintético", "Chamarras", "Andina", 450, 230,
     ["S", "M", "L"], ["Negro", "Café"]),
]

# Cuántas unidades llegan por variante a cada tienda (el Centro es la principal).
UNIDADES_INICIALES = {"CEN": 6, "EQP": 4, "VEN": 4}

USUARIOS_DEMO = [
    # usuario, nombre, contraseña de demostración, rol, sucursal
    ("rosa", "Rosa Áñez", "Boutique2026", "admin", None),
    ("carla.v", "Carla Vaca", "Equipetrol26", "encargado", "EQP"),
    ("luis.r", "Luis Roca", "Ventura2026", "encargado", "VEN"),
]

VENDEDORES = {"CEN": ["Rosa", "Mariela"], "EQP": ["Carla"], "VEN": ["Luis", "Paola"]}
METODOS = ["efectivo", "qr", "qr", "tarjeta"]  # el QR es el pago más común


def _redondear_a_10(monto: Decimal) -> Decimal:
    """El cliente suele pagar con billetes: monto recibido redondeado a Bs 10 hacia arriba."""
    return (monto / 10).to_integral_value(rounding=ROUND_CEILING) * 10


def cargar_ejemplo(
    inv: Inventario,
    usuarios: Optional[RegistroUsuarios] = None,
    hoy: Optional[datetime] = None,
    dias: int = 14,
    semilla: int = 2026,
) -> dict:
    """Llena ``inv`` (vacío) con la boutique de ejemplo. Devuelve un resumen."""
    if inv.sucursales or inv.productos:
        raise ValueError("El inventario ya tiene datos; los datos de ejemplo van en uno vacío")
    hoy = hoy or datetime.now()
    rng = random.Random(semilla)
    inicio = datetime.combine((hoy - timedelta(days=dias)).date(), time(9, 0))

    suc = {codigo: inv.crear_sucursal(codigo, nombre, dir) for codigo, nombre, dir in SUCURSALES}
    for codigo, nombre, cat, marca, precio, costo, tallas, colores in CATALOGO:
        prod = inv.crear_producto(codigo, nombre, cat, precio, costo, marca=marca)
        inv.generar_matriz(prod.id, tallas, colores, stock_minimo=2)

    # Stock inicial: las tallas del medio llegan con más unidades.
    for codigo, base in UNIDADES_INICIALES.items():
        items = []
        for var in inv.variantes.values():
            extra = 2 if var.talla in ("M", "28", "30") else 0
            items.append((var.id, base + extra))
        inv.registrar_ingreso(suc[codigo].id, items, f"Pedido inicial {codigo}")

    # Reposición del Centro a Ventura Mall, recibida con una prenda menos.
    jeans = [v for v in inv.variantes.values() if v.sku.startswith("JEA-010")][:3]
    trf = inv.enviar_transferencia(
        suc["CEN"].id, suc["VEN"].id, [(v.id, 2) for v in jeans], "Reposición de jeans"
    )
    inv.recibir_transferencia(
        trf.id, {jeans[0].id: 1, jeans[1].id: 2, jeans[2].id: 2}, "Una prenda llegó dañada"
    )

    # Ventas de las últimas semanas, más movimiento los fines de semana.
    variantes = list(inv.variantes.values())
    for dia in range(dias):
        fecha = inicio + timedelta(days=dia)
        for codigo, sucursal in suc.items():
            cantidad_ventas = rng.randint(2, 5) + (2 if fecha.weekday() >= 5 else 0)
            for _ in range(cantidad_ventas):
                momento = fecha + timedelta(minutes=rng.randint(0, 11 * 60))
                elegidas = rng.sample(variantes, rng.choice([1, 1, 2, 3]))
                items = []
                for var in elegidas:
                    descuento = rng.choice([0, 0, 0, 0, 10, 15])
                    items.append((var.id, rng.choice([1, 1, 1, 2]), descuento))
                metodo = rng.choice(METODOS)
                recibido = None
                if metodo == "efectivo":
                    total = Decimal("0")
                    for v, c, d in items:
                        bruto = inv.productos[inv.variantes[v].producto_id].precio_venta * c
                        total += bruto - (bruto * d / 100).quantize(Decimal("0.01"))
                    recibido = _redondear_a_10(total)
                try:
                    inv.registrar_venta(
                        sucursal.id, items, metodo, recibido,
                        vendedor=rng.choice(VENDEDORES[codigo]), fecha=momento,
                    )
                except StockInsuficiente:
                    continue  # esa prenda se agotó en la tienda: el cliente no la llevó

    # Un error de caja corregido por la dueña.
    primera = next(iter(inv.ventas.values()))
    inv.anular_venta(primera.id, "Se cobró dos veces la misma prenda")

    if usuarios is not None:
        for usuario, nombre, clave, rol, sucursal in USUARIOS_DEMO:
            if usuarios.por_nombre(usuario) is None:
                usuarios.crear(
                    usuario, nombre, clave, rol, suc[sucursal].id if sucursal else None
                )

    return {
        "sucursales": len(inv.sucursales),
        "productos": len(inv.productos),
        "variantes": len(inv.variantes),
        "ventas": len(inv.ventas),
        "usuarios": len(usuarios.usuarios) if usuarios is not None else 0,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Genera datos de ejemplo de una boutique cruceña")
    parser.add_argument(
        "--archivo", default=os.environ.get("BOUTIQUE_DATOS", "data/boutique.json"),
        help="Archivo de datos (por defecto BOUTIQUE_DATOS o data/boutique.json)",
    )
    parser.add_argument("--dias", type=int, default=14, help="Días de ventas a generar")
    parser.add_argument("--forzar", action="store_true", help="Reemplazar el archivo si existe")
    args = parser.parse_args(argv)

    almacen = Almacen(args.archivo)
    if almacen.existe() and not args.forzar:
        print(f"{args.archivo} ya existe; use --forzar para reemplazarlo.", file=sys.stderr)
        return 1
    inv = Inventario()
    usuarios = RegistroUsuarios(secreto="x" * 32)  # el secreto no se guarda en el archivo
    resumen = cargar_ejemplo(inv, usuarios, dias=args.dias)
    almacen.guardar(inv, usuarios)
    print(
        f"Boutique de ejemplo guardada en {args.archivo}: {resumen['sucursales']} sucursales, "
        f"{resumen['productos']} productos, {resumen['variantes']} variantes, "
        f"{resumen['ventas']} ventas."
    )
    print("Usuarios de demostración (cambie las contraseñas antes de usarlo en serio):")
    for usuario, _, clave, rol, sucursal in USUARIOS_DEMO:
        print(f"  {usuario:8} {clave:13} {rol}{' · ' + sucursal if sucursal else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
