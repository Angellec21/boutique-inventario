# Registro de cambios

Todos los cambios importantes de este proyecto se documentan en este archivo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [1.0.0] - 2026-10-29

Primera versión estable: inventario completo para una boutique con varias sucursales.

### Agregado

- **Catálogo**: productos con código, categoría, marca, precio y costo en Bs, margen por prenda y búsqueda sin importar tildes.
- **Variantes** talla × color con SKU automático (`BLU-001-NEG-M`) y generación de la matriz completa; tallas de letra, numéricas y `UNICA`.
- **Stock por sucursal**: ingresos de mercadería (todo o nada), ajustes por conteo físico con motivo, kardex de movimientos y matriz de stock con valor en Bs.
- **Alertas de reposición** con el stock disponible en otras sucursales.
- **Transferencias** entre sucursales con estado en tránsito, recepción con faltantes y anulación.
- **Ventas en caja** con descuento por línea, pago en efectivo (con cambio), QR o tarjeta, precio y costo congelados, y anulaciones con devolución al stock.
- **Reportes del dueño**: más vendidos con margen, ventas por talla, cierre de caja por método de pago y vendedor, valor de la mercadería por sucursal.
- **Usuarios y roles** con JWT: administrador y encargado de tienda limitado a su sucursal; contraseñas cifradas con PBKDF2.
- **Persistencia** en archivo JSON con escritura atómica; se guarda tras cada cambio y se recupera al reiniciar.
- **Datos de ejemplo** de una boutique de Santa Cruz (`python -m app.datos_ejemplo`).
- **Respaldo descargable** (`GET /respaldo`, solo admin) y `/salud` con versión y modo de guardado.
- Integración continua con GitHub Actions en Python 3.11, 3.12 y 3.13.

[1.0.0]: https://github.com/Angellec21/boutique-inventario/releases/tag/v1.0.0
