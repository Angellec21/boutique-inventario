"""Configuración común de las pruebas.

``app.main`` crea la aplicación al importarse con el archivo de ``BOUTIQUE_DATOS``;
en pruebas se apunta a una carpeta temporal para no escribir en ``data/``.
"""

import os
import tempfile

os.environ.setdefault(
    "BOUTIQUE_DATOS", os.path.join(tempfile.mkdtemp(prefix="boutique-pruebas-"), "boutique.json")
)
