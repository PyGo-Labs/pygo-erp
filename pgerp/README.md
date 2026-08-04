# PyGo ERP (pgerp)

Complete ERP/CRM system built with [PyGo Framework](https://github.com/PyGo-labs/pygo-framework) — covering accounting, inventory, sales, purchasing, HR, project management, and more.

## 🚀 Quick Start

```bash
# Create the ERP project using PyGo CLI
pygo new pgerp "PyGo ERP" --full-stack
cd pgerp

# Install all required modules
pygo module install auth
pygo module install multitenancy
pygo module install i18n
pygo module install observability
pygo module install notifications
pygo module install admin
pygo module install ui

# Run database migrations
pygo db migrate

# Start the server
pygo serve
```

Visit `http://localhost:8080` → Login page

## 🏗️ Architecture

Built on the full PyGo ecosystem:

| Module | Version | Purpose |
|--------|---------|---------|
| pygo-framework | v1.2.0 | Core runtime + transpiler |
| pygo-multitenancy | v0.1.0 | Multi-company/tenant isolation |
| pygo-auth | v1.0.0 | RBAC + JWT sessions |
| pygo-i18n | v0.1.0 | Spanish/English, multi-domain |
| pygo-observability | v0.1.0 | Tracing + metrics |
| pygo-notifications | v0.1.0 | Email/SMS/Push |
| pygo-admin | v0.5.0 | CRUD UI components |
| pygo-ui | v0.5.0 | 44 HTMX components |

## 📦 Modules (10 ERP areas)

```
┌─────────────────────────────────────────────────────┐
│  PYGO ERP — Full ERP Suite                          │
├──────────────┬──────────────┬──────────────────────┤
│ 📊 Contabilidad │ 📦 Inventario  │ 🛒 Ventas           │
│ - Facturas       │ - Stock          │ - Pedidos           │
│ - Cuentas        │ - Movimientos    │ - Clientes          │
│ - Pagos          │ - Almacenes      │ - Cotizaciones      │
├──────────────┬──────────────┬──────────────────────┤
│ 🛒 Compras        │ 👥 RRHH         │ 📁 Proyectos        │
│ - Órdenes        │ - Empleados      │ - Proyectos          │
│ - Proveedores     │ - Departamentos  │ - Tareas            │
│ - Recepciones    │ - Puestos        │ - Timesheets        │
├──────────────┬──────────────┬──────────────────────┤
│ ⚙️ Config        │ 📈 Reportes    │ 📱 Mobile           │
│ - Monedas        │ - Ventas         │ - Responsive UI      │
│ - Impuestos       │ - Inventario      │ - HTMX/PWA         │
│ - Usuarios        │ - Contabilidad    │                     │
└─────────────────────────────────────────────────────┘
```

## 🎯 Features

- Multi-tenancy (multi-company support)
- Multi-currency with exchange rates
- Multi-language (Spanish/English)
- RBAC (Role-based access control)
- Full CRUD with HTMX (no page reloads)
- REST API endpoints
- Traceability (tracing + metrics)
- Reports (PDF/Excel planned)
- Mobile-responsive UI (pygo-ui v0.5.0)

## 🧪 Testing

```bash
# Run ERP tests
pygo test app/
```

## 📜 License

MIT — see [LICENSE](LICENSE)
