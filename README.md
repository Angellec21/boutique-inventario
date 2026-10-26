# 👗 Boutique Inventario

[![CI](https://github.com/Angellec21/boutique-inventario/actions/workflows/ci.yml/badge.svg)](https://github.com/Angellec21/boutique-inventario/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green.svg)](LICENSE)

API de inventario para **tiendas de ropa con varias sucursales**: cada prenda se controla por **talla y color**, con stock separado por tienda, alertas de reposición y kardex de movimientos. Montos en **bolivianos (Bs)**.

> 🚧 **En desarrollo.** Hoy funciona el catálogo, las variantes, el stock por sucursal, las transferencias entre tiendas, las ventas en caja y los reportes del dueño. Usuarios, persistencia y datos de ejemplo llegan en las próximas versiones (ver [Roadmap](#-roadmap)).

## 💼 El problema

Una boutique de Santa Cruz con tiendas en el centro y en un mall suele llevar el inventario en cuadernos o en Excel por tienda. Las preguntas del día a día no tienen respuesta rápida:

- *«¿Tenemos esta blusa en talla M color beige? ¿En qué sucursal?»*
- *«¿Qué tallas se están acabando y hay que pedir al proveedor?»*
- *«¿Cuánta plata hay en mercadería en cada tienda?»*
- *«¿Por qué el conteo físico no cuadra con el sistema?»*
- *«¿Qué modelos y qué tallas se venden más? ¿Cuánto entró hoy por QR y cuánto en efectivo?»*

Boutique Inventario responde esas preguntas con una API que puede usar un sistema de caja, una app móvil o un panel web.

## ✨ Funcionalidades

| Módulo | Qué hace |
|---|---|
| **Catálogo** | Productos (modelos) con código, categoría, marca, precio y costo en Bs; margen por prenda; búsqueda sin importar tildes |
| **Variantes** | Combinaciones talla × color con **SKU automático** (`BLU-001-AZM-M`); se puede generar toda la matriz de una vez. Tallas XS–XXL, `UNICA` o numéricas (jeans 28–44) |
| **Stock por sucursal** | Ingresos de mercadería por SKU o id (todo o nada), ajustes por conteo físico con motivo obligatorio |
| **Kardex** | Cada movimiento queda registrado con cantidad, saldo, motivo y referencia (p. ej. n.º de pedido) |
| **Matriz de stock** | Tabla talla × color por producto, en una sucursal o en todas, con valor de la mercadería en Bs |
| **Alertas de reposición** | Variantes en o por debajo de su stock mínimo, con cuánto falta y cuánto hay en otras sucursales (para transferir antes de comprar) |
| **Transferencias** | Envío entre sucursales con código `TRF-00001`: el stock sale del origen y queda **en tránsito** hasta que el destino confirma. Recepción con conteo y registro de faltantes, o anulación con devolución al origen |
| **Ventas en caja** | Venta por SKU con código `V-CEN-000001`, descuento por línea (hasta 50 %), pago en efectivo (con cambio), QR o tarjeta. Todo o nada; precio y costo quedan congelados para calcular el margen real. Anulación con motivo que devuelve las prendas al stock |
| **Reportes del dueño** | Más vendidos por modelo o SKU con margen, ventas por talla (para decidir la curva de compra), cierre de caja por método de pago y vendedor, valor de la mercadería por sucursal a costo y a precio de venta |

## 🛠️ Tecnologías

- **Python 3.11+** y **FastAPI** (documentación OpenAPI automática en `/docs`)
- **Pydantic v2** para validación; montos con `Decimal`
- **pytest** + `TestClient` para pruebas de servicio y de API
- **GitHub Actions**: pruebas en Python 3.11, 3.12 y 3.13 en cada push y pull request

## 🏗️ Arquitectura

```
app/
├── models.py      # Modelos de dominio: Sucursal, Producto, Variante, Movimiento, Transferencia, Venta
├── inventario.py  # Reglas de negocio (servicio): SKU, stock, ajustes, alertas, transferencias, ventas
├── reportes.py    # Reportes de solo lectura: más vendidos, tallas, cierre de caja, valor de inventario
├── schemas.py     # Esquemas de entrada de la API
└── main.py        # Rutas FastAPI y mapeo de errores de negocio a HTTP
tests/
├── test_inventario.py          # Pruebas del servicio
├── test_transferencias.py      # Ciclo de vida de las transferencias
├── test_api.py                 # Pruebas de los endpoints
├── test_api_transferencias.py  # Endpoints de transferencias
├── test_ventas.py              # Ventas, descuentos, cambio y anulaciones
├── test_reportes.py            # Reportes del dueño
└── test_api_ventas.py          # Endpoints de ventas y reportes
```

La lógica de negocio vive en `Inventario`, sin depender de FastAPI: se prueba de forma aislada y la persistencia se puede cambiar sin tocar las rutas. Los errores de negocio se traducen a HTTP: `404` (no existe), `409` (duplicado o stock insuficiente) y `422` (dato inválido).

### Ciclo de una transferencia

```mermaid
stateDiagram-v2
    [*] --> en_transito: envío (sale stock del origen)
    en_transito --> recibida: llegó todo
    en_transito --> recibida_con_diferencias: llegó menos (observación obligatoria)
    en_transito --> anulada: el stock vuelve al origen
```

Cada paso genera movimientos en el kardex con el código de la transferencia como referencia, así se puede rastrear una prenda de una tienda a otra.

## 🚀 Instalación

```bash
git clone https://github.com/Angellec21/boutique-inventario.git
cd boutique-inventario
python -m venv .venv && source .venv/bin/activate   # En Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Abrir la documentación interactiva en <http://localhost:8000/docs>.

### Pruebas

```bash
python -m pytest
```

## 📖 Uso rápido

```bash
# 1. Sucursal y producto
curl -X POST localhost:8000/sucursales -H 'Content-Type: application/json' \
  -d '{"codigo":"CEN","nombre":"Centro","direccion":"Calle 24 de Septiembre #155"}'
curl -X POST localhost:8000/productos -H 'Content-Type: application/json' \
  -d '{"codigo":"BLU-001","nombre":"Blusa de lino manga corta","categoria":"Blusas","precio_venta":"189","costo":"95"}'

# 2. Todas las variantes S/M/L en negro y beige
curl -X POST localhost:8000/productos/1/variantes/matriz -H 'Content-Type: application/json' \
  -d '{"tallas":["S","M","L"],"colores":["Negro","Beige"]}'

# 3. Ingreso de mercadería por SKU
curl -X POST localhost:8000/stock/ingresos -H 'Content-Type: application/json' \
  -d '{"sucursal_id":1,"referencia":"Pedido 0045","items":[{"sku":"BLU-001-NEG-M","cantidad":6}]}'

# 4. ¿Qué hay y qué falta?
curl localhost:8000/productos/1/stock
curl localhost:8000/sucursales/1/alertas

# 5. Enviar 2 blusas M al mall y confirmar la llegada (faltó 1)
curl -X POST localhost:8000/transferencias -H 'Content-Type: application/json' \
  -d '{"origen_id":1,"destino_id":2,"nota":"Vitrina fin de semana","items":[{"sku":"BLU-001-NEG-M","cantidad":2}]}'
curl -X POST localhost:8000/transferencias/1/recepcion -H 'Content-Type: application/json' \
  -d '{"items":[{"sku":"BLU-001-NEG-M","cantidad":1}],"observacion":"Faltó 1 en la bolsa"}'

# 6. Vender 2 blusas con 10 % de descuento, pago en efectivo
curl -X POST localhost:8000/ventas -H 'Content-Type: application/json' \
  -d '{"sucursal_id":1,"metodo_pago":"efectivo","monto_recibido":"400","vendedor":"Carla","items":[{"sku":"BLU-001-NEG-M","cantidad":2,"descuento_pct":"10"}]}'

# 7. Cierre de caja del día y lo más vendido del mes
curl "localhost:8000/reportes/resumen-ventas?desde=2026-10-26&hasta=2026-10-26&sucursal_id=1"
curl "localhost:8000/reportes/mas-vendidos?desde=2026-10-01&hasta=2026-10-31&por=variante"
```

Ejemplo de cierre de caja (`GET /reportes/resumen-ventas`):

```json
{
  "cantidad_ventas": 2,
  "ventas_anuladas": 1,
  "unidades": 5,
  "total": "997.10",
  "descuentos": "18.90",
  "ticket_promedio": "498.55",
  "margen": "487.10",
  "margen_pct": "48.9",
  "por_metodo_pago": { "efectivo": "827.00", "qr": "170.10" },
  "por_vendedor": { "Carla": "827.00", "Luis": "170.10" }
}
```

Ejemplo de matriz de stock (`GET /productos/1/stock`):

```json
{
  "codigo": "BLU-001",
  "tallas": ["S", "M", "L"],
  "colores": ["Beige", "Negro"],
  "celdas": { "Beige": { "S": 0, "M": 0, "L": 0 }, "Negro": { "S": 0, "M": 6, "L": 0 } },
  "total_unidades": 6,
  "valor_venta": "1134.00"
}
```

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` / `GET` | `/sucursales` | Crear y listar sucursales |
| `POST` / `GET` | `/productos` | Crear y buscar productos (`?q=`, `?categoria=`) |
| `GET` | `/productos/{id}` | Detalle con margen y variantes con stock total |
| `POST` | `/productos/{id}/variantes` | Agregar una variante talla/color |
| `POST` | `/productos/{id}/variantes/matriz` | Generar todas las combinaciones |
| `GET` | `/variantes/sku/{sku}` | Buscar por SKU (lector de código) |
| `POST` | `/stock/ingresos` | Ingreso de mercadería a una sucursal |
| `POST` | `/stock/ajustes` | Ajuste por conteo físico |
| `GET` | `/productos/{id}/stock` | Matriz talla × color (`?sucursal_id=`) |
| `GET` | `/sucursales/{id}/alertas` | Variantes por reponer |
| `GET` | `/variantes/{id}/kardex` | Historial de movimientos |
| `POST` | `/transferencias` | Enviar mercadería a otra sucursal |
| `GET` | `/transferencias` | Listar (`?sucursal_id=`, `?estado=en_transito`) |
| `GET` | `/transferencias/{id}` | Detalle con unidades enviadas y faltantes |
| `POST` | `/transferencias/{id}/recepcion` | Confirmar llegada (todo o lo contado) |
| `POST` | `/transferencias/{id}/anulacion` | Anular el envío; el stock vuelve al origen |
| `POST` | `/ventas` | Registrar venta (por SKU o id, con descuento y método de pago) |
| `GET` | `/ventas` | Listar (`?sucursal_id=`, `?desde=`, `?hasta=` en formato AAAA-MM-DD) |
| `GET` | `/ventas/{id}` | Detalle con subtotales, descuento, total y cambio |
| `POST` | `/ventas/{id}/anulacion` | Anular la venta; las prendas vuelven al stock |
| `GET` | `/reportes/mas-vendidos` | Ranking (`?por=producto\|variante`, `?limite=`, fechas, sucursal) |
| `GET` | `/reportes/ventas-por-talla` | Unidades y % por talla (`?categoria=`) |
| `GET` | `/reportes/resumen-ventas` | Cierre de caja por método de pago y vendedor |
| `GET` | `/reportes/valor-inventario` | Mercadería por sucursal a costo y a precio de venta |

## 🗺️ Roadmap

- [x] Catálogo con variantes por talla y color
- [x] Stock por sucursal, ajustes y kardex
- [x] Alertas de stock mínimo
- [x] Transferencias entre sucursales (envío, recepción con faltantes y anulación)
- [x] Ventas con descuento de stock, descuentos por línea y anulaciones
- [x] Reportes: más vendidos, ventas por talla, cierre de caja, valor de inventario por sucursal
- [ ] Usuarios y roles (encargado de tienda / administrador)
- [ ] Persistencia en SQLite y datos de ejemplo de Santa Cruz

## 📄 Licencia

[MIT](LICENSE) © 2026 Angel Emanuel Lecaro Quispe
