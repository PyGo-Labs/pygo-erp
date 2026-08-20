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
	}, false)

	r.Handle("GET", "/metrics", func(ctx map[string]interface{}) (interface{}, error) {
		return observability.GetMetrics(), nil
	}, false)

	// --- HTML Views ---
	r.Handle("GET", "/", func(ctx map[string]interface{}) (interface{}, error) {
		return loadTemplate("app/views/dashboard.html"), nil
	}, false)

	for _, view := range []string{"/productos", "/clientes", "/facturas", "/login", "/companies", "/users", "/inventory"} {
		r.Handle("GET", view, func(ctx map[string]interface{}) (interface{}, error) {
			return loadTemplate("app/views" + ctx["_path"].(string) + ".html"), nil
		}, false)
	}

	// --- Auth API ---
	r.Handle("POST", "/api/auth/login", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.login", ctx)
	}, false)

	r.Handle("POST", "/api/auth/logout", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.logout", ctx)
	}, false)

	r.Handle("GET", "/api/auth/me", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.me", ctx)
	}, false)

	r.Handle("GET", "/api/auth/users", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.list", ctx)
	}, false)

	r.Handle("POST", "/api/auth/users", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.create", ctx)
	}, false)

	r.Handle("PUT", "/api/auth/users/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/auth/users/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.auth.users.delete", ctx)
	}, false)

	// --- Tenancy API ---
	r.Handle("GET", "/api/tenancy/companies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.list", ctx)
	}, false)

	r.Handle("POST", "/api/tenancy/companies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.create", ctx)
	}, false)

	r.Handle("PUT", "/api/tenancy/companies/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/tenancy/companies/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.companies.delete", ctx)
	}, false)

	r.Handle("POST", "/api/tenancy/switch", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.switch", ctx)
	}, false)

	r.Handle("GET", "/api/tenancy/current", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tenancy.current", ctx)
	}, false)

	// --- Inventory API ---
	r.Handle("GET", "/api/inventory/warehouses", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.warehouses.list", ctx)
	}, false)

	r.Handle("POST", "/api/inventory/warehouses", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.warehouses.create", ctx)
	}, false)

	r.Handle("GET", "/api/inventory/stock", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.list", ctx)
	}, false)

	r.Handle("POST", "/api/inventory/stock/transfer", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.transfer", ctx)
	}, false)

	r.Handle("POST", "/api/inventory/stock/adjust", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.adjust", ctx)
	}, false)

	r.Handle("GET", "/api/inventory/stock/movements", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.movements", ctx)
	}, false)

	r.Handle("GET", "/api/inventory/stock/alerts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.stock.alerts", ctx)
	}, false)

	r.Handle("GET", "/api/inventory/categories", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.categories.list", ctx)
	}, false)

	r.Handle("POST", "/api/inventory/categories", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.inventory.categories.create", ctx)
	}, false)

	// --- Sales API ---
	r.Handle("GET", "/api/sales/orders", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.list", ctx)
	}, false)

	r.Handle("POST", "/api/sales/orders", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.create", ctx)
	}, false)

	r.Handle("POST", "/api/sales/orders/{id}/confirm", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.confirm", ctx)
	}, false)

	r.Handle("POST", "/api/sales/orders/{id}/deliver", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.deliver", ctx)
	}, false)

	r.Handle("POST", "/api/sales/orders/{id}/invoice", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.invoice", ctx)
	}, false)

	r.Handle("POST", "/api/sales/orders/{id}/cancel", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.orders.cancel", ctx)
	}, false)

	r.Handle("GET", "/api/sales/purchase", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.purchase.list", ctx)
	}, false)

	r.Handle("POST", "/api/sales/purchase", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.purchase.create", ctx)
	}, false)

	r.Handle("GET", "/api/sales/quotes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.quotes.list", ctx)
	}, false)

	r.Handle("POST", "/api/sales/quotes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.quotes.create", ctx)
	}, false)

	r.Handle("GET", "/api/sales/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sales.summary", ctx)
	}, false)

	// --- Accounting Real API ---
	r.Handle("GET", "/api/accounting/tax-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax_rates.list", ctx)
	}, false)

	r.Handle("POST", "/api/accounting/tax-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax_rates.create", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/currencies", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.currencies.list", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/exchange-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.exchange_rates.list", ctx)
	}, false)

	r.Handle("POST", "/api/accounting/exchange-rates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.exchange_rates.create", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/exchange-rates/convert", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.exchange_rates.convert", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/diot/generate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.diot.generate", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/retentions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.retentions.list", ctx)
	}, false)

	r.Handle("POST", "/api/accounting/retentions/calculate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.retentions.calculate", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/fiscal-periods", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.fiscal_periods.list", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/tax/calculate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax.calculate", ctx)
	}, false)

	r.Handle("GET", "/api/accounting/tax/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.accounting.tax.summary", ctx)
	}, false)

	// --- CRM API ---
	r.Handle("GET", "/api/crm/leads", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.list", ctx)
	}, false)

	r.Handle("POST", "/api/crm/leads", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.create", ctx)
	}, false)

	r.Handle("POST", "/api/crm/leads/{id}/convert", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.leads.convert", ctx)
	}, false)

	r.Handle("GET", "/api/crm/opportunities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.list", ctx)
	}, false)

	r.Handle("POST", "/api/crm/opportunities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.create", ctx)
	}, false)

	r.Handle("POST", "/api/crm/opportunities/{id}/won", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.won", ctx)
	}, false)

	r.Handle("POST", "/api/crm/opportunities/{id}/lost", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.opportunities.lost", ctx)
	}, false)

	r.Handle("GET", "/api/crm/pipeline/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.pipeline.summary", ctx)
	}, false)

	r.Handle("GET", "/api/crm/pipeline/funnel", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.pipeline.funnel", ctx)
	}, false)

	r.Handle("GET", "/api/crm/activities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.activities.list", ctx)
	}, false)

	r.Handle("POST", "/api/crm/activities", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.activities.create", ctx)
	}, false)

	r.Handle("GET", "/api/crm/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.crm.dashboard", ctx)
	}, false)

	// --- Projects API ---
	r.Handle("GET", "/api/projects", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.list", ctx)
	}, false)

	r.Handle("POST", "/api/projects", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.create", ctx)
	}, false)

	r.Handle("PUT", "/api/projects/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/projects/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.delete", ctx)
	}, false)

	r.Handle("GET", "/api/projects/tasks", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.list", ctx)
	}, false)

	r.Handle("POST", "/api/projects/tasks", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.create", ctx)
	}, false)

	r.Handle("PUT", "/api/projects/tasks/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.update", ctx)
	}, false)

	r.Handle("POST", "/api/projects/tasks/{id}/complete", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.tasks.complete", ctx)
	}, false)

	r.Handle("GET", "/api/projects/timesheets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.timesheets.list", ctx)
	}, false)

	r.Handle("POST", "/api/projects/timesheets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.timesheets.create", ctx)
	}, false)

	r.Handle("GET", "/api/projects/milestones", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.milestones.list", ctx)
	}, false)

	r.Handle("POST", "/api/projects/milestones", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.milestones.create", ctx)
	}, false)

	r.Handle("GET", "/api/projects/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.projects.dashboard", ctx)
	}, false)

	// --- Workflow API ---
	r.Handle("GET", "/api/workflow/states", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.states.list", ctx)
	}, false)

	r.Handle("POST", "/api/workflow/states", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.states.create", ctx)
	}, false)

	r.Handle("GET", "/api/workflow/transitions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.transitions.list", ctx)
	}, false)

	r.Handle("POST", "/api/workflow/transitions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.transitions.create", ctx)
	}, false)

	r.Handle("GET", "/api/workflow/history", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.history.list", ctx)
	}, false)

	r.Handle("POST", "/api/workflow/transition/execute", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.transition.execute", ctx)
	}, false)

	r.Handle("POST", "/api/workflow/init/sales-order", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.workflow.init_sales_order", ctx)
	}, false)

	// --- Permissions API ---
	r.Handle("GET", "/api/permissions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.permissions.list", ctx)
	}, false)

	r.Handle("POST", "/api/permissions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.permissions.create", ctx)
	}, false)

	r.Handle("GET", "/api/permissions/check", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.permissions.check", ctx)
	}, false)

	r.Handle("POST", "/api/permissions/grant", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.permissions.grant_to_user", ctx)
	}, false)

	r.Handle("POST", "/api/permissions/revoke", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.permissions.revoke_from_user", ctx)
	}, false)

	// --- i18n API ---
	r.Handle("GET", "/api/i18n/langs", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.langs", ctx)
	}, false)

	r.Handle("POST", "/api/i18n/set", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.set", ctx)
	}, false)

	r.Handle("GET", "/api/i18n/all", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.i18n.all", ctx)
	}, false)

	// --- Files API ---
	r.Handle("GET", "/api/files", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.files.list", ctx)
	}, false)

	r.Handle("GET", "/api/files/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.files.get", ctx)
	}, false)

	r.Handle("DELETE", "/api/files/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.files.delete", ctx)
	}, false)

	// --- Export/Import API ---
	r.Handle("GET", "/api/export/csv", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.export.csv", ctx)
	}, false)

	r.Handle("POST", "/api/import/csv", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.import.csv", ctx)
	}, false)

	r.Handle("GET", "/api/import/templates", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.import.templates", ctx)
	}, false)

	// --- Reports PDF ---
	r.Handle("GET", "/api/reports/pdf/invoice", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.pdf.invoice", ctx)
	}, false)

	r.Handle("GET", "/api/reports/pdf/quote", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.pdf.quote", ctx)
	}, false)

	r.Handle("GET", "/api/reports/pdf/ticket", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.reports.pdf.ticket", ctx)
	}, false)

	// --- REST Productos/Clientes/Facturas ---
	r.Handle("GET", "/api/productos", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.list", ctx)
	}, false)

	r.Handle("GET", "/api/productos/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.find", ctx)
	}, false)

	r.Handle("POST", "/api/productos", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.create", ctx)
	}, false)

	r.Handle("PUT", "/api/productos/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/productos/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.productos.delete", ctx)
	}, false)

	r.Handle("GET", "/api/clientes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.list", ctx)
	}, false)

	r.Handle("GET", "/api/clientes/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.find", ctx)
	}, false)

	r.Handle("POST", "/api/clientes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.create", ctx)
	}, false)

	r.Handle("PUT", "/api/clientes/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/clientes/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.clientes.delete", ctx)
	}, false)

	r.Handle("GET", "/api/facturas", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.list", ctx)
	}, false)

	r.Handle("GET", "/api/facturas/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.find", ctx)
	}, false)

	r.Handle("POST", "/api/facturas", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.create", ctx)
	}, false)

	r.Handle("PUT", "/api/facturas/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/facturas/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.services.facturas.delete", ctx)
	}, false)

	// --- Excel Export ---
	r.Handle("GET", "/api/export/excel", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.export.excel", ctx)
	}, false)

	// --- Notifications ---
	r.Handle("GET", "/api/notifications/config", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.notifications.config", ctx)
	}, false)

	r.Handle("POST", "/api/notifications/test", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.notifications.send_test", ctx)
	}, false)

	r.Handle("POST", "/api/notifications/order-created", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.notifications.order_created", ctx)
	}, false)

	r.Handle("POST", "/api/notifications/invoice-generated", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.notifications.invoice_generated", ctx)
	}, false)

	// --- Cache ---
	r.Handle("GET", "/api/cache/stats", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cache.stats", ctx)
	}, false)

	r.Handle("GET", "/api/cache/get", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cache.get", ctx)
	}, false)

	r.Handle("POST", "/api/cache/set", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cache.set", ctx)
	}, false)

	r.Handle("DELETE", "/api/cache/clear", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cache.clear", ctx)
	}, false)

	// --- B1: UoM ---
	r.Handle("GET", "/api/uom/categories", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.uom.categories.list", ctx)
	}, false)

	r.Handle("POST", "/api/uom/categories", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.uom.categories.create", ctx)
	}, false)

	r.Handle("GET", "/api/uom", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.uom.list", ctx)
	}, false)

	r.Handle("POST", "/api/uom", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.uom.create", ctx)
	}, false)

	r.Handle("GET", "/api/uom/convert", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.uom.convert", ctx)
	}, false)

	// --- B1: Pricelists ---
	r.Handle("GET", "/api/pricelists", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.pricelists.list", ctx)
	}, false)

	r.Handle("POST", "/api/pricelists", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.pricelists.create", ctx)
	}, false)

	r.Handle("GET", "/api/pricelists/items", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.pricelists.items.list", ctx)
	}, false)

	r.Handle("POST", "/api/pricelists/items", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.pricelists.items.create", ctx)
	}, false)

	r.Handle("GET", "/api/pricelists/resolve", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.pricelists.resolve", ctx)
	}, false)

	r.Handle("POST", "/api/pricelists/assign-customer", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.pricelists.assign_customer", ctx)
	}, false)

	// --- B1: Payment terms ---
	r.Handle("GET", "/api/payment-terms", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.payment_terms.list", ctx)
	}, false)

	r.Handle("POST", "/api/payment-terms", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.payment_terms.create", ctx)
	}, false)

	r.Handle("GET", "/api/payment-terms/schedule", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.payment_terms.schedule", ctx)
	}, false)

	// --- B1: Sequences ---
	r.Handle("GET", "/api/sequences", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sequences.list", ctx)
	}, false)

	r.Handle("POST", "/api/sequences", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sequences.create", ctx)
	}, false)

	r.Handle("POST", "/api/sequences/next", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.sequences.next", ctx)
	}, false)

	// --- B2: Suppliers ---
	r.Handle("GET", "/api/suppliers", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.list", ctx)
	}, false)

	r.Handle("POST", "/api/suppliers", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.create", ctx)
	}, false)

	r.Handle("PUT", "/api/suppliers/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.update", ctx)
	}, false)

	r.Handle("DELETE", "/api/suppliers/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.delete", ctx)
	}, false)

	r.Handle("GET", "/api/suppliers/agreements", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.agreements.list", ctx)
	}, false)

	r.Handle("POST", "/api/suppliers/agreements", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.agreements.create", ctx)
	}, false)

	r.Handle("GET", "/api/suppliers/best-price", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.suppliers.best_price", ctx)
	}, false)

	// --- B2: RFQ ---
	r.Handle("GET", "/api/rfq", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.rfq.list", ctx)
	}, false)

	r.Handle("POST", "/api/rfq", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.rfq.create", ctx)
	}, false)

	r.Handle("POST", "/api/rfq/{id}/send", func(ctx map[string]interface{}) (interface{}, error) {
		ctx["rfq_id"] = ctx["id"]
		return app.Call("core.rfq.send", ctx)
	}, false)

	r.Handle("POST", "/api/rfq/quotes", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.rfq.quotes.add", ctx)
	}, false)

	r.Handle("GET", "/api/rfq/compare", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.rfq.compare", ctx)
	}, false)

	r.Handle("POST", "/api/rfq/award", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.rfq.award", ctx)
	}, false)

	// --- B2: Receipts & returns ---
	r.Handle("GET", "/api/purchase/receipts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.purchase.receipts.list", ctx)
	}, false)

	r.Handle("POST", "/api/purchase/receipts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.purchase.receipts.create", ctx)
	}, false)

	r.Handle("GET", "/api/purchase/receipts/pending", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.purchase.receipts.pending", ctx)
	}, false)

	r.Handle("GET", "/api/purchase/returns", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.purchase.returns.list", ctx)
	}, false)

	r.Handle("POST", "/api/purchase/returns", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.purchase.returns.create", ctx)
	}, false)

	// --- B3: Cost centers & budgets ---
	r.Handle("GET", "/api/cost-centers", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cost_centers.list", ctx)
	}, false)

	r.Handle("POST", "/api/cost-centers", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cost_centers.create", ctx)
	}, false)

	r.Handle("POST", "/api/cost-centers/allocate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cost_centers.allocate", ctx)
	}, false)

	r.Handle("GET", "/api/cost-centers/report", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.cost_centers.report", ctx)
	}, false)

	r.Handle("GET", "/api/budgets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.budgets.list", ctx)
	}, false)

	r.Handle("POST", "/api/budgets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.budgets.create", ctx)
	}, false)

	r.Handle("GET", "/api/budgets/vs-actual", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.budgets.vs_actual", ctx)
	}, false)

	// --- B3: Fixed assets ---
	r.Handle("GET", "/api/assets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.assets.list", ctx)
	}, false)

	r.Handle("POST", "/api/assets", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.assets.create", ctx)
	}, false)

	r.Handle("GET", "/api/assets/schedule", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.assets.schedule", ctx)
	}, false)

	r.Handle("POST", "/api/assets/depreciate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.assets.depreciate", ctx)
	}, false)

	r.Handle("POST", "/api/assets/dispose", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.assets.dispose", ctx)
	}, false)

	r.Handle("GET", "/api/assets/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.assets.summary", ctx)
	}, false)

	// --- B3: Payments & aging ---
	r.Handle("GET", "/api/payments", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.payments.list", ctx)
	}, false)

	r.Handle("POST", "/api/payments", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.payments.register", ctx)
	}, false)

	r.Handle("GET", "/api/ar/aging", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.ar.aging", ctx)
	}, false)

	r.Handle("GET", "/api/ap/aging", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.ap.aging", ctx)
	}, false)

	// --- B3: Banking ---
	r.Handle("GET", "/api/bank/accounts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.bank.accounts.list", ctx)
	}, false)

	r.Handle("POST", "/api/bank/accounts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.bank.accounts.create", ctx)
	}, false)

	r.Handle("POST", "/api/bank/statements/import", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.bank.statement.import_lines", ctx)
	}, false)

	r.Handle("POST", "/api/bank/reconcile/auto", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.bank.reconcile.auto", ctx)
	}, false)

	r.Handle("GET", "/api/bank/reconcile/status", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.bank.reconcile.status", ctx)
	}, false)

	// --- B4: HR org ---
	r.Handle("GET", "/api/hr/departments", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.departments.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/departments", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.departments.create", ctx)
	}, false)

	r.Handle("GET", "/api/hr/positions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.positions.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/positions", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.positions.create", ctx)
	}, false)

	r.Handle("GET", "/api/hr/employees", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.employees.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/employees", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.employees.create", ctx)
	}, false)

	r.Handle("PUT", "/api/hr/employees/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.employees.update", ctx)
	}, false)

	r.Handle("POST", "/api/hr/employees/terminate", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.employees.terminate", ctx)
	}, false)

	r.Handle("GET", "/api/hr/contracts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.contracts.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/contracts", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.contracts.create", ctx)
	}, false)

	r.Handle("GET", "/api/hr/headcount", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.headcount", ctx)
	}, false)

	// --- B4: Leave ---
	r.Handle("GET", "/api/hr/leave-types", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave_types.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/leave-types", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave_types.create", ctx)
	}, false)

	r.Handle("GET", "/api/hr/leave", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/leave", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave.request", ctx)
	}, false)

	r.Handle("POST", "/api/hr/leave/approve", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave.approve", ctx)
	}, false)

	r.Handle("POST", "/api/hr/leave/reject", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave.reject", ctx)
	}, false)

	r.Handle("GET", "/api/hr/leave/balance", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.leave.balance", ctx)
	}, false)

	// --- B4: Expenses ---
	r.Handle("GET", "/api/hr/expenses", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.expenses.list", ctx)
	}, false)

	r.Handle("POST", "/api/hr/expenses", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.expenses.create", ctx)
	}, false)

	r.Handle("POST", "/api/hr/expenses/submit", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.expenses.submit", ctx)
	}, false)

	r.Handle("POST", "/api/hr/expenses/approve", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.expenses.approve", ctx)
	}, false)

	r.Handle("POST", "/api/hr/expenses/reimburse", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hr.expenses.reimburse", ctx)
	}, false)

	// --- B5: BOM ---
	r.Handle("GET", "/api/mrp/boms", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.boms.list", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/boms", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.boms.create", ctx)
	}, false)

	r.Handle("GET", "/api/mrp/boms/explode", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.boms.explode", ctx)
	}, false)

	r.Handle("GET", "/api/mrp/boms/cost", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.boms.cost", ctx)
	}, false)

	// --- B5: Work centers & routings ---
	r.Handle("GET", "/api/mrp/work-centers", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.work_centers.list", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/work-centers", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.work_centers.create", ctx)
	}, false)

	r.Handle("GET", "/api/mrp/routings", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.routings.list", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/routings", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.routings.create", ctx)
	}, false)

	// --- B5: Production orders ---
	r.Handle("GET", "/api/mrp/production", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.production.list", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/production", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.production.create", ctx)
	}, false)

	r.Handle("GET", "/api/mrp/production/availability", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.production.check_availability", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/production/start", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.production.start", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/production/complete", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.production.complete", ctx)
	}, false)

	r.Handle("POST", "/api/mrp/production/cancel", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.production.cancel", ctx)
	}, false)

	r.Handle("GET", "/api/mrp/dashboard", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.mrp.dashboard", ctx)
	}, false)

	// --- Fase A: Module system ---
	r.Handle("GET", "/api/modules", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.list", ctx)
	}, false)

	r.Handle("POST", "/api/modules/scan", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.scan", ctx)
	}, false)

	r.Handle("GET", "/api/modules/info", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.info", ctx)
	}, false)

	r.Handle("POST", "/api/modules/install", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.install", ctx)
	}, false)

	r.Handle("POST", "/api/modules/uninstall", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.uninstall", ctx)
	}, false)

	r.Handle("POST", "/api/modules/enable", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.enable", ctx)
	}, false)

	r.Handle("POST", "/api/modules/disable", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.disable", ctx)
	}, false)

	r.Handle("GET", "/api/modules/graph", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.modules.dependency_graph", ctx)
	}, false)

	// --- Fase A: Hooks ---
	r.Handle("GET", "/api/hooks", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hooks.list", ctx)
	}, false)

	r.Handle("POST", "/api/hooks", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hooks.register", ctx)
	}, false)

	r.Handle("POST", "/api/hooks/run", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.hooks.run", ctx)
	}, false)

	// --- Fase A: Generic tax engine ---
	r.Handle("GET", "/api/tax", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tax.list", ctx)
	}, false)

	r.Handle("POST", "/api/tax", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tax.create", ctx)
	}, false)

	r.Handle("GET", "/api/tax/groups", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tax.groups.list", ctx)
	}, false)

	r.Handle("POST", "/api/tax/groups", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tax.groups.create", ctx)
	}, false)

	r.Handle("GET", "/api/tax/compute", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tax.compute", ctx)
	}, false)

	r.Handle("POST", "/api/tax/compute-document", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.tax.compute_document", ctx)
	}, false)

	// --- Dynamic module handler dispatch ---
	// Lets an installed module expose handlers without new Go routes.
	r.Handle("POST", "/api/module/call", func(ctx map[string]interface{}) (interface{}, error) {
		handler, ok := ctx["handler"].(string)
		if !ok || handler == "" {
			return map[string]interface{}{"error": "handler required"}, nil
		}
		delete(ctx, "handler")
		return app.Call(handler, ctx)
	}, false)

	r.Handle("GET", "/api/module/call", func(ctx map[string]interface{}) (interface{}, error) {
		handler, ok := ctx["handler"].(string)
		if !ok || handler == "" {
			return map[string]interface{}{"error": "handler required"}, nil
		}
		delete(ctx, "handler")
		return app.Call(handler, ctx)
	}, false)

	// --- Fase C: Setup wizard ---
	r.Handle("GET", "/api/setup/status", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.status", ctx)
	}, false)

	r.Handle("GET", "/api/setup/countries", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.countries", ctx)
	}, false)

	r.Handle("POST", "/api/setup/company", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.company", ctx)
	}, false)

	r.Handle("POST", "/api/setup/localization", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.localization", ctx)
	}, false)

	r.Handle("POST", "/api/setup/finalize", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.finalize", ctx)
	}, false)

	r.Handle("GET", "/api/setup/settings", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.settings", ctx)
	}, false)

	r.Handle("POST", "/api/setup/settings", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.set_setting", ctx)
	}, false)

	r.Handle("POST", "/api/setup/reset", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.setup.reset", ctx)
	}, false)

	// --- Fase C: Audit trail ---
	r.Handle("POST", "/api/audit", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.audit.record", ctx)
	}, false)

	r.Handle("GET", "/api/audit/history", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.audit.history", ctx)
	}, false)

	r.Handle("GET", "/api/audit/by-user", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.audit.by_user", ctx)
	}, false)

	r.Handle("GET", "/api/audit/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.audit.summary", ctx)
	}, false)

	// --- Fase C: Attachments ---
	r.Handle("GET", "/api/attachments", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.attachments.list", ctx)
	}, false)

	r.Handle("POST", "/api/attachments", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.attachments.attach", ctx)
	}, false)

	r.Handle("DELETE", "/api/attachments/{id}", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.attachments.detach", ctx)
	}, false)

	r.Handle("GET", "/api/attachments/summary", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.attachments.summary", ctx)
	}, false)

	// --- Fase C: System readiness & demo data ---
	r.Handle("GET", "/api/system/readiness", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.system.readiness", ctx)
	}, false)

	r.Handle("POST", "/api/demo/load", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.demo.load", ctx)
	}, false)

	r.Handle("POST", "/api/demo/clear", func(ctx map[string]interface{}) (interface{}, error) {
		return app.Call("core.demo.clear", ctx)
	}, false)
}

func loadTemplate(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Sprintf("Error loading template: %v", err)
	}
	return string(data)
}
