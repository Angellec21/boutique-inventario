"""Utilidades compartidas por las pruebas de la API."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.usuarios import RegistroUsuarios

SECRETO = "secreto-solo-para-pruebas-0123456789abcdef"
ADMIN = ("rosa", "Boutique2026")


def ingresar(client: TestClient, usuario: str, clave: str) -> TestClient:
    r = client.post("/auth/token", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client


def cliente_admin() -> TestClient:
    """Cliente con sesión de administradora (Rosa, la dueña)."""
    usuarios = RegistroUsuarios(secreto=SECRETO, iteraciones=1_000)
    usuarios.crear(ADMIN[0], "Rosa Áñez", ADMIN[1], rol="admin")
    return ingresar(TestClient(create_app(usuarios=usuarios)), *ADMIN)


def como(client: TestClient, usuario: str, clave: str) -> TestClient:
    """Otro cliente sobre la misma app, con la sesión de otro usuario."""
    return ingresar(TestClient(client.app), usuario, clave)
