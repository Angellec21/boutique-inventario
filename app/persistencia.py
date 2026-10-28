"""Guardado del inventario y los usuarios en un archivo JSON.

Una boutique pequeña no necesita un servidor de base de datos para empezar:
todo el estado (sucursales, catálogo, stock, kardex, transferencias, ventas y
usuarios) se guarda en un solo archivo que se puede respaldar copiándolo.

* La escritura es atómica: se escribe un archivo temporal en la misma carpeta y
  se reemplaza el anterior con ``os.replace``. Si se corta la luz a mitad del
  guardado, queda el archivo anterior intacto, nunca uno a medias.
* Los montos se guardan como texto (``"189.00"``) para no perder precisión.
* El archivo lleva un número de formato para poder migrarlo en el futuro.
* Las contraseñas se guardan solo como hash PBKDF2; el secreto de los tokens
  nunca se escribe en el archivo (va en la variable ``BOUTIQUE_SECRET``).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .inventario import ErrorInventario, Inventario
from .models import Movimiento, Producto, Sucursal, Transferencia, Variante, Venta
from .usuarios import RegistroUsuarios, Usuario

VERSION_FORMATO = 1


class ArchivoInvalido(ErrorInventario):
    """El archivo de datos no se puede leer o es de un formato desconocido."""


def exportar(inv: Inventario, usuarios: Optional[RegistroUsuarios] = None) -> dict:
    """Todo el estado como un diccionario serializable a JSON."""
    datos = {
        "formato": VERSION_FORMATO,
        "guardado_en": datetime.now().isoformat(timespec="seconds"),
        "secuencias": dict(inv._seq),
        "sucursales": [s.model_dump(mode="json") for s in inv.sucursales.values()],
        "productos": [p.model_dump(mode="json") for p in inv.productos.values()],
        "variantes": [v.model_dump(mode="json") for v in inv.variantes.values()],
        "stock": [
            {"variante_id": v, "sucursal_id": s, "cantidad": c}
            for (v, s), c in sorted(inv._stock.items())
            if c != 0
        ],
        "movimientos": [m.model_dump(mode="json") for m in inv.movimientos],
        "transferencias": [t.model_dump(mode="json") for t in inv.transferencias.values()],
        "ventas": [v.model_dump(mode="json") for v in inv.ventas.values()],
    }
    if usuarios is not None:
        datos["usuarios"] = {
            "ultimo_id": usuarios._ultimo_id,
            "lista": [u.model_dump() for u in usuarios.usuarios.values()],
        }
    return datos


def importar(
    datos: dict, inv: Inventario, usuarios: Optional[RegistroUsuarios] = None
) -> None:
    """Reemplaza el estado de ``inv`` (y de ``usuarios``) con el contenido de ``datos``."""
    if not isinstance(datos, dict) or datos.get("formato") != VERSION_FORMATO:
        raise ArchivoInvalido(
            f"Formato de datos no soportado (se esperaba formato {VERSION_FORMATO})"
        )
    try:
        sucursales = {s.id: s for s in map(Sucursal.model_validate, datos["sucursales"])}
        productos = {p.id: p for p in map(Producto.model_validate, datos["productos"])}
        variantes = {v.id: v for v in map(Variante.model_validate, datos["variantes"])}
        movimientos = [Movimiento.model_validate(m) for m in datos["movimientos"]]
        transferencias = {
            t.id: t for t in map(Transferencia.model_validate, datos["transferencias"])
        }
        ventas = {v.id: v for v in map(Venta.model_validate, datos["ventas"])}
        stock: dict[tuple[int, int], int] = defaultdict(int)
        for fila in datos["stock"]:
            stock[(int(fila["variante_id"]), int(fila["sucursal_id"]))] = int(fila["cantidad"])
        secuencias = defaultdict(int, {k: int(v) for k, v in datos["secuencias"].items()})
        lista_usuarios = None
        if usuarios is not None and "usuarios" in datos:
            lista_usuarios = [Usuario.model_validate(u) for u in datos["usuarios"]["lista"]]
            ultimo_id = int(datos["usuarios"]["ultimo_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ArchivoInvalido(f"El archivo de datos está dañado: {exc}") from exc

    # Solo se modifica el estado cuando todo se leyó bien (todo o nada).
    inv.sucursales, inv.productos, inv.variantes = sucursales, productos, variantes
    inv.movimientos, inv.transferencias, inv.ventas = movimientos, transferencias, ventas
    inv._stock, inv._seq = stock, secuencias
    if lista_usuarios is not None:
        usuarios.usuarios = {u.id: u for u in lista_usuarios}
        usuarios._ultimo_id = ultimo_id


class Almacen:
    """Archivo JSON donde vive el estado del sistema."""

    def __init__(self, ruta: str | os.PathLike):
        self.ruta = Path(ruta)
        self._candado = threading.Lock()

    def existe(self) -> bool:
        return self.ruta.is_file()

    def guardar(self, inv: Inventario, usuarios: Optional[RegistroUsuarios] = None) -> None:
        with self._candado:
            contenido = json.dumps(exportar(inv, usuarios), ensure_ascii=False, indent=1)
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            fd, temporal = tempfile.mkstemp(
                prefix=f".{self.ruta.name}.", suffix=".tmp", dir=self.ruta.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(contenido)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporal, self.ruta)
            except BaseException:
                if os.path.exists(temporal):
                    os.unlink(temporal)
                raise

    def cargar(self, inv: Inventario, usuarios: Optional[RegistroUsuarios] = None) -> bool:
        """Carga el archivo si existe. Devuelve ``False`` en el primer arranque."""
        if not self.existe():
            return False
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArchivoInvalido(f"No se pudo leer {self.ruta}: {exc}") from exc
        importar(datos, inv, usuarios)
        return True
