# pygo-erp

ERP/CRM showcase for [PyGo Framework](https://github.com/PyGo-labs/pygo-framework) — database models, CRUD routes, and HTMX templates demonstrating PyGo's native capabilities.

## 🐍 Instalación

```python
from app.models import (
  Empresa, Producto, Cliente, Proveedor,
  Factura, Inventario, Usuario, Configuracion,
)

# Initialize the ERP
empresa = Empresa(rfc="RFC123", razon_social="Acme Corp").save()

# Create products
producto = Producto(
  codigo="PROD-001",
  nombre="Laptop",
  precio_unitario=15000.00,
  empresa=empresa.id,
).save()

# Track inventory
Inventario(producto=producto.id).save()
```

## 🏗️ Arquitectura

- Uses native `pygo-multitenancy` for multi-tenant data isolation
- Native `pygo-auth` for user management and RBAC
- Native `pygo-validator` for input validation in `.pgo` routes
- `pygo-ui` v0.5.0 components (Table, Form, Badge, Icon)
- HTMX + Alpine.js for interactivity

## 📊 Modelo de datos

| Modelo | Tabla | Descripción |
|--------|-------|-------------|
| Empresa | empresas | Company/organization (tenant root) |
| Categoria | categorias | Product/service categories |
| Producto | productos | Products with pricing, cost, inventory |
| Cliente | clientes | Customer records |
| Proveedor | proveedores | Supplier records |
| Factura | facturas | Sales/purchase invoices |
| FacturaLinea | facturas_lineas | Invoice line items |
| Inventario | inventarios | Stock tracking per product/warehouse |
| Usuario | usuarios | System users with roles |
| Configuracion | configuraciones | Key-value configuration |

## 🛠️ Uso en routes (.pgo)

```pgo
# Import models
from app.models import Producto, Inventario
from auth import current_user

route GET /productos -> productos.list

handler productos_list:
  productos.list() -> HTML:
    query = Producto.where("empresa", current_user.empresa)
    productos = query.limit(20).all()
    # Returns HTMX-enhanced table
    return Table(...)
```

## 📜 License

MIT — see [LICENSE](LICENSE)
