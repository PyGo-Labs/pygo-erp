package main

import (
	"fmt"
	"log"
	"os"

	"pygo-framework/observability"
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

	r.Handle("GET", "/metrics", func(ctx map[string]interface{}) (interface{}, error) {
		return observability.GetMetrics(), nil
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

	r.Handle("GET", "/tenancy", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/tenancy.html"), nil
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

	// --- Accounting API ---
	r.Handle("GET", "/api/accounting/accounts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.accounts.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/accounts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.accounts.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/accounts/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.accounts.detail", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/accounts/seed", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.accounts.seed", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/journal", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.journal.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/journal", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.journal.create", ctx)
	}, true, false)

	r.Handle("POST", "/api/accounting/journal/from-sale/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.journal.from_sale", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/trial-balance", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.trial_balance", ctx)
	}, false, false)

	r.Handle("GET", "/api/accounting/income-statement", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.income_statement", ctx)
	}, false, false)

	r.Handle("GET", "/api/accounting/balance-sheet", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.balance_sheet", ctx)
	}, false, false)

	// --- CRM API ---
	r.Handle("GET", "/api/crm/leads", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/crm/leads", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/crm/leads/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.update", ctx)
	}, true, false)

	r.Handle("POST", "/api/crm/leads/{id}/convert", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.convert", ctx)
	}, true, false)

	r.Handle("GET", "/api/crm/opportunities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/crm/opportunities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/crm/opportunities/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.update", ctx)
	}, true, false)

	r.Handle("POST", "/api/crm/opportunities/{id}/won", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.won", ctx)
	}, true, false)

	r.Handle("POST", "/api/crm/opportunities/{id}/lost", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.lost", ctx)
	}, true, false)

	r.Handle("GET", "/api/crm/pipeline/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.pipeline.summary", ctx)
	}, false, false)

	r.Handle("GET", "/api/crm/pipeline/funnel", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.pipeline.funnel", ctx)
	}, false, false)

	r.Handle("GET", "/api/crm/activities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.activities.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/crm/activities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.activities.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/crm/contacts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.contacts.list", ctx)
	}, false, false)

	r.Handle("GET", "/api/crm/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.dashboard", ctx)
	}, false, false)

	// --- Projects API ---
	r.Handle("GET", "/api/projects", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/projects", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/projects/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.update", ctx)
	}, true, false)

	r.Handle("DELETE", "/api/projects/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.delete", ctx)
	}, true, false)

	r.Handle("GET", "/api/projects/tasks", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/projects/tasks", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/projects/tasks/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.update", ctx)
	}, true, false)

	r.Handle("POST", "/api/projects/tasks/{id}/complete", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.complete", ctx)
	}, true, false)

	r.Handle("DELETE", "/api/projects/tasks/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.delete", ctx)
	}, true, false)

	r.Handle("GET", "/api/projects/timesheets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.timesheets.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/projects/timesheets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.timesheets.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/projects/timesheets/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.timesheets.summary", ctx)
	}, false, false)

	r.Handle("GET", "/api/projects/milestones", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.milestones.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/projects/milestones", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.milestones.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/projects/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.dashboard", ctx)
	}, false, false)

	// --- Reports API ---
	r.Handle("GET", "/api/reports/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.dashboard", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/sales/by-period", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.sales.by_period", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/sales/top-products", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.sales.top_products", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/sales/top-clients", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.sales.top_clients", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/inventory/stock", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.inventory.stock_status", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/inventory/movements", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.inventory.movements", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/financial/cashflow", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.financial.cashflow", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/crm/conversion", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.crm.conversion", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/crm/activities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.crm.activity_summary", ctx)
	}, false, false)

	r.Handle("GET", "/api/reports/projects/progress", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.projects.progress", ctx)
	}, false, false)

	r.Handle("GET", "/api/projects/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.dashboard", ctx)
	}, false, false)

	// --- i18n API ---
	r.Handle("GET", "/api/i18n/langs", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.langs", ctx)
	}, false, false)

	r.Handle("POST", "/api/i18n/set", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.set", ctx)
	}, false, false)

	r.Handle("GET", "/api/i18n/translate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.translate", ctx)
	}, false, false)

	r.Handle("GET", "/api/i18n/all", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.all", ctx)
	}, false, false)

	// --- File Upload API ---
	r.Handle("GET", "/api/files", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.files.list", ctx)
	}, false, false)

	r.Handle("GET", "/api/files/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.files.get", ctx)
	}, false, false)

	r.Handle("DELETE", "/api/files/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.files.delete", ctx)
	}, true, false)

	// --- Accounting Real: Taxes, Currencies, DIOT, Retentions ---
	r.Handle("GET", "/api/accounting/tax-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax_rates.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/tax-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax_rates.create", ctx)
	}, true, false)

	r.Handle("PUT", "/api/accounting/tax-rates/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax_rates.update", ctx)
	}, true, false)

	r.Handle("DELETE", "/api/accounting/tax-rates/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax_rates.delete", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/currencies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.currencies.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/currencies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.currencies.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/exchange-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.exchange_rates.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/exchange-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.exchange_rates.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/exchange-rates/convert", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.exchange_rates.convert", ctx)
	}, false, false)

	r.Handle("GET", "/api/accounting/diot/generate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.diot.generate", ctx)
	}, false, false)

	r.Handle("GET", "/api/accounting/retentions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.retentions.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/retentions/calculate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.retentions.calculate", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/fiscal-periods", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.fiscal_periods.list", ctx)
	}, false, false)

	r.Handle("POST", "/api/accounting/fiscal-periods", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.fiscal_periods.create", ctx)
	}, true, false)

	r.Handle("GET", "/api/accounting/tax/calculate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax.calculate", ctx)
	}, false, false)

	r.Handle("GET", "/api/accounting/tax/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax.summary", ctx)
	}, false, false)

	// --- WebSocket: real-time notifications ---
	r.Handle("GET", "/ws", func(ctx map[string]interface{}) (interface{}, error) {
		return map[string]interface{}{"status": "use WebSocket protocol at /ws"}, nil
	}, false, true)

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
