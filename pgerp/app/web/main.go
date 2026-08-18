package main

import (
	"fmt"
	"log"
	"os"

	"pygo-framework/web"
)

func main() {
	socketPath := "/tmp/pgerp.sock"
	os.MkdirAll("/tmp", 0o755)

	app := web.NewApp(socketPath, "app.core.main")
	if err := app.Init(); err != nil {
		log.Fatalf("PyGo init error: %v", err)
	}

	registerRoutes(app)

	log.Println("PyGo ERP — V2.0 native dual-language ready")
	log.Printf("  Python: UDS bridge at %s", socketPath)

	if err := app.Run(":8080"); err != nil {
		log.Fatalf("PyGo server error: %v", err)
	}
}

func registerRoutes(app *web.App) {
	r := app.Router()

	// --- Health ---
	r.Handle("GET", "/health", func(ctx map[string]interface{}) (interface{}, error) {
		return map[string]interface{}{
			"status":    "ok",
			"runtime":   "hybrid",
			"languages": []string{"go", "python"},
		}, nil
	}, false, false)

	// --- Dashboard (HTML) ---
	r.Handle("GET", "/", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/dashboard.html"), nil
	}, false, false)

	// --- HTML Views ---
	r.Handle("GET", "/productos", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/productos.html"), nil
	}, false, false)

	r.Handle("GET", "/clientes", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/clientes.html"), nil
	}, false, false)

	r.Handle("GET", "/facturas", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/facturas.html"), nil
	}, false, false)

	r.Handle("GET", "/login", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/login.html"), nil
	}, false, false)

	r.Handle("GET", "/companies", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/companies.html"), nil
	}, false, false)

	r.Handle("GET", "/users", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/users.html"), nil
	}, false, false)

	// --- Tenancy API ---
	r.Handle("GET", "/api/tenancy/companies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/tenancy/companies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/tenancy/companies/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.update", ctx)
	}, true, false)

	r.Handle("DELETE", "/api/tenancy/companies/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.delete", ctx)
	}, true, false)

	r.Handle("POST", "/api/tenancy/switch", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.switch", ctx)
	}, false, false)

	r.Handle("GET", "/api/tenancy/current", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.current", ctx)
	}, false, false)

	r.Handle("POST", "/api/tenancy/users/transfer", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.users.transfer", ctx)
	}, true, false)

	// --- Inventory API ---
	r.Handle("GET", "/api/inventory/warehouses", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.warehouses.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/inventory/warehouses", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.warehouses.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/inventory/warehouses/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.warehouses.update", ctx)
	}, true, false)

	r.Handle("DELETE", "/api/inventory/warehouses/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.warehouses.delete", ctx)
	}, true, false)

	r.Handle("GET", "/api/inventory/stock", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/inventory/stock/transfer", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.transfer", ctx)
	}, true, false)

	r.Handle("POST", "/api/inventory/stock/adjust", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.adjust", ctx)
	}, true, false)

	r.Handle("GET", "/api/inventory/stock/movements", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.movements", ctx)
	}, false, false)

	r.Handle("GET", "/api/inventory/stock/alerts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.alerts", ctx)
	}, false, false)

	r.Handle("GET", "/api/inventory/categories", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.categories.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/inventory/categories", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.categories.create", ctx)
	}, true, false)

	// --- Sales API ---
	r.Handle("GET", "/api/sales/orders", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/sales/orders", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.create", ctx)
	}, true, false)

	r.Handle("POST", "/api/sales/orders/{id}/confirm", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.confirm", ctx)
	}, true, false)

	r.Handle("POST", "/api/sales/orders/{id}/deliver", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.deliver", ctx)
	}, true, false)

	r.Handle("POST", "/api/sales/orders/{id}/invoice", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.invoice", ctx)
	}, true, false)

	r.Handle("POST", "/api/sales/orders/{id}/cancel", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.cancel", ctx)
	}, true, false)

	r.Handle("GET", "/api/sales/purchase", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.purchase.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/sales/purchase", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.purchase.create", ctx)
	}, true, false)

	r.Handle("POST", "/api/sales/purchase/{id}/receive", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.purchase.receive", ctx)
	}, true, false)

	r.Handle("GET", "/api/sales/quotes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.quotes.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/sales/quotes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.quotes.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/sales/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.summary", ctx)
	}, false, false)

	// --- Auth API ---
	r.Handle("POST", "/api/auth/login", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.login", ctx)
	}, false, false)

	r.Handle("POST", "/api/auth/logout", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.logout", ctx)
	}, false, false)

	r.Handle("GET", "/api/auth/me", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.me", ctx)
	}, false, false)

	r.Handle("GET", "/api/auth/users", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.list", ctx)
	}, true, false)

	r.Handle("POST", "/api/auth/users", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/auth/users/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.update", ctx)
	}, true, false)

	r.Handle("DELETE", "/api/auth/users/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.delete", ctx)
	}, true, false)

	// --- REST API: Productos CRUD ---
	r.Handle("GET", "/api/productos", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.list", map[string]interface{}{})
	}, false, false)

	r.Handle("GET", "/api/productos-table", func(ctx map[string]interface{}) (interface{}, error) {
		result, err := app.Call("core.services.productos.list", map[string]interface{}{})
		if err != nil {
			return nil, err
		}
		return renderProductosRows(result), nil
	}, false, false)

	r.Handle("GET", "/api/productos/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.find", map[string]interface{}{"id": ctx["id"]})
	}, false, false)

	r.Handle("POST", "/api/productos", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.create", ctx)
	}, false, false)

	r.Handle("PUT", "/api/productos/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.update", ctx)
	}, false, false)

	r.Handle("DELETE", "/api/productos/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.delete", map[string]interface{}{"id": ctx["id"]})
	}, false, false)

	// --- REST API: Clientes CRUD ---
	r.Handle("GET", "/api/clientes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.list", map[string]interface{}{})
	}, false, false)

	r.Handle("GET", "/api/clientes/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.find", map[string]interface{}{"id": ctx["id"]})
	}, false, false)

	r.Handle("POST", "/api/clientes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.create", ctx)
	}, false, false)

	r.Handle("PUT", "/api/clientes/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.update", ctx)
	}, false, false)

	r.Handle("DELETE", "/api/clientes/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.delete", map[string]interface{}{"id": ctx["id"]})
	}, false, false)

	// --- REST API: Facturas CRUD ---
	r.Handle("GET", "/api/facturas", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.list", map[string]interface{}{})
	}, false, false)

	r.Handle("GET", "/api/facturas/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.find", map[string]interface{}{"id": ctx["id"]})
	}, false, false)

	r.Handle("POST", "/api/facturas", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.create", ctx)
	}, false, false)

	r.Handle("PUT", "/api/facturas/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.update", ctx)
	}, false, false)

	r.Handle("DELETE", "/api/facturas/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.delete", map[string]interface{}{"id": ctx["id"]})
	}, false, false)
}

// loadTemplate reads an HTML file.
func loadTemplate(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Sprintf("Error loading template: %v", err)
	}
	return string(data)
}

// renderProductosRows renders producto rows as HTML for HTMX.
func renderProductosRows(data interface{}) string {
	items, ok := data.([]interface{})
	if !ok {
		return ""
	}
	var rows string
	for _, item := range items {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		id := m["id"]
		codigo := m["codigo"]
		nombre := m["nombre"]
		precio := m["precio_unitario"]
		rows += fmt.Sprintf(`<tr><td class="px-6 py-4">%v</td><td class="px-6 py-4">%v</td><td class="px-6 py-4">%v</td><td class="px-6 py-4">$%.2f</td><td class="px-6 py-4"><button hx-delete="/api/productos/%v" hx-target="#productos-table" hx-confirm="Eliminar producto?">Eliminar</button></td></tr>`, id, codigo, nombre, precio, id)
	}
	return rows
}
