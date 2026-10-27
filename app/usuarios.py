"""Usuarios, contraseñas y tokens de acceso.

Dos roles, pensados para una boutique con varias sucursales:

* ``admin``: el dueño o la administradora. Ve y hace todo, incluidos costos,
  márgenes y reportes.
* ``encargado``: la persona a cargo de una tienda. Opera solo su sucursal
  (ventas, ingresos, conteos, recepción de transferencias) y no ve costos.

Las contraseñas se guardan con PBKDF2-SHA256 y sal aleatoria (biblioteca
estándar), nunca en texto plano. Los tokens son JWT firmados con HS256.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from pydantic import BaseModel

from .inventario import Conflicto, ErrorInventario, NoEncontrado

ROLES = ("admin", "encargado")
ITERACIONES = 200_000
MINUTOS_TOKEN = 8 * 60  # un turno de tienda
_USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,30}$")


class CredencialesInvalidas(ErrorInventario):
    """Usuario o contraseña incorrectos, token vencido o usuario inactivo."""


class Usuario(BaseModel):
    id: int
    usuario: str
    nombre: str
    rol: str
    sucursal_id: Optional[int] = None
    activo: bool = True
    clave_hash: str

    def publico(self) -> dict:
        return self.model_dump(exclude={"clave_hash"})


def cifrar_clave(
    clave: str, sal: Optional[bytes] = None, iteraciones: int = ITERACIONES
) -> str:
    """Devuelve ``pbkdf2_sha256$iteraciones$sal$hash`` (sal y hash en base64)."""
    sal = sal or secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, iteraciones)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(iteraciones),
            base64.b64encode(sal).decode(),
            base64.b64encode(derivada).decode(),
        )
    )


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        algoritmo, iteraciones, sal_b64, hash_b64 = guardado.split("$")
    except ValueError:
        return False
    if algoritmo != "pbkdf2_sha256":
        return False
    derivada = hashlib.pbkdf2_hmac(
        "sha256", clave.encode(), base64.b64decode(sal_b64), int(iteraciones)
    )
    return hmac.compare_digest(derivada, base64.b64decode(hash_b64))


def validar_clave(clave: str) -> None:
    if len(clave) < 8:
        raise ErrorInventario("La contraseña debe tener al menos 8 caracteres")
    if clave.isdigit() or clave.isalpha():
        raise ErrorInventario("La contraseña debe combinar letras y números")


class RegistroUsuarios:
    """Usuarios del sistema y emisión/validación de tokens."""

    def __init__(
        self,
        secreto: Optional[str] = None,
        minutos_token: int = MINUTOS_TOKEN,
        iteraciones: int = ITERACIONES,
    ):
        self.usuarios: dict[int, Usuario] = {}
        self._secreto = secreto or os.environ.get("BOUTIQUE_SECRET") or secrets.token_urlsafe(32)
        if len(self._secreto) < 32:
            raise ValueError("El secreto para firmar tokens debe tener al menos 32 caracteres")
        self.minutos_token = minutos_token
        self.iteraciones = iteraciones  # menos solo en pruebas, para que corran rápido
        self._ultimo_id = 0

    # --------------------------------------------------------------- gestión
    def crear(
        self,
        usuario: str,
        nombre: str,
        clave: str,
        rol: str = "encargado",
        sucursal_id: Optional[int] = None,
    ) -> Usuario:
        usuario = usuario.strip().lower()
        if not _USUARIO_VALIDO.match(usuario):
            raise ErrorInventario(
                "Usuario inválido: 3 a 30 caracteres, minúsculas, números, punto, guion"
            )
        if any(u.usuario == usuario for u in self.usuarios.values()):
            raise Conflicto(f"El usuario {usuario} ya existe")
        rol = rol.strip().lower()
        if rol not in ROLES:
            raise ErrorInventario(f"Rol inválido. Use: {', '.join(ROLES)}")
        if rol == "encargado" and sucursal_id is None:
            raise ErrorInventario("Un encargado debe tener una sucursal asignada")
        if not nombre.strip():
            raise ErrorInventario("Indique el nombre de la persona")
        validar_clave(clave)
        self._ultimo_id += 1
        nuevo = Usuario(
            id=self._ultimo_id,
            usuario=usuario,
            nombre=nombre.strip(),
            rol=rol,
            sucursal_id=sucursal_id if rol == "encargado" else None,
            clave_hash=cifrar_clave(clave, iteraciones=self.iteraciones),
        )
        self.usuarios[nuevo.id] = nuevo
        return nuevo

    def obtener(self, usuario_id: int) -> Usuario:
        try:
            return self.usuarios[usuario_id]
        except KeyError:
            raise NoEncontrado(f"Usuario {usuario_id} no existe") from None

    def por_nombre(self, usuario: str) -> Optional[Usuario]:
        usuario = usuario.strip().lower()
        return next((u for u in self.usuarios.values() if u.usuario == usuario), None)

    def _admins_activos(self) -> int:
        return sum(1 for u in self.usuarios.values() if u.rol == "admin" and u.activo)

    def desactivar(self, usuario_id: int) -> Usuario:
        """Da de baja a un usuario (no se borra, para conservar el historial)."""
        u = self.obtener(usuario_id)
        if u.rol == "admin" and u.activo and self._admins_activos() == 1:
            raise Conflicto("No se puede desactivar al único administrador activo")
        u.activo = False
        return u

    def cambiar_clave(self, usuario_id: int, actual: str, nueva: str) -> None:
        u = self.obtener(usuario_id)
        if not verificar_clave(actual, u.clave_hash):
            raise CredencialesInvalidas("La contraseña actual no es correcta")
        validar_clave(nueva)
        u.clave_hash = cifrar_clave(nueva, iteraciones=self.iteraciones)

    def restablecer_clave(self, usuario_id: int, nueva: str) -> None:
        """El administrador asigna una contraseña nueva (p. ej. si la olvidaron)."""
        validar_clave(nueva)
        self.obtener(usuario_id).clave_hash = cifrar_clave(nueva, iteraciones=self.iteraciones)

    # ---------------------------------------------------------------- acceso
    def autenticar(self, usuario: str, clave: str) -> Usuario:
        u = self.por_nombre(usuario)
        # Se verifica igual una clave ficticia para no revelar qué usuarios existen.
        guardado = u.clave_hash if u else cifrar_clave("x", b"0" * 16, self.iteraciones)
        if not verificar_clave(clave, guardado) or u is None or not u.activo:
            raise CredencialesInvalidas("Usuario o contraseña incorrectos")
        return u

    def emitir_token(self, u: Usuario, ahora: Optional[datetime] = None) -> str:
        ahora = ahora or datetime.now(timezone.utc)
        datos = {
            "sub": str(u.id),
            "rol": u.rol,
            "suc": u.sucursal_id,
            "iat": ahora,
            "exp": ahora + timedelta(minutes=self.minutos_token),
        }
        return jwt.encode(datos, self._secreto, algorithm="HS256")

    def usuario_del_token(self, token: str) -> Usuario:
        try:
            datos = jwt.decode(token, self._secreto, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise CredencialesInvalidas("La sesión venció; vuelva a ingresar") from None
        except jwt.InvalidTokenError:
            raise CredencialesInvalidas("Token inválido") from None
        u = self.usuarios.get(int(datos["sub"]))
        if u is None or not u.activo:
            raise CredencialesInvalidas("El usuario ya no tiene acceso")
        return u
