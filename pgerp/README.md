# PyGo ERP (pgerp)

Complete ERP/CRM system built natively with PyGo Framework — using `.pgo` DSL syntax, native models, HTMX templates, and the full PyGo ecosystem.

## 🚀 Quick Start

```bash
# Option 1: Use PyGo CLI to scaffold the project
pygo new pgerp "PyGo ERP" --full-stack
cd pgerp

# Install required modules
pygo module install auth
pygo module install multitenancy
pygo module install i18n
pygo module install observability
pygo module install notifications
pygo module install admin
pygo module install ui

# Run migrations
pygo db migrate

# Start the server — ¡te consulto antes de levantar!
pygo serve
```

Visit `http://localhost:8080` — PyGo ERP dashboard

## 🏗️ Arquitectura Native PyGo

Todo escrito en `.pgo` — sin necesidad de Python:

```
pgerp/
├── pygo.toml          # Project config (DSL v0.0.1)
├── app.pgo            # Main routes + handlers (native DSL)
├── models.pgo         # Database models (native DSL)
├── migrations/        # SQL schema
│   └── 001_schema.sql
├── templates/         # HTMX templates
│   ├── base.html
│   ├── dashboard.html
│   ├── auth/login.html
│   ├── productos/
│   │   ├── index.html
│   │   └── form.html
│   ├── clientes/
│   ├── proveedores/
│   ├── facturas/
│   ├── inventario/
│   ├── pedidos/
│   ├── empleados/
│   ├── proyectos/
│   │   └── kanban.html
│   ├── tareas/
│   │   └── kanban.html
│   ├── reportes/
│   │   └── ventas.html
│   └── configuracion/
│       └── index.html
└── tests/
```

## 📦 Models (Native .pgo)

All models written in PyGo DSL — transpiled to Go and Python automatically:

```pgo
# models.pgo
model Producto:
  codigo: String
  nombre: String
  descripcion: String?
  tipo: Enum = producto
  categoria: UUID?
  unidad_medida: String = "pz"
  precio_unitario: Decimal = 0.00
  empresa: UUID
  activo: Boolean = true
```

## 🎯 Modules

| Module | Purpose |
|--------|---------|
| `auth` | RBAC + JWT sessions |
| `multitenancy` | Multi-company isolation |
| `i18n` | Multi-language (ES/EN) |
| `observability` | Tracing + metrics |
| `notifications` | Email/SMS/Push |
| `admin` | CRUD UI components |
| `ui` | 44 HTMX components |

## 🧪 Testing

```bash
pygo test
```

## 📜 License

MIT — see [LICENSE](LICENSE)
